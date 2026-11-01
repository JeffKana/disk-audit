r"""T3-04（待办 G1）范围选择界面纯逻辑测试。

依据：方案 P4（预设四目录 %APPDATA% / %LOCALAPPDATA% / %PROGRAMDATA% / C:\Program Files）、
P5（build 22621 启动检测，不足拒绝）、P6（仅固定本地盘，其余置灰+原因）、
开发规范 §1（引擎/UI 解耦：disk_audit 包内不得 import tkinter；文案集中资源处）、§3（测试规范）。

测试只覆盖纯逻辑（版本闸、盘型置灰、预设模型、文案、耦合边界），
不创建 Tk 实例、不起 mainloop（CI 稳定性）；UI 真启动由本机实测截图留档（验收③）。
"""
from __future__ import annotations

import ast
import dataclasses
import sys
import threading
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import launcher  # noqa: E402
from disk_audit.engine import texts  # noqa: E402
from disk_audit.scanner import ProgressEvent, scan_path  # noqa: E402


# ---------- 验收①：版本不足拒绝路径（P5，注入假版本） ----------


@pytest.mark.parametrize(
    "build,expect",
    [
        (10240, False),  # Win10 1507
        (22000, False),  # Win11 21H2（低于 22621）
        (22620, False),  # 边界下侧
        (22621, True),  # Win11 22H2（P5 最低要求）
        (26200, True),  # 本机实测 build
    ],
)
def test_is_build_supported_boundaries(build: int, expect: bool):
    assert launcher.is_build_supported(build) is expect


def test_run_rejects_and_never_opens_window_when_build_below_minimum():
    """注入假版本 22000：拒绝路径必须通知用户、不创建任何窗口、返回非零退出码。"""
    notified: list[int] = []
    window_calls: list[tuple] = []
    rc = launcher.run(
        build_probe=lambda: 22000,
        notify_unsupported=notified.append,
        window_factory=lambda *args: window_calls.append(args),
    )
    assert rc == launcher.EXIT_UNSUPPORTED
    assert notified == [22000]
    assert window_calls == []


def test_run_supported_path_builds_window_once_with_models():
    """满足版本时：以注入的盘型/预设模型建窗一次，build 数字透传（版本状态标签用）。"""
    window_args: list[tuple] = []
    rc = launcher.run(
        build_probe=lambda: 26200,
        drive_probe=lambda: {"C:": launcher.DRIVE_FIXED},
        notify_unsupported=lambda build: pytest.fail("满足版本时不应触发拒绝通知"),
        window_factory=lambda entries, presets, build: window_args.append(
            (entries, presets, build)
        ),
    )
    assert rc == launcher.EXIT_OK
    assert len(window_args) == 1
    entries, presets, build = window_args[0]
    assert build == 26200
    assert entries[0].letter == "C:" and entries[0].supported
    assert [row.key for row in presets] == [p.key for p in launcher.PRESET_DIRS]


def test_unsupported_build_text_contains_both_numbers():
    """拒绝提示文案必须同时给出当前 build 与最低要求（P5 口径，零假设：只说事实）。"""
    message = texts.LAUNCHER_TEXTS["build_unsupported"].format(build=22000, min_build=22621)
    assert "22000" in message and "22621" in message


# ---------- 验收②：盘型置灰逻辑（P6，驱动类型注入） ----------


@pytest.mark.parametrize(
    "drive_type,reason_key",
    [
        (0, "drive_reason_unknown"),  # DRIVE_UNKNOWN
        (1, "drive_reason_unknown"),  # DRIVE_NO_ROOT_DIR
        (2, "drive_reason_removable"),  # DRIVE_REMOVABLE
        (4, "drive_reason_remote"),  # DRIVE_REMOTE
        (5, "drive_reason_cdrom"),  # DRIVE_CDROM
        (6, "drive_reason_ramdisk"),  # DRIVE_RAMDISK
    ],
)
def test_unsupported_drive_types_are_grayed_with_reason(drive_type: int, reason_key: str):
    entries = launcher.build_drive_entries({"X:": drive_type})
    assert len(entries) == 1
    entry = entries[0]
    assert entry.supported is False
    assert entry.reason == texts.LAUNCHER_TEXTS[reason_key]
    assert entry.reason  # 原因文案非空（P6：置灰并说明原因）


def test_fixed_drive_is_selectable_without_reason():
    entries = launcher.build_drive_entries({"C:": launcher.DRIVE_FIXED})
    assert entries[0].supported is True
    assert entries[0].reason == ""


def test_drive_entries_keep_letters_sorted():
    entries = launcher.build_drive_entries({"Z:": 3, "A:": 2, "M:": 4})
    assert [entry.letter for entry in entries] == ["A:", "M:", "Z:"]


def test_every_unsupported_reason_states_fixed_only_policy():
    """P6 零假设口径：每条置灰原因都说明"仅支持固定本地盘"。"""
    blob = " ".join(texts.LAUNCHER_TEXTS[key] for key in launcher.DRIVE_REASON_KEYS.values())
    assert "固定本地盘" in blob


# ---------- P4：预设四目录模型 ----------


def test_preset_dirs_exactly_four_in_plan_order():
    """P4：预设四项，顺序与模板逐字对照方案定稿。"""
    assert [item.key for item in launcher.PRESET_DIRS] == [
        "appdata",
        "localappdata",
        "programdata",
        "program_files",
    ]
    assert [item.template for item in launcher.PRESET_DIRS] == [
        "%APPDATA%",
        "%LOCALAPPDATA%",
        "%PROGRAMDATA%",
        r"C:\Program Files",
    ]


def test_build_preset_rows_resolves_injected_env():
    env = {
        "APPDATA": r"C:\Users\demo\AppData\Roaming",
        "LOCALAPPDATA": r"C:\Users\demo\AppData\Local",
        "PROGRAMDATA": r"C:\ProgramData",
    }
    rows = launcher.build_preset_rows(env)
    assert [row.path for row in rows] == [
        r"C:\Users\demo\AppData\Roaming",
        r"C:\Users\demo\AppData\Local",
        r"C:\ProgramData",
        r"C:\Program Files",
    ]


def test_preset_row_text_contains_label_and_path():
    env = {"APPDATA": r"C:\Users\demo\AppData\Roaming"}
    rows = launcher.build_preset_rows(env)
    assert texts.LAUNCHER_TEXTS["preset_label_appdata"] in rows[0].text
    assert r"C:\Users\demo\AppData\Roaming" in rows[0].text


def test_expand_env_keeps_missing_var_literal():
    """环境变量缺失时保留原文（交由开始时的存在性校验兜底，不崩溃）。"""
    assert launcher.expand_preset_env("%APPDATA%\\sub", {}) == "%APPDATA%\\sub"


# ---------- 文案集中资源处（规范 §1；Q3 禁词同样适用于启动器文案） ----------


def test_launcher_texts_required_keys_exist():
    required = [
        "window_title",
        "build_status_ok",
        "build_unsupported_title",
        "build_unsupported",
        "scope_group",
        "preset_label_appdata",
        "preset_label_localappdata",
        "preset_label_programdata",
        "preset_label_programfiles",
        "custom_option",
        "custom_browse",
        "drives_group",
        "drive_fixed",
        "drive_reason_removable",
        "drive_reason_remote",
        "drive_reason_cdrom",
        "drive_reason_ramdisk",
        "drive_reason_unknown",
        "start_button",
        "status_no_selection",
        "status_selected",
        "status_missing_folder",
    ]
    missing = [key for key in required if key not in texts.LAUNCHER_TEXTS]
    assert missing == []


def test_launcher_texts_no_forbidden_terms():
    """Q3 禁"可回收"（禁用词约束对全部对外文案生效）。"""
    blob = "".join(texts.LAUNCHER_TEXTS.values())
    assert "可回收" not in blob


def test_preset_label_keys_cover_all_presets():
    for item in launcher.PRESET_DIRS:
        assert item.label_key in texts.LAUNCHER_TEXTS


# ---------- T3-06（待办 G3）：开始体检回调流水线（scan→judge→render→save→prune→open） ----------


def test_execute_audit_runs_pipeline_in_order_with_stubbed_stages():
    """全替身链路：六环按序执行、数据逐环传递、返回报告路径（M2 闸① ≤3 步的接缝）。

    T3-05（G2）异步化后 execute_audit 恒以 progress_cb / abort_check 关键字调用
    scan 环（注入接口即异步化改造边界），故替身签名随接线更新（语义不变）。
    """
    calls: list[tuple] = []
    deps = launcher.AuditDeps(
        scan=lambda p, progress_cb=None, abort_check=None: (
            calls.append(("scan", p)), {"root": p, "units": [], "skipped": {}})[1],
        judge=lambda scan: (
            calls.append(("judge", scan["root"])),
            {"schema_version": "1.0", "scan_root": scan["root"], "candidates": []},
        )[1],
        render=lambda report: (
            calls.append(("render", report["scan_root"])),
            "<html>" + report["scan_root"] + "</html>",
        )[1],
        save=lambda html: (calls.append(("save", html)), r"C:\reports\report-1.html")[1],
        prune=lambda: (calls.append(("prune", None)), [])[1],
        open=lambda path: calls.append(("open", path)),
    )
    got = launcher.execute_audit(r"C:\scope", deps=deps)
    assert got == r"C:\reports\report-1.html"
    assert [entry[0] for entry in calls] == ["scan", "judge", "render", "save", "prune", "open"]
    assert calls[0][1] == r"C:\scope"
    assert calls[1][1] == r"C:\scope"
    assert calls[2][1] == r"C:\scope"
    assert calls[3][1] == "<html>" + r"C:\scope" + "</html>"
    assert calls[5][1] == r"C:\reports\report-1.html"


def test_execute_audit_with_default_deps_writes_under_injected_dir(tmp_path):
    """默认装配：scan/judge/render/open 不实际执行（仅验证可调用），
    save/prune 绑定注入目录——真实落盘一次验证接线正确（路径根可注入）。"""
    deps = launcher.default_deps(reports_dir=str(tmp_path))
    path = deps.save("<html>wiring</html>")
    assert Path(path).parent == tmp_path
    assert Path(path).name.startswith("report-")
    assert deps.prune() == []


def test_default_deps_scan_and_judge_are_real_entrypoints():
    """默认装配绑定真实 scan/judge/render/open 入口（CI 不实际调用它们）。"""
    from disk_audit.engine.report import judge_scan_result
    from disk_audit.engine.render import render_report

    deps = launcher.default_deps()
    assert deps.judge is judge_scan_result
    assert deps.render is render_report


# ---------- 耦合边界（验收④：引擎零 UI 依赖；规范 §1：包内零 tkinter） ----------


def test_launcher_imports_engine_only_via_declared_interfaces():
    """UI → 引擎方向只允许经本卡声明的接口模块进入 disk_audit 包。

    T3-04 骨架期仅文案资源（texts）；T3-06（待办 G3）按任务卡接线
    scan/judge/render/save/open 六环，allowlist 相应扩至：
    scanner（scan 接口）、engine.report（judge）、engine.render（render）、
    reports（落盘/淘汰/打开）。守卫语义不变：不得 import 判定细节外的
    包内私有模块，且引擎侧零 tkinter 由 test_package_has_no_tkinter_import 钉死。
    """
    source = (_REPO_ROOT / "launcher.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.append(node.module)
    engine_imports = {name for name in imported if name.startswith("disk_audit")}
    assert engine_imports <= {
        "disk_audit",  # 包根（disk_audit.reports 的导入形式）
        "disk_audit.engine",
        "disk_audit.engine.report",
        "disk_audit.engine.render",
        "disk_audit.reports",
        "disk_audit.scanner",
    }


def test_package_has_no_tkinter_import():
    """规范 §1：disk_audit 包内任何模块不得 import tkinter（check_imports 白名单不禁
    标准库 tkinter，故在此以测试钉死引擎侧边界，守住 M1 验收④语义）。"""
    violations: list[str] = []
    for py in sorted((_REPO_ROOT / "disk_audit").rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".", 1)[0] == "tkinter":
                        violations.append(f"{py.name}:{node.lineno}")
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                if node.module.split(".", 1)[0] == "tkinter":
                    violations.append(f"{py.name}:{node.lineno}")
    assert violations == []


# ---------- T3-05（待办 G2）：进度与中止 UI（消费 C8 回调 + C7 统一中止出口） ----------
#
# 设计依据：中止 = UI 置 threading.Event 停止标志 → abort_check 返回 True →
# scanner X-2 统一"不完整"出口（产品侧同测试侧禁抛真 KeyboardInterrupt，T2-05③
# 定夺）；进度 = C8 回调经 after() 派发主线程（回调内不做渲染/IO）；体检流水线
# 搬入后台 daemon 线程（UI 线程零阻塞）；中止后呈现"不完整报告"态并可重新发起
# （全新停止标志/新线程/进度归零，无状态残留）；中止路径不落盘报告、不开浏览器。


def _stub_deps(calls: list[tuple], scan_result: dict | None = None) -> launcher.AuditDeps:
    """六环替身：scan 结果可注入（incomplete 语义由替身承载）；各环调用全记录，
    供"六环按序 / 未落盘未打开"断言。scan 替身签名 = G2 后的注入接口
    （execute_audit 恒以 progress_cb / abort_check 关键字透传）。"""

    def scan(path: str, progress_cb=None, abort_check=None):
        calls.append(("scan", path, progress_cb, abort_check))
        if scan_result is not None:
            return scan_result
        return {"root": path, "entries": 0, "skipped": {}, "units": []}

    return launcher.AuditDeps(
        scan=scan,
        judge=lambda s: (
            calls.append(("judge", s.get("root"))),
            {"schema_version": "1.0", "scan_root": s.get("root"), "candidates": []},
        )[1],
        render=lambda report: (calls.append(("render", report["scan_root"])), "<html></html>")[1],
        save=lambda html: (calls.append(("save", html)), r"C:\reports\report-2.html")[1],
        prune=lambda: (calls.append(("prune", None)), [])[1],
        open=lambda path: calls.append(("open", path)),
    )


def test_execute_audit_forwards_progress_and_abort_to_scan():
    """execute_audit 把进度回调与中止谓词原样透传给 scan 环（C8/C7 注入口）。"""
    calls: list[tuple] = []
    deps = _stub_deps(calls)
    progress_cb = lambda event: None  # noqa: E731
    stop = threading.Event()
    launcher.execute_audit(r"C:\scope", deps=deps, progress_cb=progress_cb, abort_check=stop.is_set)
    entry = calls[0]
    assert entry[0] == "scan" and entry[1] == r"C:\scope"
    assert entry[2] is progress_cb
    # abort_check 行为等价于停止标志（bound method 不比身份，比行为）
    assert entry[3]() is False
    stop.set()
    assert entry[3]() is True


def test_execute_audit_abort_path_returns_none_and_skips_render_save_open():
    """中止路径（X-2 incomplete）：返回 None，不 judge/render/save/prune/open
    （C7 不产生半成品结论——T3-05 定夺：中止路径不落盘报告、不开浏览器）。"""
    calls: list[tuple] = []
    deps = _stub_deps(
        calls, scan_result={"root": r"C:\scope", "incomplete": True, "units": [], "skipped": {}}
    )
    got = launcher.execute_audit(r"C:\scope", deps=deps, abort_check=lambda: True)
    assert got is None
    assert [c[0] for c in calls] == ["scan"]


def test_execute_audit_complete_path_full_pipeline_with_abort_params():
    """完整路径不受中止参数影响：六环按序、返回报告路径（G3 既有语义不回退）。"""
    calls: list[tuple] = []
    deps = _stub_deps(calls)
    got = launcher.execute_audit(
        r"C:\scope", deps=deps, progress_cb=lambda event: None, abort_check=lambda: False
    )
    assert got == r"C:\reports\report-2.html"
    assert [c[0] for c in calls] == ["scan", "judge", "render", "save", "prune", "open"]


def test_run_audit_async_runs_scan_on_background_daemon_thread():
    """验收④架构断言：扫描在工作线程执行（非 UI 线程），线程为 daemon
    （窗口关闭不悬挂）。工作线程阻塞期间断言，规避线程 ident 复用。"""
    main_ident = threading.get_ident()
    calls: list[tuple] = []
    scan_seen = threading.Event()
    release = threading.Event()
    deps = _stub_deps(calls)

    def scan(path: str, progress_cb=None, abort_check=None):
        calls.append(("scan_ident", threading.get_ident()))
        scan_seen.set()
        release.wait(timeout=5)  # 阻塞工作线程直到断言完成
        return {"root": path, "entries": 0, "skipped": {}, "units": []}

    deps = dataclasses.replace(deps, scan=scan)
    thread = launcher.run_audit_async(
        r"C:\scope",
        deps=deps,
        stop=threading.Event(),
        after=lambda cb: cb(),
        on_progress=lambda event: None,
        on_complete=lambda p: None,
        on_error=lambda e: pytest.fail("不应进入错误出口"),
    )
    assert isinstance(thread, threading.Thread)
    assert thread.daemon is True
    assert scan_seen.wait(timeout=5)
    assert calls[0][1] != main_ident  # 扫描不在调用方（UI）线程
    assert thread.is_alive()
    release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_run_audit_async_progress_forwarded_via_after_not_from_worker():
    """验收④架构断言：进度事件只经 after 派发主线程执行——工作线程内 on_progress
    不得被直接调用（C8 回调侧仅转发，渲染/IO 全在主线程侧）。"""
    events_sent = [
        ProgressEvent(entries=10, path=r"C:\a", elapsed=0.5),
        ProgressEvent(entries=20, path=r"C:\b", elapsed=1.0),
    ]
    after_cbs: list = []
    ui_events: list[ProgressEvent] = []
    ui_idents: list[int] = []
    done = threading.Event()
    deps = _stub_deps([])

    def scan(path: str, progress_cb=None, abort_check=None):
        for event in events_sent:
            progress_cb(event)
        return {"root": path, "entries": 20, "skipped": {}, "units": []}

    deps = dataclasses.replace(deps, scan=scan)

    thread = launcher.run_audit_async(
        r"C:\scope",
        deps=deps,
        stop=threading.Event(),
        after=after_cbs.append,
        on_progress=lambda event: (
            ui_idents.append(threading.get_ident()),
            ui_events.append(event),
        ),
        on_complete=lambda p: (ui_idents.append(threading.get_ident()), done.set()),
        on_error=lambda e: pytest.fail("不应进入错误出口"),
    )
    thread.join(timeout=5)  # 工作线程收尾 = 全部派发已入队（after 收集器不执行回调）
    assert not thread.is_alive()
    # 工作线程只把回调排入 after 队列（2 进度 + 1 完成），未直接执行任何 UI 更新
    assert len(after_cbs) == len(events_sent) + 1
    assert ui_events == [] and not done.is_set()
    for cb in list(after_cbs):  # 主线程（测试线程）统一消化 after 队列
        cb()
    assert done.is_set()
    assert [e.entries for e in ui_events] == [10, 20]
    assert set(ui_idents) == {threading.get_ident()}  # 全部 UI 更新发生在主线程侧


def test_run_audit_async_abort_yields_incomplete_without_save_or_open():
    """验收①逻辑断言：置停止标志 → scan 依 abort_check 返回 incomplete →
    on_complete(None)（不完整态），save/open 零调用（不落盘不开浏览器）。"""
    calls: list[tuple] = []
    deps = _stub_deps(
        calls, scan_result={"root": r"C:\scope", "incomplete": True, "units": [], "skipped": {}}
    )
    stop = threading.Event()
    after_cbs: list = []
    results: list = []
    thread = launcher.run_audit_async(
        r"C:\scope",
        deps=deps,
        stop=stop,
        after=after_cbs.append,
        on_progress=lambda event: None,
        on_complete=lambda p: results.append(p),
        on_error=lambda e: pytest.fail("中止不是错误出口"),
    )
    stop.set()  # 协作式中止：只置标志，任何路径不抛真 KeyboardInterrupt（T2-05③ 定夺）
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert calls[0][3]() is True  # scan 收到的 abort_check 即停止标志（C7 注入语义）
    assert len(after_cbs) == 1  # 仅完成派发，无错误出口
    for cb in list(after_cbs):
        cb()
    assert results == [None]  # None = 不完整报告态（UI 呈现依据）
    assert [c[0] for c in calls] == ["scan"]


def test_rescan_after_abort_uses_fresh_state_and_completes():
    """验收③逻辑断言：中止后重新发起 = 全新停止标志（未置位、非旧对象）+ 新线程，
    完整路径六环走完、报告产出——无状态残留。"""
    # 第一次：中止
    calls1: list[tuple] = []
    deps1 = _stub_deps(
        calls1, scan_result={"root": r"C:\scope", "incomplete": True, "units": [], "skipped": {}}
    )
    stop1 = threading.Event()
    done1 = threading.Event()
    r1: list = []
    launcher.run_audit_async(
        r"C:\scope", deps=deps1, stop=stop1, after=lambda cb: cb(),
        on_progress=lambda event: None,
        on_complete=lambda p: (r1.append(p), done1.set()),
        on_error=lambda e: pytest.fail("不应进入错误出口"),
    )
    stop1.set()
    assert done1.wait(timeout=5)
    assert r1 == [None]
    assert [c[0] for c in calls1] == ["scan"]
    # 第二次：全新状态，完整完成
    calls2: list[tuple] = []
    deps2 = _stub_deps(calls2)
    stop2 = threading.Event()
    assert stop2 is not stop1 and not stop2.is_set()
    done2 = threading.Event()
    r2: list = []
    launcher.run_audit_async(
        r"C:\scope", deps=deps2, stop=stop2, after=lambda cb: cb(),
        on_progress=lambda event: None,
        on_complete=lambda p: (r2.append(p), done2.set()),
        on_error=lambda e: pytest.fail("不应进入错误出口"),
    )
    assert done2.wait(timeout=5)
    assert r2 == [r"C:\reports\report-2.html"]
    assert [c[0] for c in calls2] == ["scan", "judge", "render", "save", "prune", "open"]


def test_run_audit_async_scan_exception_goes_to_error_exit_without_save_open():
    """scan 环节异常 → on_error 出口（UI 呈现失败态），save/open 零调用。"""
    calls: list[tuple] = []
    deps = _stub_deps(calls)

    def boom(path: str, progress_cb=None, abort_check=None):
        calls.append(("scan", path, progress_cb, abort_check))
        raise RuntimeError("扫描替身失败")

    deps = dataclasses.replace(deps, scan=boom)
    after_cbs: list = []
    errors: list = []
    thread = launcher.run_audit_async(
        r"C:\scope", deps=deps, stop=threading.Event(), after=after_cbs.append,
        on_progress=lambda event: None,
        on_complete=lambda p: pytest.fail("异常不应走完成出口"),
        on_error=errors.append,
    )
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(after_cbs) == 1  # 仅错误派发
    for cb in list(after_cbs):
        cb()
    assert len(errors) == 1 and isinstance(errors[0], RuntimeError)
    assert [c[0] for c in calls] == ["scan"]


def test_real_scanner_abort_via_wiring_writes_no_report(tmp_path):
    """接缝集成（真实 scanner + 真实 X-2 出口）：abort_check 立即为真 →
    execute_audit 返回 None，报告目录零文件、浏览器零打开。"""
    root = tmp_path / "tree"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "a.txt").write_text("x", encoding="utf-8")
    reports_dir = tmp_path / "reports"
    deps = launcher.default_deps(reports_dir=str(reports_dir))
    opened: list[str] = []
    deps = dataclasses.replace(deps, open=opened.append)
    got = launcher.execute_audit(str(root), deps=deps, abort_check=lambda: True)
    assert got is None
    assert opened == []
    assert not reports_dir.exists() or list(reports_dir.iterdir()) == []


def test_real_scanner_progress_reaches_handler_via_after(tmp_path):
    """接缝集成（真实 scanner + C8 进度跟踪器）：进度事件经 after 派发到达主线程侧
    处理器，entries 单调不减，终态事件条目数与 scan 结果一致；完整路径正常落盘。"""
    root = tmp_path / "tree"
    for index in range(5):
        (root / f"d{index}").mkdir(parents=True)
        (root / f"d{index}" / "f.bin").write_bytes(b"x" * 100)
    calls: list[str] = []
    captured: list[dict] = []
    deps = launcher.AuditDeps(
        scan=lambda path, progress_cb=None, abort_check=None: scan_path(
            path, progress_cb=progress_cb, abort_check=abort_check
        ).to_json_dict(),
        judge=lambda s: (calls.append("judge"), captured.append(s), s)[1],
        render=lambda report: (calls.append("render"), "<html>ok</html>")[1],
        save=lambda html: (calls.append("save"), str(tmp_path / "reports" / "report-x.html"))[1],
        prune=lambda: (calls.append("prune"), [])[1],
        open=lambda p: calls.append(("open", p)),
    )
    after_cbs: list = []
    events: list[ProgressEvent] = []
    result: list = []
    thread = launcher.run_audit_async(
        str(root), deps=deps, stop=threading.Event(), after=after_cbs.append,
        on_progress=events.append,
        on_complete=result.append,
        on_error=lambda e: pytest.fail(f"不应进入错误出口：{e}"),
    )
    thread.join(timeout=30)
    assert not thread.is_alive()
    for cb in list(after_cbs):  # 主线程侧统一消化派发队列
        cb()
    assert result and Path(result[0]) == tmp_path / "reports" / "report-x.html"
    assert events  # 至少一次事件（C8 终态事件不受节流）
    entries_seq = [e.entries for e in events]
    assert entries_seq == sorted(entries_seq)  # 单调不减（T3-05 消费前提）
    assert entries_seq[-1] == captured[0]["entries"]  # 终态事件 = 精确全量
    report_path = str(tmp_path / "reports" / "report-x.html")
    assert calls[-2:] == ["prune", ("open", report_path)]  # 完整路径照常落盘+打开


# ---------- T3-05：G2 文案区块（规范 §1：集中资源处；Q3 禁词；R10 零假设） ----------


def test_g2_texts_required_keys_exist():
    required = [
        "progress_group",
        "progress_status",
        "progress_current_path",
        "abort_button",
        "status_aborting",
        "status_incomplete",
        "incomplete_banner",
    ]
    missing = [key for key in required if key not in texts.G2_TEXTS]
    assert missing == []


def test_g2_texts_no_forbidden_terms():
    """Q3 禁"可回收"（禁用词约束对全部对外文案生效）。"""
    blob = "".join(texts.G2_TEXTS.values())
    assert "可回收" not in blob


def test_g2_incomplete_banner_keeps_badge_wording():
    """不完整横幅与 F2 渲染徽标同词（X-2 语义一致，用户在 UI 与报告看到同一说法）。"""
    assert texts.INCOMPLETE_BADGE in texts.G2_TEXTS["incomplete_banner"]
    assert "未生成报告" in texts.G2_TEXTS["incomplete_banner"]  # 中止不落盘的如实披露
