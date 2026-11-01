r"""T3-04（待办 G1）范围选择界面纯逻辑测试。

依据：方案 P4（预设四目录 %APPDATA% / %LOCALAPPDATA% / %PROGRAMDATA% / C:\Program Files）、
P5（build 22621 启动检测，不足拒绝）、P6（仅固定本地盘，其余置灰+原因）、
开发规范 §1（引擎/UI 解耦：disk_audit 包内不得 import tkinter；文案集中资源处）、§3（测试规范）。

测试只覆盖纯逻辑（版本闸、盘型置灰、预设模型、文案、耦合边界），
不创建 Tk 实例、不起 mainloop（CI 稳定性）；UI 真启动由本机实测截图留档（验收③）。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import launcher  # noqa: E402
from disk_audit.engine import texts  # noqa: E402


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

    本卡同步接线；G2（T3-05）将把该流水线异步化（进度/中止），故编排收敛在
    execute_audit 单点，替身注入接口即异步化改造边界。
    """
    calls: list[tuple] = []
    deps = launcher.AuditDeps(
        scan=lambda p: (calls.append(("scan", p)), {"root": p, "units": [], "skipped": {}})[1],
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
