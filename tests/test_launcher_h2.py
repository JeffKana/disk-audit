r"""T4-02（待办 H2）UAC 取消处理测试：E-5 判定精确 / 零弹窗 / 零重试 / 原报告零变更。

依据：方案 E-5（UAC 取消 → 保留原报告、不重试、不弹错误框，仅提示"已取消，结果未变更"）、
T4-01 接口约定（ShellExecuteW 返回码语义：>32 已发起；1223=ERROR_CANCELLED 取消；其余失败）、
G2 状态栏先例（非阻塞 status_var 文案）、开发规范 §3（测试规范）。

测试策略（沿用 test_elevated.py 注入式先例，不创建 Tk 实例、不发起真实 UAC）：
- 判定收敛于纯函数 ``launcher.admin_rescan_status_text``（码 → 文案，无 Tk/无 I/O），
  注入各返回码断言判定精确性（含反例：其他失败码不得冒充取消）；
- 零弹窗/零重试以 AST 结构断言固化（回调恰一次发起、零循环/零 after 调度/零线程、
  取消路径零对话框调用）；T4-01 既有 AST 契约（request_admin_rescan 引用数==1 且
  调用点唯一在 _on_admin_rescan）由 tests/test_elevated.py 继续守护，本文件不重复锁
  引用数、只增回调内部结构断言；
- 原报告零变更以注入式行为断言：替身 runas 返回 ERROR_CANCELLED → reports 目录
  逐文件不变、done 标记零写入。

验收②"UAC 弹窗点否"本宿主为管理员会话不可复现（runas 静默通过），以本注入式
取消路径断言替代并由 R-M2 VM 复验覆盖（见 PR 描述与执行记录）。
"""
from __future__ import annotations

import ast
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import launcher  # noqa: E402
from disk_audit import elevated  # noqa: E402
from disk_audit.engine import texts  # noqa: E402

_NOW = datetime(2026, 11, 5, 12, 0, 0, tzinfo=timezone.utc)

# 对话框/弹窗类调用名单（E-5 明文：不弹错误对话框——取消路径零此类调用）
_DIALOG_CALL_NAMES = frozenset(
    {
        "messagebox",
        "showerror",
        "showwarning",
        "showinfo",
        "askyesno",
        "askokcancel",
        "askquestion",
        "askstring",
        "Dialog",
        "Toplevel",
    }
)


def _launcher_tree() -> ast.Module:
    return ast.parse((_REPO_ROOT / "launcher.py").read_text(encoding="utf-8"))


def _function(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _calls_of(node: ast.AST) -> list[str]:
    return [_call_name(c) for c in ast.walk(node) if isinstance(c, ast.Call)]


def _ref_count(tree: ast.AST, name: str) -> int:
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name:
            count += 1
        elif isinstance(node, ast.Attribute) and node.attr == name:
            count += 1
    return count


# ---------- 验收①：取消路径判定（注入 ERROR_CANCELLED，判定精确） ----------


def test_cancel_text_carries_e5_exact_wording():
    """E-5 定稿原文短语"已取消，结果未变更"必须出现在取消文案中。"""
    cancelled = texts.H2_TEXTS["status_admin_cancelled"]
    assert "已取消，结果未变更" in cancelled


def test_error_cancelled_maps_to_cancel_text_exactly():
    """1223（ERROR_CANCELLED）→ 取消文案；常量与字面量同一映射（判定精确）。"""
    expected = texts.H2_TEXTS["status_admin_cancelled"]
    assert launcher.admin_rescan_status_text(elevated.ERROR_CANCELLED) == expected
    assert launcher.admin_rescan_status_text(1223) == expected


@pytest.mark.parametrize("code", [0, 2, 5, 8, 11, 26, 31, 32, -1])
def test_other_failure_codes_never_masquerade_as_cancelled(code: int):
    """反例（判定精确性）：其余 ≤32 失败码（NotFound=2/AccessDenied=5 等）不得显示取消文案。"""
    cancelled = texts.H2_TEXTS["status_admin_cancelled"]
    launched = texts.H1_TEXTS["status_admin_launched"]
    status = launcher.admin_rescan_status_text(code)
    assert status != cancelled
    assert "已取消" not in status  # 不冒充取消
    assert status != launched  # 也不冒充已发起
    assert str(code) in status  # 返回码如实披露（独立状态栏文案）


@pytest.mark.parametrize("code", [33, 42, 100, 2147483647])
def test_success_codes_keep_h1_launched_text(code: int):
    """>32 已发起 → H1 "已发起"文案（正常完成路径不受 H2 改造影响）。"""
    assert (
        launcher.admin_rescan_status_text(code) == texts.H1_TEXTS["status_admin_launched"]
    )


def test_three_outcomes_have_three_distinct_texts():
    """取消 / 发起失败 / 已发起三态文案两两可区分（其他失败不冒充取消的结构前提）。"""
    outcomes = {
        launcher.admin_rescan_status_text(42),
        launcher.admin_rescan_status_text(elevated.ERROR_CANCELLED),
        launcher.admin_rescan_status_text(5),
    }
    assert len(outcomes) == 3


# ---------- 验收③：重试计数为零（无自动重试路径） ----------


def test_cancel_callback_requests_exactly_once_with_zero_retry_structure():
    """AST 结构断言：回调内恰一次发起，零循环/零 after 调度/零线程——无自动重试路径。"""
    click = _function(_launcher_tree(), "_on_admin_rescan")
    assert click is not None
    calls = _calls_of(click)
    assert calls.count("request_admin_rescan") == 1  # 恰一次发起（重试计数恒 0）
    loops = [n for n in ast.walk(click) if isinstance(n, (ast.For, ast.While, ast.AsyncFor))]
    assert loops == []  # 零循环重试
    assert "after" not in calls  # 零定时再触发
    for thread_name in ("Thread", "Event", "start_new_thread"):
        assert _ref_count(click, thread_name) == 0  # 零线程重试


def test_status_text_decision_is_pure_and_cannot_relaunch():
    """判定纯函数零 I/O、零自启动引用——呈现环节结构上不可能再次发起。"""
    decision = _function(_launcher_tree(), "admin_rescan_status_text")
    assert decision is not None
    assert set(_calls_of(decision)) <= {"format"}  # 仅字符串格式化，无任何 I/O/调度
    for relaunch in ("request_admin_rescan", "_launch_elevated_self", "_shell_execute_runas"):
        assert _ref_count(decision, relaunch) == 0  # 零自启动引用


def test_cancel_decision_uses_elevated_constant_not_magic_number():
    """取消判定引用 elevated.ERROR_CANCELLED 常量，不得裸写 1223（单一事实源）。"""
    decision = _function(_launcher_tree(), "admin_rescan_status_text")
    assert decision is not None
    assert _ref_count(decision, "ERROR_CANCELLED") == 1
    literals = [
        n.value for n in ast.walk(decision)
        if isinstance(n, ast.Constant) and isinstance(n.value, int)
    ]
    assert 1223 not in literals


def test_cancel_presentation_adds_no_second_request(tmp_path):
    """行为断言：取消后完成呈现环节，request_admin_rescan 调用计数仍为 1（零第二次调用）。"""
    calls: list[tuple[str, str, str]] = []

    def fake_shell_execute(lp_file: str, lp_verb: str, lp_parameters: str) -> int:
        calls.append((lp_file, lp_verb, lp_parameters))
        return elevated.ERROR_CANCELLED

    rc = launcher.request_admin_rescan(
        r"C:\scope\x",
        tmp_dir=str(tmp_path),
        shell_execute=fake_shell_execute,
        executable=r"D:\py\python.exe",
        script=r"E:\repo\launcher.py",
        now=_NOW,
    )
    assert rc == elevated.ERROR_CANCELLED
    assert len(calls) == 1
    status = launcher.admin_rescan_status_text(rc)  # 呈现环节（回调内唯一后续动作）
    assert len(calls) == 1  # 呈现后仍恰一次——无第二次 request_admin_rescan 调用
    assert "已取消，结果未变更" in status


# ---------- 验收②（注入式替代）：取消后原报告零变更 + done 标记零写入 ----------


def test_cancel_path_keeps_reports_and_writes_no_done_marker(tmp_path):
    """注入式取消全链：spec 为发起尝试物（U-2 tmp 位），reports 目录逐文件不变，
    done 标记/认领残留零写入（E-5：保留原报告）。"""
    calls: list[tuple[str, str, str]] = []

    def fake_shell_execute(lp_file: str, lp_verb: str, lp_parameters: str) -> int:
        calls.append((lp_file, lp_verb, lp_parameters))
        return elevated.ERROR_CANCELLED

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    original_report = reports_dir / "report-20261105-120000.html"
    original_report.write_text("<html>old</html>", encoding="utf-8")
    before = sorted(p.name for p in reports_dir.iterdir())

    rc = launcher.request_admin_rescan(
        r"C:\scope\x",
        tmp_dir=str(tmp_path),
        shell_execute=fake_shell_execute,
        executable=r"D:\py\python.exe",
        script=r"E:\repo\launcher.py",
        now=_NOW,
    )
    status = launcher.admin_rescan_status_text(rc)

    assert len(calls) == 1  # 恰一次发起（U-3 单击语义）
    assert "已取消，结果未变更" in status
    # 原报告零变更：reports 目录文件集合与内容均不变
    assert sorted(p.name for p in reports_dir.iterdir()) == before
    assert original_report.read_text(encoding="utf-8") == "<html>old</html>"
    # done 标记零写入（E-5/H1 接口：done 只由合法提权请求产出）；认领文件零残留
    assert not (tmp_path / elevated.DONE_FILENAME).exists()
    assert not (tmp_path / (elevated.SPEC_FILENAME + elevated.CLAIM_SUFFIX)).exists()
    assert (tmp_path / elevated.SPEC_FILENAME).is_file()  # 发起尝试物（陈旧请求由时效窗拒绝）


# ---------- 零弹窗（E-5 明文：不弹出错误框） + 回调接线 ----------


@pytest.mark.parametrize("func_name", ["_on_admin_rescan", "admin_rescan_status_text"])
def test_cancel_path_contains_zero_dialog_calls(func_name: str):
    """取消路径（回调 + 判定函数）零对话框调用——提示只走非阻塞状态栏（G2 先例）。"""
    node = _function(_launcher_tree(), func_name)
    assert node is not None, f"缺少函数 {func_name}"
    dialog_calls = [c for c in _calls_of(node) if c in _DIALOG_CALL_NAMES]
    assert dialog_calls == []


def test_callback_wires_decision_into_status_bar():
    """回调接线：返回码经 admin_rescan_status_text 判定后写入 status_var（G2 状态栏先例）。"""
    click = _function(_launcher_tree(), "_on_admin_rescan")
    assert click is not None
    calls = _calls_of(click)
    assert "admin_rescan_status_text" in calls
    assert "set" in calls  # status_var.set —— 非阻塞状态栏文案


# ---------- H2 文案区块（texts.py 文末 append-only；Q3 禁词同样适用） ----------


def test_h2_texts_required_keys_exist():
    assert set(texts.H2_TEXTS) == {"status_admin_cancelled", "status_admin_launch_failed"}


def test_h2_texts_no_forbidden_terms():
    blob = "".join(texts.H2_TEXTS.values())
    assert "可回收" not in blob


def test_failure_text_discloses_code_without_cancel_wording():
    """发起失败文案如实披露返回码、不含"已取消"措辞（判定精确的反例面）。"""
    text = texts.H2_TEXTS["status_admin_launch_failed"].format(code=5)
    assert "5" in text
    assert "已取消" not in text
    assert "管理员重扫" in text
