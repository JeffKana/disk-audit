r"""Tkinter 启动器 · G1 范围选择 + G2 进度与中止（待办 G1/G2，任务卡 T3-04/T3-05）。

依据：方案 P4（预设四目录 %APPDATA% / %LOCALAPPDATA% / %PROGRAMDATA% / C:\Program Files）、
P5（启动即检 build >= 22621，不足拒绝并提示）、P6（仅固定本地盘；可移动/网络/光驱等
在选择界面置灰并说明原因）、E-1（实时进度三字段，刷新 <= 500ms）、X-2/C7（中止统一
"不完整"出口，不产生半成品结论）；开发规范 §1（引擎与 UI 严格分离——本启动器为包外
独立入口，`disk_audit` 包内任何模块不得 import tkinter）。

耦合边界（任务卡实现约束）：本模块对 `disk_audit` 包的依赖仅限文案资源
`disk_audit.engine.texts`、报告落盘/淘汰/打开 `disk_audit.reports`、提权重扫
`disk_audit.elevated`（T4-01：spec/done/命令构造/只读证据装配），以及
scan/judge/render 三个接口入口（T3-06 接线，见 execute_audit；T3-05 经
run_audit_async 把该流水线搬入后台线程，进度经 after() 派发主线程），以及
T4-07（待办 F4）接线的系统交互白名单 `disk_audit.system_actions`（B3 三能力，
A1~A3 建议动作的唯一系统交互出口，default_action_deps/run_suggested_action
延迟导入）。UI 不 import 判定细节、不直接触碰报告文件（U-2：落盘仅经
disk_audit.reports 守卫写入 DATA_DIR\reports\）；除 B3 白名单外不发起任何
系统交互（U-4）。

T4-01 防重生日志：自重启调用单点化于本模块 `_shell_execute_runas`（全仓库唯一
ShellExecuteW 出口，仅 `_on_admin_rescan` 点击回调经 `request_admin_rescan` →
`_launch_elevated_self` 抵达；AST 断言调用点唯一 + 提权分支零自启动，见
tests/test_elevated.py）。前次执行曾出现 python 进程自重生链（根因未确证），
本卡以四道结构性防线阻断：单点发起 / 提权分支 AST 零自启动 / spec 一次性消费 /
UI 仅单击无重试。

可注入点（验收①②）：build 探测 `get_windows_build`、盘符枚举 `enumerate_drive_types`
均可经 `run(...)` 注入替换；体检流水线六环经 `AuditDeps` 注入（T3-06）；
建议动作三能力经 `ActionDeps` 注入（T4-07，默认装配绑定 B3）；
纯逻辑（`is_build_supported` / `build_drive_entries` / `build_preset_rows` /
`execute_audit` / `run_audit_async` / `select_operable_candidates` /
`run_suggested_action`）无 Tk I/O，供 tests/test_launcher.py 与
tests/test_launcher_actions.py 无 Tk 测试。
tkinter 延迟导入：纯逻辑可无 Tk 环境加载，Tk 根仅在真实运行时创建。

中止设计（T3-05 定夺，关闭 T2-05 未尽事项③）：产品侧同测试侧一律禁抛真
KeyboardInterrupt——中止只经协作式停止标志（threading.Event → abort_check 返回
True）走 scanner X-2 统一"不完整"出口（返回 incomplete=True），任何路径不得以
异常（尤其真 KI）传递中止信号。
"""
from __future__ import annotations

import argparse
import ctypes
import os
import re
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Mapping, Sequence

from disk_audit import elevated, reports
from disk_audit.engine import texts

if TYPE_CHECKING:  # 仅类型标注引用（延迟导入模式：模块加载不拖入扫描栈）
    from disk_audit.scanner import ProgressEvent

LAUNCHER_TEXTS = texts.LAUNCHER_TEXTS
G3_TEXTS = texts.G3_TEXTS
G2_TEXTS = texts.G2_TEXTS
F4_TEXTS = texts.F4_TEXTS
H1_TEXTS = texts.H1_TEXTS

# P5：Win11 22H2（build 22621）及以上，启动时检测
MIN_BUILD = 22621

# F4 建议动作（T4-07）：可操作候选筛选口径（A5 语义，见 select_operable_candidates）
OPERABLE_CONFIDENCES = ("高", "中")  # 5.1 四档中仅此两档可操作；受保护/低固定 A5
OPERABLE_ACTIONS = ("A1", "A2", "A3")  # 5.3 中经 B3 白名单执行的三种动作
ACTION_KEYS = ("A1", "A2", "A3")  # 界面动作按钮顺序（5.3 编号序）

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
    """体检流水线六环依赖（T3-06 接线；T3-05 扩展 scan 注入口）。

    全部可注入：全链路替身单测（scan/judge/render/save/prune/open）与 G2
    异步化改造都以本结构为边界；default_deps() 给出真实装配。
    scan 恒以 ``progress_cb`` / ``abort_check`` 关键字透传（C8 进度回调与
    C7 中止谓词；默认 None = 零开销路径，语义同 scanner.scan_path）。
    """

    scan: Callable[..., dict]  # (范围, progress_cb=, abort_check=) → scan 结果 JSON dict
    judge: Callable[[dict], dict]  # scan 结果 → report-v1 dict（六层判定）
    render: Callable[[dict], str]  # report-v1 → 离线单文件 HTML
    save: Callable[[str], str]  # HTML → 落盘，返回报告绝对路径
    prune: Callable[[], list[str]]  # 旧报告淘汰（保留 12 份）
    open: Callable[[str], None]  # 默认浏览器打开报告（只读）


@dataclass(frozen=True)
class ActionDeps:
    """建议动作三能力依赖（T4-07/F4；方案 5.3 A1~A3 + U-4 白名单）。

    全部可注入（验收①参数断言替身）；default_action_deps() 给出真实装配，
    绑定 disk_audit.system_actions（B3）三个公开能力函数——UI 侧不自行实现
    任何系统交互，越权防护完全由 B3 结构性白名单承担（SystemActionRejected）。
    """

    copy_path: Callable[[str], None]  # A1 复制路径：copy_to_clipboard(path)
    locate: Callable[[str], None]  # A2 打开所在文件夹：locate_in_explorer(path)
    open_settings: Callable[[], None]  # A3 打开系统应用列表：open_apps_settings()


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
        scan=lambda path, progress_cb=None, abort_check=None: scan_path(
            path, progress_cb=progress_cb, abort_check=abort_check
        ).to_json_dict(),
        judge=judge_scan_result,
        render=render_report,
        save=lambda html_text: reports.save_report(html_text, reports_dir=reports_dir),
        prune=lambda: reports.prune_reports(reports_dir=reports_dir),
        open=reports.open_report,
    )


def _elevated_deps(reports_dir: str | None = None) -> AuditDeps:
    """提权实例流水线装配（T4-01；与 default_deps 的差异即 R9 边界，逐环说明）：

    save=elevated.save_admin_report（admin- 前缀，S-3 文件级可区分）；
    prune=no-op（提权实例不淘汰普通报告——最小写入面）；
    open=no-op（R9：提权进程不执行任何外部程序——os.startfile 会启动浏览器）；
    judge 经 elevated.collect_evidence_readonly 只装配 winreg 只读证据源
    （Appx/进程/服务三源需 powershell 子进程，提权模式不采集并降级披露）。
    scan 与普通实例共用同一只读枚举器 scan_path（E-4：提权只为读原本无权读的目录）。
    """
    from disk_audit.engine.render import render_report
    from disk_audit.engine.report import judge_scan_result
    from disk_audit.scanner import scan_path

    return AuditDeps(
        scan=lambda path, progress_cb=None, abort_check=None: scan_path(
            path, progress_cb=progress_cb, abort_check=abort_check
        ).to_json_dict(),
        judge=lambda scan: judge_scan_result(
            scan, bundle=elevated.collect_evidence_readonly()
        ),
        render=render_report,
        save=lambda html_text: elevated.save_admin_report(html_text, reports_dir=reports_dir),
        prune=lambda: [],
        open=lambda report_path: None,
    )


def execute_audit(
    path: str,
    *,
    deps: "AuditDeps | None" = None,
    progress_cb: "Callable[[ProgressEvent], None] | None" = None,
    abort_check: "Callable[[], bool] | None" = None,
    on_report: "Callable[[dict], None] | None" = None,
) -> str | None:
    """一次完整体检流水线（M2 闸①：选范围 → 扫描 → 浏览器自动打开 = 3 步）。

    分段清晰（每环一步）：① scan 只读采集（透传 C8 进度回调与 C7 中止谓词）
    → ② judge 六层判定 →（on_report：judge 输出的 report-v1 dict 原样透传，
    T4-07 完成态建议动作区的数据源；在 render/save 前回调，缺省不回调）
    → ③ render 离线 HTML → ④ save 落盘（U-2 唯一写入位）
    → ⑤ prune 淘汰保留 12 份 → ⑥ open 默认浏览器打开（只读）。
    完整路径返回报告绝对路径；环节异常向上抛出，由调用方统一呈现失败态。
    中止/异常路径（X-2：scan 结果置 incomplete=True）：短路返回 None，不
    judge/render/save/open——C7 不产生半成品结论，完整报告的落盘+打开仍走
    本函数完成路径（T3-05 定夺：中止路径不落盘报告、不开浏览器，部分结果仅
    在内存中保留，UI 呈现"不完整报告"态并可重新发起）。
    中止信号 = abort_check 返回 True（协作式停止标志），产品侧任何路径不得
    抛真 KeyboardInterrupt（T2-05③ 定夺，见模块 docstring）。
    """
    pipeline = deps if deps is not None else default_deps()
    scan_result = pipeline.scan(path, progress_cb=progress_cb, abort_check=abort_check)
    if scan_result.get("incomplete") is True:  # X-2：中止/异常统一"不完整"出口
        return None
    report = pipeline.judge(scan_result)
    if on_report is not None:
        on_report(report)
    html_text = pipeline.render(report)
    report_path = pipeline.save(html_text)
    pipeline.prune()
    pipeline.open(report_path)
    return report_path


def default_action_deps() -> "ActionDeps":
    """真实装配（T4-07/F4）：三能力绑定 disk_audit.system_actions（B3 公开接口）。

    延迟 import：launcher 模块加载不拖入 ctypes/B3 栈（T3-04 延迟导入模式延续）；
    B3 自带 executor/writer 注入点（验收①参数断言打到 B3 白名单出口）。
    """
    from disk_audit import system_actions

    return ActionDeps(
        copy_path=system_actions.copy_to_clipboard,
        locate=system_actions.locate_in_explorer,
        open_settings=system_actions.open_apps_settings,
    )


def action_button_label(action: str) -> str:
    """动作按钮文案：5.3 编号 + 固定动作标签（texts.ACTION_LABELS 单一措辞源）。"""
    return f"{action} {texts.ACTION_LABELS.get(action, action)}"


def select_operable_candidates(report: dict) -> list[dict]:
    """纯函数（F4/A5 语义）：从 report-v1 dict 筛选可执行建议动作的候选。

    可操作 = 置信度 ∈ {高, 中} 且 suggested_action ∈ {A1, A2, A3}：
    - 受保护/低置信固定 A5（方案 5.3）→ 永不进入可操作列表（卡面硬约束：
      "受保护/低置信项不得出现 A1~A3 入口"）；
    - 建议动作已是 A5 的高/中候选（在用软件等，judge 打标口径）同样不进入——
      报告对它们展示"无建议"，UI 不得自相矛盾地提供动作入口（R10 一致性；
      本口径是对卡面"仅高/中可操作"的收窄而非放宽）；
    - 防御性输入（缺键/非对象元素）→ 空列表，不抛异常。
    A4（查看证据链）为报告内展开，不属于本筛选（无外部调用，F2 details 原生）。
    """
    candidates = report.get("candidates") if isinstance(report, dict) else None
    if not isinstance(candidates, list):
        return []
    operable: list[dict] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("confidence") not in OPERABLE_CONFIDENCES:
            continue
        if candidate.get("suggested_action") not in OPERABLE_ACTIONS:
            continue
        operable.append(candidate)
    return operable


def run_suggested_action(action: str, path: str, *, deps: "ActionDeps | None" = None) -> str:
    """执行一个建议动作（A1/A2/A3），返回状态栏文案（E-5 风格）。

    仅接受 OPERABLE_ACTIONS 三个动作键，其余一律不触达任何系统出口、仅返回
    披露文案；A1/A2/A3 经 ActionDeps（默认 B3 白名单）执行。B3 的越权拒绝
    （SystemActionRejected）与失败（OSError 等）在本层捕获并转为状态栏文案，
    不向 UI 抛异常、不弹错误对话框（E-5：非阻塞披露，沿 G2 状态栏先例）。
    """
    from disk_audit import system_actions  # 延迟导入：异常类型与白名单出口同源

    pipeline = deps if deps is not None else default_action_deps()
    try:
        if action == "A1":
            pipeline.copy_path(path)
            return F4_TEXTS["status_copied"].format(path=path)
        if action == "A2":
            pipeline.locate(path)
            return F4_TEXTS["status_located"].format(path=path)
        if action == "A3":
            pipeline.open_settings()
            return F4_TEXTS["status_settings_opened"]
    except system_actions.SystemActionRejected as exc:  # U-4 越权拒绝：披露白名单边界
        return str(exc)
    except Exception as exc:  # 剪贴板失败（OSError）等：状态栏披露，不弹错误框
        return F4_TEXTS["status_action_failed"].format(reason=exc)
    return F4_TEXTS["status_unknown_action"].format(action=action or "（空）")


def run_audit_async(
    path: str,
    *,
    deps: "AuditDeps | None" = None,
    stop: threading.Event,
    after: Callable[[Callable[[], None]], None],
    on_progress: "Callable[[ProgressEvent], None]",
    on_complete: Callable[[str | None], None],
    on_error: Callable[[Exception], None],
    on_report: "Callable[[dict], None] | None" = None,
) -> threading.Thread:
    """把体检流水线搬入后台 daemon 线程执行（G2/T3-05：UI 线程零阻塞）。

    线程模型：scan/judge/render/save/prune/open 全部在返回的工作线程内执行；
    所有 UI 变更（进度/报告/完成/失败）一律经 ``after`` 派发主线程执行（真实
    运行传 ``root.after`` 的 0 延迟包装）——工作线程内不触碰任何 UI 状态。
    C8 进度事件的节流已由 scanner 侧保证（>=500ms 或 2 万条目双阈值），本函数
    只转发。on_report（T4-07：judge 输出的 report dict 透传给完成态建议动作区）
    同样经 after 派发主线程执行。中止 = 调用方对 ``stop`` 置位（协作式停止标志，
    透传为 scan 的 abort_check），任何路径不得抛真 KeyboardInterrupt（T2-05③
    定夺：产品侧同测试侧禁抛真 KI）。返回工作线程对象（daemon：窗口销毁后不
    悬挂进程）。

    参数：
        stop: 停止标志；置位后 scanner 在下一目录展开前经 abort_check 退出（X-2）。
        after: 主线程调度器（主循环回调注入），签名 after(callback) -> object。
        on_progress: 主线程执行的进度更新（ProgressEvent 三字段，E-1）。
        on_complete: 主线程执行的完成处理；参数为报告路径，None = 不完整（X-2）。
        on_error: 主线程执行的失败处理（scan/judge 等环节异常）。
        on_report: 主线程执行的报告透传（report-v1 dict，T4-07；缺省不透传）。
    """

    def _dispatch(callback: Callable[[], None]) -> None:
        """派发兜底：根窗口销毁后 after 失败仅静默收尾（daemon 线程退出场景）。"""
        try:
            after(callback)
        except Exception:
            pass  # 窗口已销毁时无 UI 可更新，线程随之结束，不掩盖扫描本身的结果

    def worker() -> None:
        try:
            report_cb = (
                (lambda report: _dispatch(lambda: on_report(report)))
                if on_report is not None
                else None
            )
            report_path = execute_audit(
                path,
                deps=deps,
                progress_cb=lambda event: _dispatch(lambda: on_progress(event)),
                abort_check=stop.is_set,
                on_report=report_cb,
            )
        except Exception as exc:  # 环节失败统一出口：主线程呈现失败态，程序不中断
            failure = exc  # except 块结束时解释器删除 exc，先绑定再进派发闭包
            _dispatch(lambda: on_error(failure))
            return
        _dispatch(lambda: on_complete(report_path))

    thread = threading.Thread(target=worker, name="diskaudit-audit", daemon=True)
    thread.start()
    return thread


# ---------- T4-01（待办 H1）：以管理员身份重扫 · 宿主侧发起 ----------

# 【防重生防线 1】自重启调用单点化：全仓库 ShellExecuteW/WinExec/os.system/os.popen/
# subprocess/os.startfile 仅允许出现在 _shell_execute_runas 这一处（ctypes
# ShellExecuteW；tests/test_elevated.py AST 断言全仓库唯一 + 提权分支零自启动）。
# 【U-3】runas 发起只能由用户点击回调（_on_admin_rescan）经 request_admin_rescan
# → _launch_elevated_self 抵达本函数，调用点唯一、无重试/轮询/自动再触发路径
# （AST 断言固化）。取消（ERROR_CANCELLED）与发起失败的 UX 归 T4-02/T4-03（E-5/X-4
# 接口位），本卡不弹框、不重试。
def _shell_execute_runas(lp_file: str, lp_verb: str, lp_parameters: str) -> int:
    """真实发起（全仓库唯一 ShellExecuteW 出口；仅由点击回调链抵达）。"""
    result = ctypes.windll.shell32.ShellExecuteW(
        None, lp_verb, lp_file, lp_parameters, None, elevated.SW_SHOWNORMAL
    )
    return int(result)


def _launch_elevated_self(
    *,
    shell_execute: "elevated.ShellExecute | None" = None,
    executable: str | None = None,
    script: str | None = None,
) -> int:
    """构造"重启自身"命令并发起 runas（shell_execute 可注入供单测断言参数）。"""
    lp_file, lp_parameters = elevated.build_rescan_command(
        executable=executable, script=script
    )
    if shell_execute is not None:  # 测试注入替身：不触达真实 ShellExecuteW
        return shell_execute(lp_file, "runas", lp_parameters)
    return _shell_execute_runas(lp_file, "runas", lp_parameters)


def request_admin_rescan(
    scope: str,
    *,
    tmp_dir: str | None = None,
    shell_execute: "elevated.ShellExecute | None" = None,
    executable: str | None = None,
    script: str | None = None,
    now: datetime | None = None,
) -> int:
    """宿主侧点击处理（纯逻辑，无 Tk；U-3：仅由 _on_admin_rescan 点击回调调用）。

    顺序：写 tmp\\spec.json（U-2 合规位，含范围/时间戳/唯一请求 ID）→ runas
    重启自身。返回 ShellExecuteW 返回码：>32 已发起；ERROR_CANCELLED 取消
    （E-5，T4-02 接口位）；其余发起失败（X-4，T4-03 接口位）——原样透传，
    本卡不做取消/失败的 UX，不弹任何框、不重试。
    """
    elevated.write_rescan_request(scope, tmp_dir=tmp_dir, now=now)
    return _launch_elevated_self(
        shell_execute=shell_execute, executable=executable, script=script
    )


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

    T3-05（G2）接线进度与中止：体检流水线经 run_audit_async 在后台线程执行，
    进度（C8 回调，E-1 三字段）经 after 派发主线程刷新；"中止体检"置协作式
    停止标志（abort_check → X-2），中止后呈现"不完整报告"横幅并可重新发起
    （每次"开始体检"新建停止标志/新线程/进度归零，无状态残留）。
    U-1：点击"开始体检"即用户显式选择，此前不读取所选文件系统路径。
    T4-01（H1/E-4）：范围区新增"以管理员身份重扫"入口——U-3 全程序唯一提权
    发起路径 = 本区按钮单击回调 _on_admin_rescan（写 spec.json → runas 重启
    自身，无重试/轮询；防重生设计见 disk_audit/elevated.py）。
    """
    import tkinter as tk
    from tkinter import filedialog, ttk

    root.title(LAUNCHER_TEXTS["window_title"])
    root.geometry("720x820")
    root.minsize(640, 760)

    status_var = tk.StringVar(value="")
    scope_var = tk.StringVar(value="")
    custom_var = tk.StringVar(value="")
    progress_var = tk.StringVar(value="")
    current_path_var = tk.StringVar(value="")
    banner_var = tk.StringVar(value="")

    build_label = tk.Label(
        root,
        text=LAUNCHER_TEXTS["build_status_ok"].format(build=build, min_build=MIN_BUILD),
        anchor="w",
    )
    build_label.pack(fill="x", padx=12, pady=(12, 4))

    scope_frame = tk.LabelFrame(root, text=LAUNCHER_TEXTS["scope_group"])
    scope_frame.pack(fill="x", padx=12, pady=4)
    scope_radios: list[tk.Radiobutton] = []
    for row in presets:
        radio = tk.Radiobutton(
            scope_frame, text=row.text, value=row.path, variable=scope_var, anchor="w"
        )
        radio.pack(fill="x")
        scope_radios.append(radio)

    custom_row = tk.Frame(scope_frame)
    custom_row.pack(fill="x")
    custom_radio = tk.Radiobutton(
        custom_row, text=LAUNCHER_TEXTS["custom_option"], value=CUSTOM_SENTINEL,
        variable=scope_var,
    )
    custom_radio.pack(side="left")
    scope_radios.append(custom_radio)
    custom_entry = tk.Entry(custom_row, textvariable=custom_var, state="disabled")
    custom_entry.pack(side="left", fill="x", expand=True, padx=6)
    browse_button = tk.Button(
        custom_row, text=LAUNCHER_TEXTS["custom_browse"], state="disabled",
        command=lambda: _browse_folder(root, custom_var, scope_var, filedialog),
    )
    browse_button.pack(side="left")

    # E-4/T4-01：以管理员身份重扫入口（U-3：唯一提权发起路径 = 本按钮单击回调）
    admin_rescan_button = tk.Button(
        scope_frame, text=H1_TEXTS["admin_rescan_button"],
        command=lambda: _on_admin_rescan(),
    )
    admin_rescan_button.pack(fill="x", pady=(6, 0))

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
        radio = tk.Radiobutton(
            drives_frame, text=text, value=entry.letter + "\\",
            variable=scope_var, state=state, anchor="w",
        )
        radio.pack(fill="x")
        scope_radios.append(radio)

    progress_frame = tk.LabelFrame(root, text=G2_TEXTS["progress_group"])
    progress_frame.pack(fill="x", padx=12, pady=4)
    progressbar = ttk.Progressbar(progress_frame, mode="indeterminate")
    progressbar.pack(fill="x", padx=8, pady=(6, 2))
    tk.Label(progress_frame, textvariable=progress_var, anchor="w").pack(fill="x")
    tk.Label(
        progress_frame, textvariable=current_path_var, anchor="w",
        wraplength=660, justify="left",
    ).pack(fill="x")
    banner_label = tk.Label(
        root, textvariable=banner_var, anchor="w", wraplength=660, justify="left",
        bg="#FFF3CD", fg="#664D03", padx=8, pady=4,
    )

    # F4 建议动作区（T4-07）：完成态填充可操作候选（select_operable_candidates
    # 口径：高/中置信且建议 A1~A3；受保护/低置信/建议 A5 的候选永不出现——A5 语义，
    # 无任何入口）。动作经 run_suggested_action → ActionDeps（默认 B3 白名单）
    # 执行；拒绝/失败仅状态栏披露（E-5，不弹错误框）。A4 = 指向报告"证据链"区的
    # 文字指引（报告内 details 原生展开）；A5 = 无任何入口。
    actions_frame = tk.LabelFrame(root, text=F4_TEXTS["actions_group"])
    actions_frame.pack(fill="x", padx=12, pady=4)
    actions_note_var = tk.StringVar(value=F4_TEXTS["candidate_none"])
    tk.Label(
        actions_frame, textvariable=actions_note_var, anchor="w",
        wraplength=660, justify="left",
    ).pack(fill="x")
    cand_var = tk.StringVar(value="")
    cand_box = ttk.Combobox(actions_frame, textvariable=cand_var, state="readonly")
    cand_box.pack(fill="x", padx=8, pady=(4, 2))
    actions_row = tk.Frame(actions_frame)
    actions_row.pack(fill="x", padx=8)
    action_buttons: dict[str, tk.Button] = {}
    for action_key in ACTION_KEYS:
        button = tk.Button(
            actions_row,
            text=action_button_label(action_key),
            command=lambda key=action_key: _on_action(key),
            state="disabled",
            width=18,
        )
        button.pack(side="left", padx=(0, 8))
        action_buttons[action_key] = button
    tk.Label(
        actions_frame, text=F4_TEXTS["a4_hint"], anchor="w",
        wraplength=660, justify="left", fg="#6b7280",
    ).pack(fill="x", padx=8, pady=(2, 6))
    operable_paths: list[str] = []

    def _set_actions_state(enabled: bool) -> None:
        for button in action_buttons.values():
            button.config(state="normal" if enabled else "disabled")

    def _reset_actions() -> None:
        """新一次体检发起时清空动作区（上一次的候选/选中态零残留，对齐 G2 会话语义）。"""
        operable_paths.clear()
        cand_box.config(values=())
        cand_var.set("")
        actions_note_var.set(F4_TEXTS["candidate_none"])
        _set_actions_state(False)

    def _populate_actions(report: dict) -> None:
        """完成态（主线程）：按 A5 语义填充可操作候选，默认选中第一条。"""
        operable = select_operable_candidates(report)
        operable_paths.clear()
        if not operable:
            cand_box.config(values=())
            cand_var.set("")
            actions_note_var.set(F4_TEXTS["no_operable"])
            _set_actions_state(False)
            return
        items: list[str] = []
        for candidate in operable:
            path = str(candidate.get("path", ""))
            operable_paths.append(path)
            items.append(F4_TEXTS["candidate_item_fmt"].format(
                path=path,
                confidence=candidate.get("confidence", ""),
                source=candidate.get("verdict_source", ""),
            ))
        cand_box.config(values=items)
        cand_box.current(0)
        actions_note_var.set(F4_TEXTS["actions_note"])
        _set_actions_state(True)

    def _on_action(action: str) -> None:
        index = cand_box.current()
        if index < 0 or index >= len(operable_paths):
            status_var.set(F4_TEXTS["no_candidate_selected"])
            return
        status_var.set(run_suggested_action(action, operable_paths[index]))

    bottom = tk.Frame(root)
    bottom.pack(fill="x", padx=12, pady=(4, 12))
    start_button = tk.Button(bottom, text=LAUNCHER_TEXTS["start_button"], command=lambda: _on_start())
    start_button.pack(side="left")
    abort_button = tk.Button(
        bottom, text=G2_TEXTS["abort_button"], command=lambda: _on_abort(), state="disabled"
    )
    abort_button.pack(side="left", padx=(8, 0))
    tk.Label(bottom, textvariable=status_var, anchor="w").pack(fill="x", pady=(6, 0))

    # 一次体检的会话状态：每次"开始体检"整体替换（新停止标志/新线程）——
    # 重新发起扫描天然无跨次残留（验收③）。
    session: dict = {"stop": None}

    def _set_audit_state(running: bool) -> None:
        """扫描期间锁定范围选择与开始按钮，启用中止；结束后还原（含自定义联动）。"""
        for radio in scope_radios:
            radio.config(state="disabled" if running else "normal")
        start_button.config(state="disabled" if running else "normal")
        admin_rescan_button.config(state="disabled" if running else "normal")
        abort_button.config(state="normal" if running else "disabled")
        if running:
            custom_entry.config(state="disabled")
            browse_button.config(state="disabled")
        else:
            _sync_custom_state()

    def _resolve_selected_scope() -> "str | None":
        """当前所选范围（U-1：未选择/不存在时置状态栏并返回 None，不读取任何路径）。"""
        selected = scope_var.get()
        if selected == CUSTOM_SENTINEL:
            path = custom_var.get().strip()
            if not path:
                status_var.set(LAUNCHER_TEXTS["status_no_selection"])
                return None
            if not os.path.isdir(path):
                status_var.set(LAUNCHER_TEXTS["status_missing_folder"])
                return None
            return path
        if not selected:
            status_var.set(LAUNCHER_TEXTS["status_no_selection"])
            return None
        return selected

    def _on_start() -> None:
        path = _resolve_selected_scope()
        if path is None:
            return
        # G2 接线（T3-05）：全新会话 → 后台线程执行体检（UI 线程零阻塞）；
        # 进度经 after 派发主线程刷新；中止 = 置停止标志（C7 统一出口）。
        stop = threading.Event()
        session["stop"] = stop
        progress_var.set(G2_TEXTS["progress_status"].format(entries=0, seconds=0))
        current_path_var.set("")
        banner_var.set("")
        banner_label.pack_forget()
        status_var.set(G3_TEXTS["status_scanning"].format(path=path))
        _set_audit_state(running=True)
        progressbar.start(50)
        _reset_actions()  # F4：新会话清空上一次的可操作候选（无跨次残留）

        def on_progress(event: "ProgressEvent") -> None:
            progress_var.set(
                G2_TEXTS["progress_status"].format(
                    entries=event.entries, seconds=int(event.elapsed)
                )
            )
            current_path_var.set(G2_TEXTS["progress_current_path"].format(path=event.path))

        def on_report(report: dict) -> None:
            # 主线程执行（run_audit_async 经 after 派发）：judge 输出到达即填充
            # 建议动作区（先于 on_complete 的状态栏完成文案，after 队列 FIFO）。
            _populate_actions(report)

        def on_complete(report_path: "str | None") -> None:
            progressbar.stop()
            _set_audit_state(running=False)
            if report_path is None:  # X-2：中止/异常 → 不完整报告态（未落盘、未开浏览器）
                banner_var.set(G2_TEXTS["incomplete_banner"])
                banner_label.pack(fill="x", padx=12, pady=(0, 4), before=progress_frame)
                status_var.set(G2_TEXTS["status_incomplete"])
            else:
                status_var.set(G3_TEXTS["status_report_opened"].format(path=report_path))

        def on_error(exc: Exception) -> None:
            progressbar.stop()
            _set_audit_state(running=False)
            status_var.set(G3_TEXTS["status_audit_failed"].format(reason=exc))

        session["thread"] = run_audit_async(
            path,
            deps=None,
            stop=stop,
            after=lambda cb: root.after(0, cb),
            on_progress=on_progress,
            on_report=on_report,
            on_complete=on_complete,
            on_error=on_error,
        )

    def _on_abort() -> None:
        stop = session.get("stop")
        if stop is None or stop.is_set():
            return
        # 协作式中止（T3-05 定夺）：只置停止标志 → abort_check 返回 True →
        # scanner X-2 统一"不完整"出口；产品侧任何路径不抛真 KeyboardInterrupt。
        stop.set()
        abort_button.config(state="disabled")
        status_var.set(G2_TEXTS["status_aborting"])

    def _on_admin_rescan() -> None:
        """以管理员身份重扫（E-4/T4-01；U-3：全程序唯一提权发起路径 = 本点击回调）。

        单击 → 写 tmp\\spec.json（范围+时间戳+唯一请求 ID，U-2 合规位）→
        ShellExecuteW runas 重启自身（单点 _shell_execute_runas，AST 断言调用点
        唯一、无重试/轮询/自动再触发——防重生设计，见 disk_audit/elevated.py）。
        ShellExecuteW 返回码语义：>32 已发起 → 状态栏提示；ERROR_CANCELLED=UAC
        取消（E-5，T4-02 接口位）；其余=发起失败（X-4，T4-03 接口位）——本卡
        只留接口位：不弹框、不重试。
        """
        path = _resolve_selected_scope()
        if path is None:
            return
        result_code = request_admin_rescan(path)
        if result_code > 32:  # Win32：>32 = 已发起
            status_var.set(H1_TEXTS["status_admin_launched"])
        # 其余返回码（含 ERROR_CANCELLED=1223 取消）→ E-5/H2、X-4/T4-03 口径，
        # 本卡不实现取消/失败 UX（不弹框、不重试、不轮询）。


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


def _cmd_elevated_rescan() -> int:
    """--elevated-rescan 提权实例分支（任务卡 T4-01；R9/防重生约束的 AST 断言锚点）。

    消费 tmp\\spec.json（一次性：原子认领即焚，重复/陈旧/无请求一律
    EXIT_BAD_REQUEST 拒绝退出）→ 复用 execute_audit 流水线（save=admin- 前缀、
    prune/open 双 no-op、judge 只装配 winreg 只读证据源）→ 写
    admin_rescan_done.json → 退出码三态 0/4/5。
    本函数及其调用链 AST 断言零自启动、零网络、零 UI（tests/test_elevated.py）。
    """
    return elevated.run_elevated_rescan(deps=_elevated_deps(), audit=execute_audit)


def main(argv: list[str] | None = None) -> int:
    """独立入口（规范 §1：启动器在独立模块/入口）。

    --elevated-rescan：提权实例分支（Q6 重启自身 = 同一入口；无 UI、零自启动、
    零网络）；默认：范围选择界面（U-1 范围经界面选择）。
    """
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(prog="DiskAudit", description=LAUNCHER_TEXTS["window_title"])
    parser.add_argument(
        elevated.ELEVATED_FLAG,
        action="store_true",
        help=H1_TEXTS["cli_help_elevated"],
    )
    args = parser.parse_args(argv)
    if args.elevated_rescan:  # 提权实例分支（防重生：零自启动，AST 断言锁定）
        return _cmd_elevated_rescan()
    return run()


if __name__ == "__main__":
    sys.exit(main())
