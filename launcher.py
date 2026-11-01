r"""Tkinter 启动器 · G1 范围选择界面（待办 G1，任务卡 T3-04）。

依据：方案 P4（预设四目录 %APPDATA% / %LOCALAPPDATA% / %PROGRAMDATA% / C:\Program Files）、
P5（启动即检 build >= 22621，不足拒绝并提示）、P6（仅固定本地盘；可移动/网络/光驱等
在选择界面置灰并说明原因）；开发规范 §1（引擎与 UI 严格分离——本启动器为包外独立入口，
`disk_audit` 包内任何模块不得 import tkinter）。

耦合边界（任务卡实现约束）：本模块对 `disk_audit` 包的依赖仅限文案资源
`disk_audit.engine.texts`、报告落盘/淘汰/打开 `disk_audit.reports`，以及
scan/judge/render 三个接口入口（T3-06 接线，见 execute_audit；T3-05 进度/中止
将经 after() 调度把该流水线异步化）。UI 不 import 判定细节、不直接触碰
报告文件（U-2：落盘仅经 disk_audit.reports 守卫写入 DATA_DIR\reports\）。

可注入点（验收①②）：build 探测 `get_windows_build`、盘符枚举 `enumerate_drive_types`
均可经 `run(...)` 注入替换；体检流水线六环经 `AuditDeps` 注入（T3-06）；
纯逻辑（`is_build_supported` / `build_drive_entries` / `build_preset_rows` /
`execute_audit`）无 Tk I/O，供 tests/test_launcher.py 无 Tk 测试。
tkinter 延迟导入：纯逻辑可无 Tk 环境加载，Tk 根仅在真实运行时创建。
"""
from __future__ import annotations

import argparse
import ctypes
import os
import re
import sys
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from disk_audit import reports
from disk_audit.engine import texts

LAUNCHER_TEXTS = texts.LAUNCHER_TEXTS
G3_TEXTS = texts.G3_TEXTS

# P5：Win11 22H2（build 22621）及以上，启动时检测
MIN_BUILD = 22621

# GetDriveTypeW 返回的盘型常量（Win32 DEVICE_TYPE 语义）
DRIVE_UNKNOWN = 0
DRIVE_NO_ROOT_DIR = 1
DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
DRIVE_REMOTE = 4
DRIVE_CDROM = 5
DRIVE_RAMDISK = 6

EXIT_OK = 0
# 预检失败退出码：与 argparse 用法错误(2)、引擎扫描失败(2)区分
EXIT_UNSUPPORTED = 3

# 自定义文件夹单选项哨兵值（自定义路径存独立变量，单选值只表意图）
CUSTOM_SENTINEL = "__custom_folder__"

_ENV_VAR_RE = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")

BuildProbe = Callable[[], int]
DriveProbe = Callable[[], Mapping[str, int]]
NotifyUnsupported = Callable[[int], None]
WindowFactory = Callable[[Sequence["DriveEntry"], Sequence["PresetRow"], int], None]


@dataclass(frozen=True)
class AuditDeps:
    """体检流水线六环依赖（T3-06 接线）。

    全部可注入：全链路替身单测（scan/judge/render/save/prune/open）与 G2
    异步化改造都以本结构为边界；default_deps() 给出真实装配。
    """

    scan: Callable[[str], dict]  # 范围 → scan 结果 JSON dict（只读采集）
    judge: Callable[[dict], dict]  # scan 结果 → report-v1 dict（六层判定）
    render: Callable[[dict], str]  # report-v1 → 离线单文件 HTML
    save: Callable[[str], str]  # HTML → 落盘，返回报告绝对路径
    prune: Callable[[], list[str]]  # 旧报告淘汰（保留 12 份）
    open: Callable[[str], None]  # 默认浏览器打开报告（只读）


@dataclass(frozen=True)
class PresetDir:
    """P4 预设项模型：key 标识、label_key 文案键、template 环境变量模板。"""

    key: str
    label_key: str
    template: str


@dataclass(frozen=True)
class PresetRow:
    """预设单选行：text = 中文标签 + 解析后路径，path 为单选值。"""

    key: str
    text: str
    path: str


@dataclass(frozen=True)
class DriveEntry:
    """盘符行模型：supported=False 时 reason 给出置灰原因（P6）。"""

    letter: str
    drive_type: int
    supported: bool
    reason: str


# P4 预设四目录（顺序 = 方案定稿口径）
PRESET_DIRS: tuple[PresetDir, ...] = (
    PresetDir("appdata", "preset_label_appdata", "%APPDATA%"),
    PresetDir("localappdata", "preset_label_localappdata", "%LOCALAPPDATA%"),
    PresetDir("programdata", "preset_label_programdata", "%PROGRAMDATA%"),
    PresetDir("program_files", "preset_label_programfiles", r"C:\Program Files"),
)

# 不支持盘型 → 置灰原因文案键（P6）；UNKNOWN 与 NO_ROOT_DIR 同按无法识别处理
DRIVE_REASON_KEYS: dict[int, str] = {
    DRIVE_UNKNOWN: "drive_reason_unknown",
    DRIVE_NO_ROOT_DIR: "drive_reason_unknown",
    DRIVE_REMOVABLE: "drive_reason_removable",
    DRIVE_REMOTE: "drive_reason_remote",
    DRIVE_CDROM: "drive_reason_cdrom",
    DRIVE_RAMDISK: "drive_reason_ramdisk",
}


def _force_utf8_stdio() -> None:
    """中文 print 前 UTF-8 化（T-01 教训：Windows runner 默认 cp1252 假红）。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (OSError, ValueError):  # 流已关闭/不可重配等场景
                pass


def get_windows_build() -> int:
    """真实探测（P5 注入点）：当前系统 build 号。仅 Windows 可用。"""
    return int(sys.getwindowsversion().build)


def is_build_supported(build: int, minimum: int = MIN_BUILD) -> bool:
    """纯函数（P5）：build 是否满足最低版本要求。"""
    return build >= minimum


def enumerate_drive_types() -> dict[str, int]:
    """真实枚举（P6 注入点）：GetLogicalDrives 位掩码 + GetDriveTypeW 逐盘取型。"""
    kernel32 = ctypes.windll.kernel32
    bitmask = int(kernel32.GetLogicalDrives()) & 0x3FFFFFF
    result: dict[str, int] = {}
    for index in range(26):
        if (bitmask >> index) & 1:
            letter = f"{chr(ord('A') + index)}:"
            result[letter] = int(kernel32.GetDriveTypeW(letter + "\\"))
    return result


def build_drive_entries(drive_types: Mapping[str, int]) -> list[DriveEntry]:
    """纯函数（验收②注入点）：盘型映射 → 置灰判定 + 原因（P6：仅固定本地盘可选）。"""
    entries: list[DriveEntry] = []
    for letter in sorted(drive_types):
        drive_type = int(drive_types[letter])
        if drive_type == DRIVE_FIXED:
            entries.append(DriveEntry(letter, drive_type, True, ""))
        else:
            reason_key = DRIVE_REASON_KEYS.get(drive_type, "drive_reason_unknown")
            entries.append(DriveEntry(letter, drive_type, False, LAUNCHER_TEXTS[reason_key]))
    return entries


def expand_preset_env(template: str, env: Mapping[str, str]) -> str:
    """纯函数：%VAR% 展开（env 注入便于测试）；缺失变量保留原文，交由确认时存在性校验兜底。"""
    return _ENV_VAR_RE.sub(lambda match: env.get(match.group(1), match.group(0)), template)


def build_preset_rows(env: Mapping[str, str] | None = None) -> list[PresetRow]:
    """纯函数（P4）：四预设 → 单选行（文本 = 中文标签 + 解析后路径）。"""
    if env is None:
        env = os.environ
    rows: list[PresetRow] = []
    for item in PRESET_DIRS:
        path = expand_preset_env(item.template, env)
        label = LAUNCHER_TEXTS[item.label_key]
        rows.append(PresetRow(item.key, f"{label}：{path}", path))
    return rows


def default_deps(reports_dir: str | None = None) -> "AuditDeps":
    """真实装配（T3-06）：scan/judge/render 绑定引擎入口，save/prune/open 绑定 reports 模块。

    延迟 import：launcher 模块加载不拖入扫描/判定栈（T3-04 延迟导入模式延续）；
    reports_dir 注入时 save/prune 落点随之替换（测试替身根），默认包内 REPORTS_DIR。
    """
    from disk_audit.engine.render import render_report
    from disk_audit.engine.report import judge_scan_result
    from disk_audit.scanner import scan_path

    return AuditDeps(
        scan=lambda path: scan_path(path).to_json_dict(),
        judge=judge_scan_result,
        render=render_report,
        save=lambda html_text: reports.save_report(html_text, reports_dir=reports_dir),
        prune=lambda: reports.prune_reports(reports_dir=reports_dir),
        open=reports.open_report,
    )


def execute_audit(path: str, *, deps: "AuditDeps | None" = None) -> str:
    """一次完整体检流水线（M2 闸①：选范围 → 扫描 → 浏览器自动打开 = 3 步）。

    分段清晰（每环一步，G2/T3-05 异步化时按段搬入后台线程）：
    ① scan 只读采集 → ② judge 六层判定 → ③ render 离线 HTML
    → ④ save 落盘（U-2 唯一写入位）→ ⑤ prune 淘汰保留 12 份
    → ⑥ open 默认浏览器打开（只读）。
    返回报告绝对路径；环节异常向上抛出，由调用方统一呈现失败态。
    """
    pipeline = deps if deps is not None else default_deps()
    scan_result = pipeline.scan(path)
    report = pipeline.judge(scan_result)
    html_text = pipeline.render(report)
    report_path = pipeline.save(html_text)
    pipeline.prune()
    pipeline.open(report_path)
    return report_path


def _notify_unsupported(build: int) -> None:
    """版本不足默认出口：优先图形提示；Tk 不可用时降级 stderr 文本提示。"""
    _force_utf8_stdio()
    message = LAUNCHER_TEXTS["build_unsupported"].format(build=build, min_build=MIN_BUILD)
    print(f"[launcher] {message}", file=sys.stderr)
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(LAUNCHER_TEXTS["build_unsupported_title"], message)
        root.destroy()
    except Exception:
        pass  # 图形提示不可用时仅保留文本提示，不掩盖拒绝结论


def build_scope_ui(
    root: object,
    entries: Sequence[DriveEntry],
    presets: Sequence[PresetRow],
    build: int,
) -> None:
    """组装范围选择界面（Tkinter 专属段）。

    T3-05 在此接线进度/中止（消费 C8 回调）；T3-06 已接线结果入口：
    "开始体检" → execute_audit（同步执行，G2/T3-05 将异步化）。
    U-1：点击"开始体检"即用户显式选择，此前不读取所选文件系统路径。
    """
    import tkinter as tk
    from tkinter import filedialog

    root.title(LAUNCHER_TEXTS["window_title"])
    root.geometry("720x560")
    root.minsize(640, 500)

    status_var = tk.StringVar(value="")
    scope_var = tk.StringVar(value="")
    custom_var = tk.StringVar(value="")

    build_label = tk.Label(
        root,
        text=LAUNCHER_TEXTS["build_status_ok"].format(build=build, min_build=MIN_BUILD),
        anchor="w",
    )
    build_label.pack(fill="x", padx=12, pady=(12, 4))

    scope_frame = tk.LabelFrame(root, text=LAUNCHER_TEXTS["scope_group"])
    scope_frame.pack(fill="x", padx=12, pady=4)
    for row in presets:
        tk.Radiobutton(
            scope_frame, text=row.text, value=row.path, variable=scope_var, anchor="w"
        ).pack(fill="x")

    custom_row = tk.Frame(scope_frame)
    custom_row.pack(fill="x")
    tk.Radiobutton(
        custom_row, text=LAUNCHER_TEXTS["custom_option"], value=CUSTOM_SENTINEL,
        variable=scope_var,
    ).pack(side="left")
    custom_entry = tk.Entry(custom_row, textvariable=custom_var, state="disabled")
    custom_entry.pack(side="left", fill="x", expand=True, padx=6)
    browse_button = tk.Button(
        custom_row, text=LAUNCHER_TEXTS["custom_browse"], state="disabled",
        command=lambda: _browse_folder(root, custom_var, scope_var, filedialog),
    )
    browse_button.pack(side="left")

    def _sync_custom_state(*_args: object) -> None:
        state = "normal" if scope_var.get() == CUSTOM_SENTINEL else "disabled"
        custom_entry.config(state=state)
        browse_button.config(state=state)

    scope_var.trace_add("write", _sync_custom_state)

    drives_frame = tk.LabelFrame(root, text=LAUNCHER_TEXTS["drives_group"])
    drives_frame.pack(fill="both", expand=True, padx=12, pady=4)
    for entry in entries:
        if entry.supported:
            text = f"{entry.letter}（{LAUNCHER_TEXTS['drive_fixed']}）"
            state = "normal"
        else:
            text = f"{entry.letter}（{entry.reason}）"
            state = "disabled"
        tk.Radiobutton(
            drives_frame, text=text, value=entry.letter + "\\",
            variable=scope_var, state=state, anchor="w",
        ).pack(fill="x")

    bottom = tk.Frame(root)
    bottom.pack(fill="x", padx=12, pady=(4, 12))
    tk.Button(bottom, text=LAUNCHER_TEXTS["start_button"], command=lambda: _on_start()).pack(
        anchor="w"
    )
    tk.Label(bottom, textvariable=status_var, anchor="w").pack(fill="x", pady=(6, 0))

    def _on_start() -> None:
        selected = scope_var.get()
        if selected == CUSTOM_SENTINEL:
            path = custom_var.get().strip()
            if not path:
                status_var.set(LAUNCHER_TEXTS["status_no_selection"])
                return
            if not os.path.isdir(path):
                status_var.set(LAUNCHER_TEXTS["status_missing_folder"])
                return
        elif not selected:
            status_var.set(LAUNCHER_TEXTS["status_no_selection"])
            return
        else:
            path = selected
        # T3-06 接线（同步执行；G2/T3-05 将异步化）：扫描 → 报告落盘 → 浏览器打开。
        # 分段入口 execute_audit 单点收敛，异常统一呈现失败态（X-2 不产生半成品结论）。
        status_var.set(G3_TEXTS["status_scanning"].format(path=path))
        root.update_idletasks()
        try:
            report_path = execute_audit(path)
        except Exception as exc:  # 环节失败统一出口：状态栏呈现原因，程序不中断
            status_var.set(G3_TEXTS["status_audit_failed"].format(reason=exc))
            return
        status_var.set(G3_TEXTS["status_report_opened"].format(path=report_path))


def _browse_folder(root: object, custom_var: object, scope_var: object, filedialog: object) -> None:
    """选择自定义文件夹：选定后写入输入框并切到自定义单选项。"""
    picked = filedialog.askdirectory(parent=root)
    if picked:
        custom_var.set(picked)
        scope_var.set(CUSTOM_SENTINEL)


def _default_window_factory(
    entries: Sequence[DriveEntry], presets: Sequence[PresetRow], build: int
) -> None:
    """真实开窗：创建 Tk 根 → 组装界面 → 进消息循环（仅真实运行时执行）。"""
    import tkinter as tk

    root = tk.Tk()
    build_scope_ui(root, entries, presets, build)
    root.mainloop()


def run(
    *,
    build_probe: BuildProbe | None = None,
    drive_probe: DriveProbe | None = None,
    notify_unsupported: NotifyUnsupported | None = None,
    window_factory: WindowFactory | None = None,
) -> int:
    """启动器主流程（P4~P6）：版本闸 → 盘型/预设建模 → 开窗。

    全部探测与出口可注入：测试注入假 build / 盘型映射与桩窗口工厂，
    不创建 Tk 实例（CI 稳定性）；真实运行走默认实现。
    """
    build_probe = build_probe or get_windows_build
    drive_probe = drive_probe or enumerate_drive_types
    notify_unsupported = notify_unsupported or _notify_unsupported
    window_factory = window_factory or _default_window_factory

    build = build_probe()
    if not is_build_supported(build):
        notify_unsupported(build)
        return EXIT_UNSUPPORTED
    entries = build_drive_entries(drive_probe())
    presets = build_preset_rows()
    window_factory(entries, presets, build)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """独立入口（规范 §1：启动器在独立模块/入口）。范围经界面选择（U-1），无 CLI 子命令。"""
    _force_utf8_stdio()
    argparse.ArgumentParser(prog="DiskAudit", description=LAUNCHER_TEXTS["window_title"]).parse_args(argv)
    return run()


if __name__ == "__main__":
    sys.exit(main())
