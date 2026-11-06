r"""T4-03（待办 H3）提权进程异常退出测试：等待通道方案 A / X-4 判定 / tmp 日志 / 报告零改动。

依据：方案 X-4（提权进程异常退出 → 保留普通模式既有报告，提示"管理员重扫失败，
已保留上次结果"）、R10 零假设（超时与崩溃不作区分性断言，细节进日志）、T4-01
接口约定（提权实例退出码 0/4/5；done 标记 error 字段；EXIT_BAD_REQUEST 不写 done）、
T4-02 归一化契约（request_admin_rescan 返回码保持 ShellExecuteW 风格、
admin_rescan_status_text 及其全部既有测试零改动；发起阶段 1223 取消不进等待链）、
G2 状态栏先例（非阻塞 status_var 文案）、E-5 零弹窗先例、开发规范 §3（测试规范）。

等待通道（任务卡方案 A）：宿主发起升级 ShellExecuteExW + SEE_MASK_NOCLOSEPROCESS
（成功时 SHELLEXECUTEINFO.hProcess 即提权实例句柄）→ 后台 daemon 线程
WaitForSingleObject（上限 ADMIN_RESCAN_WAIT_TIMEOUT_MS）→ GetExitCodeProcess →
退出码 0=成功（读 done 衔接 T4-01 完成态）/ 非 0=异常退出 → X-4 状态栏文案 +
tmp 日志（U-2 合规位，时间戳+退出码+等待摘要+done.error）。

测试策略（沿用 test_launcher_h2.py 注入式先例，不创建 Tk 实例、零真实等待、
零真实 runas/零 UAC）：
- 等待/退出码全部注入替身（wait_fn/exit_code_fn 立即返回），替身句柄为任意对象；
- 判定收敛纯函数 admin_rescan_finish_text/_admin_rescan_failed（直接构造
  AdminRescanExit 断言，含反例）；
- 发起链接线经 monkeypatch launcher._shell_execute_runas（防重生日志标注的
  全仓库唯一 ShellExecute 出口）返回 (哨兵 33, 替身句柄)，真实 ctypes 永不触达；
- 既有报告零改动以文件 hash 前后一致断言；tmp 日志写入口可注入。
"""
from __future__ import annotations

import ast
import hashlib
import sys
import threading
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
# X-4 定稿原文短语（文案断言的锚点）
_X4_PHRASE = "管理员重扫失败，已保留上次结果"

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

# 自启动调用名单（等待链/呈现链零自启动：双禁含 H3 升级的 ShellExecuteExW）
_SELFSTART_CALL_NAMES = frozenset(
    {"ShellExecuteW", "ShellExecuteExW", "WinExec", "system", "popen", "Popen", "startfile"}
)
_RELAUNCH_NAMES = ("_shell_execute_runas", "_launch_elevated_self", "request_admin_rescan")


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


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reports_snapshot(reports_dir: Path) -> dict[str, str]:
    return {p.name: _file_hash(p) for p in sorted(reports_dir.iterdir()) if p.is_file()}


# ---------- 验收①前置：等待通道常量与结果模型（方案 A 自决记录） ----------


def test_wait_timeout_budget_is_15_minutes():
    """等待上限自决 = 15 分钟（900000ms；依据见 PR/执行记录：卡面建议值，普通模式
    全盘扫描实测分钟级——方案 X4 风险项"全盘 > 60s → 降级目录级"，15 分钟远超
    常规扫描预算并给慢盘留余量；超时不清杀提权实例，R10 不咬定崩溃）。"""
    assert launcher.ADMIN_RESCAN_WAIT_TIMEOUT_MS == 15 * 60 * 1000


def test_launched_sentinel_is_shell_execute_w_style():
    """归一化哨兵 33：>32 落 T4-02"已发起"分支（对外契约不变的关键锚点）。"""
    assert launcher.ADMIN_RESCAN_LAUNCHED_CODE == 33
    assert (
        launcher.admin_rescan_status_text(launcher.ADMIN_RESCAN_LAUNCHED_CODE)
        == texts.H1_TEXTS["status_admin_launched"]
    )


def test_win32_wait_constants():
    """WAIT_OBJECT_0=0 / WAIT_TIMEOUT=0x102（Win32 语义，替身返回值断言锚点）。"""
    assert launcher.WAIT_OBJECT_0 == 0
    assert launcher.WAIT_TIMEOUT == 0x102


# ---------- 验收①：X-4 判定（纯函数，注入异常退出/超时/成功三类结果） ----------


def test_x4_exact_wording_in_failed_text():
    """X-4 定稿原文短语必须完整出现在失败文案中。"""
    assert _X4_PHRASE in texts.H3_TEXTS["status_admin_rescan_failed"]


@pytest.mark.parametrize(
    "exit_code", [5, 4, 1, 2, 259, 1223, 4294967295]
)
def test_abnormal_exit_codes_yield_x4_text(exit_code: int):
    """非 0 退出码（含 4=拒绝/5=流水线失败/硬杀任意值/1223）→ X-4 文案。

    反例面：1223 在退出码域无"取消"语义（发起阶段 1223 不进等待链，T4-02 语义
    不重做）——提权实例以 1223 退出视为异常（R10 不冒充取消）。
    """
    outcome = launcher.AdminRescanExit(timed_out=False, exit_code=exit_code, done=None)
    status = launcher.admin_rescan_finish_text(outcome)
    assert status == texts.H3_TEXTS["status_admin_rescan_failed"]
    assert _X4_PHRASE in status
    assert "已取消" not in status  # 不冒充取消（E-5 判定精确同款反例）


def test_timeout_yields_same_x4_text_r10():
    """注入超时（替身句柄 WAIT_TIMEOUT）→ 与崩溃同一 X-4 文案（R10 零假设：
    不咬定"崩溃"，超时与崩溃不作区分性措辞，细节进 tmp 日志）。"""
    outcome = launcher.AdminRescanExit(timed_out=True, exit_code=None, done=None)
    status = launcher.admin_rescan_finish_text(outcome)
    assert status == texts.H3_TEXTS["status_admin_rescan_failed"]
    assert "崩溃" not in status and "超时" not in status  # 零区分性措辞


def test_wait_failed_yields_x4_text():
    """等待失败/退出码未知（WAIT_FAILED/GetExitCodeProcess 失败）→ X-4 文案
    （R10：退出码未知不得虚报成功）。"""
    outcome = launcher.AdminRescanExit(timed_out=False, exit_code=None, done=None)
    assert launcher.admin_rescan_finish_text(outcome) == texts.H3_TEXTS["status_admin_rescan_failed"]


def test_success_exit0_completed_done_yields_completion_text():
    """注入成功退出码 0 → 读 done 衔接 T4-01 完成态：完成文案呈现 admin- 报告
    路径、无 X-4 文案。"""
    done = {"status": "completed", "report_path": r"E:\demo\admin-report-20261105.html"}
    outcome = launcher.AdminRescanExit(timed_out=False, exit_code=0, done=done)
    status = launcher.admin_rescan_finish_text(outcome)
    assert texts.H3_TEXTS["status_admin_rescan_failed"] not in status
    assert _X4_PHRASE not in status
    assert r"E:\demo\admin-report-20261105.html" in status


def test_exit0_with_missing_done_treated_as_failure_r10():
    """反例（防御性）：退出码 0 但 done 缺失/未完成 = 契约违背 → 按 X-4 处置
    （R10 零假设：不虚报成功；细节进日志，记录于执行决策）。"""
    for done in (None, {"status": "failed"}, {}):
        outcome = launcher.AdminRescanExit(timed_out=False, exit_code=0, done=done)
        assert launcher.admin_rescan_finish_text(outcome) == texts.H3_TEXTS["status_admin_rescan_failed"]


def test_admin_rescan_failed_matches_presentation_predicate():
    """X-4 判定谓词与呈现文案同一事实源（_admin_rescan_failed ↔ finish_text）。"""
    outcomes = [
        launcher.AdminRescanExit(True, None, None),
        launcher.AdminRescanExit(False, None, None),
        launcher.AdminRescanExit(False, 5, None),
        launcher.AdminRescanExit(False, 0, None),
        launcher.AdminRescanExit(False, 0, {"status": "failed"}),
    ]
    for outcome in outcomes:
        assert launcher._admin_rescan_failed(outcome) is True
        assert launcher.admin_rescan_finish_text(outcome) == texts.H3_TEXTS["status_admin_rescan_failed"]
    ok = launcher.AdminRescanExit(False, 0, {"status": "completed", "report_path": r"E:\x.html"})
    assert launcher._admin_rescan_failed(ok) is False


# ---------- 验收①：等待函数（注入替身句柄，零真实 WaitForSingleObject） ----------


def test_wait_abnormal_exit_returns_exit_code_and_done():
    """替身句柄立即信号 + 退出码 5 → AdminRescanExit(False, 5, done)；done 读取
    用于把 error 并入日志（非 0 退出也读 done——done.error 并入路径）。"""
    handle = object()
    wait_calls: list[tuple[object, int]] = []

    def fake_wait(h: object, timeout_ms: int) -> int:
        wait_calls.append((h, timeout_ms))
        return launcher.WAIT_OBJECT_0

    def fake_exit_code(h: object) -> int | None:
        assert h is handle
        return 5

    done_seen: list[bool] = []

    def fake_read_done() -> dict | None:
        done_seen.append(True)
        return {"status": "failed", "error": "流水线失败：judge 环节异常"}

    outcome = launcher.wait_admin_rescan_exit(
        handle, timeout_ms=900000, wait_fn=fake_wait,
        exit_code_fn=fake_exit_code, read_done=fake_read_done,
    )
    assert outcome == launcher.AdminRescanExit(
        timed_out=False, exit_code=5, done={"status": "failed", "error": "流水线失败：judge 环节异常"}
    )
    assert wait_calls == [(handle, 900000)]  # 替身句柄/超时上限原样透传
    assert done_seen == [True]


def test_wait_injected_timeout_returns_timed_out_without_done_read():
    """替身句柄返回 WAIT_TIMEOUT(0x102) → timed_out=True、退出码未知、不读 done
    （提权实例可能仍在运行，done 语义不成立）。"""
    handle = object()
    read_done_calls: list[int] = []

    def fake_read_done() -> dict | None:
        read_done_calls.append(1)
        return None

    outcome = launcher.wait_admin_rescan_exit(
        handle, timeout_ms=900000,
        wait_fn=lambda h, ms: launcher.WAIT_TIMEOUT,
        exit_code_fn=lambda h: pytest.fail("超时路径不得读退出码"),
        read_done=fake_read_done,
    )
    assert outcome == launcher.AdminRescanExit(timed_out=True, exit_code=None, done=None)
    assert read_done_calls == []


def test_wait_injected_wait_failed_returns_unknown_exit_code():
    """替身返回 WAIT_FAILED（ctypes c_int 语义 = -1）→ 退出码未知、不读 done。"""
    handle = object()
    outcome = launcher.wait_admin_rescan_exit(
        handle, timeout_ms=1000,
        wait_fn=lambda h, ms: -1,
        exit_code_fn=lambda h: pytest.fail("等待失败路径不得读退出码"),
        read_done=lambda: {"status": "completed"},
    )
    assert outcome == launcher.AdminRescanExit(timed_out=False, exit_code=None, done=None)


def test_wait_exit_code_read_failure_returns_unknown():
    """等待命中但 GetExitCodeProcess 失败（替身返回 None）→ 退出码未知 → X-4 处置。"""
    outcome = launcher.wait_admin_rescan_exit(
        object(), timeout_ms=1000,
        wait_fn=lambda h, ms: launcher.WAIT_OBJECT_0,
        exit_code_fn=lambda h: None,
        read_done=lambda: {"status": "completed"},
    )
    assert outcome == launcher.AdminRescanExit(timed_out=False, exit_code=None, done=None)


def test_wait_success_exit0_reads_done():
    """退出码 0 → 读 done 标记衔接 T4-01 完成态。"""
    done = {"status": "completed", "report_path": r"E:\demo\admin-report.html"}
    outcome = launcher.wait_admin_rescan_exit(
        object(), timeout_ms=1000,
        wait_fn=lambda h, ms: launcher.WAIT_OBJECT_0,
        exit_code_fn=lambda h: 0,
        read_done=lambda: done,
    )
    assert outcome == launcher.AdminRescanExit(timed_out=False, exit_code=0, done=done)


# ---------- tmp 崩溃日志（U-2 合规位；写入口可注入） ----------


def test_abnormal_exit_log_contains_stamp_request_exit_code_and_done_error(tmp_path):
    """异常退出日志：时间戳 + request_id + 退出码 + 等待摘要 + done.error 并入。"""
    outcome = launcher.AdminRescanExit(
        timed_out=False, exit_code=5,
        done={"status": "failed", "error": "流水线失败：judge 环节异常"},
    )
    launcher._write_admin_rescan_failure_log(
        outcome, request_id="a" * 32, tmp_dir=str(tmp_path), now=_NOW
    )
    log_path = tmp_path / launcher.ADMIN_RESCAN_FAILURE_LOG_FILENAME
    assert log_path.is_file()
    content = log_path.read_text(encoding="utf-8")
    assert "2026-11-05T12:00:00+00:00" in content  # 时间戳（ISO8601 UTC）
    assert "request_id=" + "a" * 32 in content
    assert "exit_code=5" in content
    assert "流水线失败：judge 环节异常" in content  # done.error 并入


def test_abnormal_exit_log_without_done_marks_error_absent(tmp_path):
    """硬杀（无 done 标记）→ 日志如实标注 done.error=无，退出码仍入日志。"""
    outcome = launcher.AdminRescanExit(timed_out=False, exit_code=3221225477, done=None)
    launcher._write_admin_rescan_failure_log(
        outcome, request_id="b" * 32, tmp_dir=str(tmp_path), now=_NOW
    )
    content = (tmp_path / launcher.ADMIN_RESCAN_FAILURE_LOG_FILENAME).read_text(encoding="utf-8")
    assert "exit_code=3221225477" in content
    assert "done.error=无" in content


def test_timeout_log_records_may_still_running(tmp_path):
    """超时日志：等待摘要含"等待超时"与"可能仍在运行"，退出码如实标注未知。"""
    outcome = launcher.AdminRescanExit(timed_out=True, exit_code=None, done=None)
    launcher._write_admin_rescan_failure_log(
        outcome, request_id="c" * 32, tmp_dir=str(tmp_path), now=_NOW
    )
    content = (tmp_path / launcher.ADMIN_RESCAN_FAILURE_LOG_FILENAME).read_text(encoding="utf-8")
    assert "等待超时" in content
    assert "可能仍在运行" in content
    assert "exit_code=unknown" in content


def test_log_line_is_pure_and_injectable_writer(tmp_path):
    """日志行纯函数（不触盘）+ 写入口可注入（log_writer 注入即零文件落盘）。"""
    outcome = launcher.AdminRescanExit(timed_out=False, exit_code=4, done=None)
    line = launcher._admin_rescan_log_line(
        outcome, request_id="d" * 32, timeout_ms=launcher.ADMIN_RESCAN_WAIT_TIMEOUT_MS, now=_NOW
    )
    assert "exit_code=4" in line and "d" * 32 in line
    captured: list[str] = []
    launcher._write_admin_rescan_failure_log(
        outcome, request_id="d" * 32, tmp_dir=str(tmp_path),
        now=_NOW, log_writer=captured.append,
    )
    assert captured == [line]
    assert not (tmp_path / launcher.ADMIN_RESCAN_FAILURE_LOG_FILENAME).exists()


def test_log_write_failure_does_not_break_presentation(tmp_path):
    """日志写失败不阻断 X-4 呈现（排查辅助降级，X-1 风格；异常不外泄）。"""

    def broken_writer(line: str) -> None:
        raise OSError("磁盘满")

    outcome = launcher.AdminRescanExit(timed_out=False, exit_code=5, done=None)
    launcher._write_admin_rescan_failure_log(
        outcome, request_id="e" * 32, tmp_dir=str(tmp_path),
        now=_NOW, log_writer=broken_writer,
    )
    # 未抛异常即通过；呈现不受影响
    assert launcher.admin_rescan_finish_text(outcome) == texts.H3_TEXTS["status_admin_rescan_failed"]


# ---------- 发起链接线（monkeypatch 单点发起 → 哨兵 33 + 替身句柄） ----------


def _wire_real_launch(monkeypatch: pytest.MonkeyPatch, handle: object) -> None:
    monkeypatch.setattr(
        launcher, "_shell_execute_runas",
        lambda lp_file, lp_verb, lp_parameters: (launcher.ADMIN_RESCAN_LAUNCHED_CODE, handle),
    )


def test_request_admin_rescan_wires_wait_chain_on_real_launch(monkeypatch, tmp_path):
    """方案 A 全接线（异常退出）：真发起链返回哨兵 33 → 后台等待（替身即时返回）
    → 退出码 5 → X-4 文案 + tmp 日志 + 既有报告零改动。"""
    handle = object()
    _wire_real_launch(monkeypatch, handle)
    monkeypatch.setattr(launcher, "_wait_for_single_object", lambda h, ms: launcher.WAIT_OBJECT_0)
    monkeypatch.setattr(launcher, "_get_exit_code_process", lambda h: 5)

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    original = reports_dir / "report-20261105-120000.html"
    original.write_text("<html>old</html>", encoding="utf-8")
    before = _reports_snapshot(reports_dir)

    finished: list[launcher.AdminRescanExit] = []
    done_evt = threading.Event()

    def on_finished(outcome: launcher.AdminRescanExit) -> None:
        finished.append(outcome)
        done_evt.set()

    rc = launcher.request_admin_rescan(
        r"C:\scope\x",
        tmp_dir=str(tmp_path),
        executable=r"D:\py\python.exe",
        script=r"E:\repo\launcher.py",
        now=_NOW,
        wait_completion=on_finished,
        after=lambda cb: cb(),  # 测试直连派发（真实运行经 root.after 派发主线程）
    )
    assert rc == launcher.ADMIN_RESCAN_LAUNCHED_CODE
    assert done_evt.wait(timeout=5)  # 替身即时返回：仅测试线程同步，非真实等待
    outcome = finished[0]
    assert outcome.timed_out is False and outcome.exit_code == 5
    assert _X4_PHRASE in launcher.admin_rescan_finish_text(outcome)
    # tmp 日志已写入（U-2 合规位）
    log_path = tmp_path / launcher.ADMIN_RESCAN_FAILURE_LOG_FILENAME
    assert log_path.is_file()
    assert "exit_code=5" in log_path.read_text(encoding="utf-8")
    # 既有报告零改动：文件集合与逐文件 hash 前后一致
    assert _reports_snapshot(reports_dir) == before
    # done 标记零写入（宿主等待链不写不删）；spec 为发起尝试物保留
    assert not (tmp_path / elevated.DONE_FILENAME).exists()
    assert (tmp_path / elevated.SPEC_FILENAME).is_file()


def test_request_admin_rescan_timeout_end_to_end_wire(monkeypatch, tmp_path):
    """方案 A 全接线（超时）：替身等待返回 WAIT_TIMEOUT → X-4 文案 + 超时日志。"""
    handle = object()
    _wire_real_launch(monkeypatch, handle)
    monkeypatch.setattr(launcher, "_wait_for_single_object", lambda h, ms: launcher.WAIT_TIMEOUT)

    finished: list[launcher.AdminRescanExit] = []
    done_evt = threading.Event()

    def on_finished(outcome: launcher.AdminRescanExit) -> None:
        finished.append(outcome)
        done_evt.set()

    rc = launcher.request_admin_rescan(
        r"C:\scope\x",
        tmp_dir=str(tmp_path),
        executable=r"D:\py\python.exe",
        script=r"E:\repo\launcher.py",
        now=_NOW,
        wait_completion=on_finished,
        after=lambda cb: cb(),
    )
    assert rc == launcher.ADMIN_RESCAN_LAUNCHED_CODE
    assert done_evt.wait(timeout=5)
    outcome = finished[0]
    assert outcome.timed_out is True and outcome.exit_code is None
    assert launcher.admin_rescan_finish_text(outcome) == texts.H3_TEXTS["status_admin_rescan_failed"]
    content = (tmp_path / launcher.ADMIN_RESCAN_FAILURE_LOG_FILENAME).read_text(encoding="utf-8")
    assert "等待超时" in content


def test_request_admin_rescan_success_wire_links_done(monkeypatch, tmp_path):
    """方案 A 全接线（成功）：退出码 0 → done 衔接完成态、无 X-4 文案；done 由
    宿主只读（不写不删）。done 由替身等待函数模拟提权实例退出前写入（时序确定；
    发起阶段 write_rescan_request 清旧 done 属 T4-01 既有语义，不在本用例面）。"""
    handle = object()
    _wire_real_launch(monkeypatch, handle)
    done_path = tmp_path / elevated.DONE_FILENAME
    done_hashes: list[str] = []

    def fake_wait(h: object, ms: int) -> int:
        # 模拟提权实例：退出前写 done=completed（T4-01 契约），宿主随后读取
        elevated.write_done_marker(
            request_id="f" * 32, status="completed",
            report_path=r"E:\demo\admin-report.html", tmp_dir=str(tmp_path),
        )
        done_hashes.append(_file_hash(done_path))
        return launcher.WAIT_OBJECT_0

    monkeypatch.setattr(launcher, "_wait_for_single_object", fake_wait)
    monkeypatch.setattr(launcher, "_get_exit_code_process", lambda h: 0)

    finished: list[launcher.AdminRescanExit] = []
    done_evt = threading.Event()

    def on_finished(outcome: launcher.AdminRescanExit) -> None:
        finished.append(outcome)
        done_evt.set()

    rc = launcher.request_admin_rescan(
        r"C:\scope\x",
        tmp_dir=str(tmp_path),
        executable=r"D:\py\python.exe",
        script=r"E:\repo\launcher.py",
        now=_NOW,
        wait_completion=on_finished,
        after=lambda cb: cb(),
    )
    assert rc == launcher.ADMIN_RESCAN_LAUNCHED_CODE
    assert done_evt.wait(timeout=5)
    outcome = finished[0]
    assert outcome.exit_code == 0
    assert outcome.done is not None and outcome.done.get("status") == "completed"
    assert "admin-report.html" in launcher.admin_rescan_finish_text(outcome)
    assert _X4_PHRASE not in launcher.admin_rescan_finish_text(outcome)
    # done 标记零改动（宿主等待链只读不写不删）；无失败日志
    assert _file_hash(done_path) == done_hashes[0]
    assert not (tmp_path / launcher.ADMIN_RESCAN_FAILURE_LOG_FILENAME).exists()


@pytest.mark.parametrize("launch_code", [elevated.ERROR_CANCELLED, 5, 2])
def test_cancel_and_launch_failure_never_enter_wait_chain(monkeypatch, launch_code, tmp_path):
    """取消（1223）与发起失败不进等待链（T4-02 语义不重做）——即使等待已接线，
    等待函数零调用、完成回调零触发。"""
    monkeypatch.setattr(
        launcher, "_shell_execute_runas",
        lambda lp_file, lp_verb, lp_parameters: (launch_code, None),
    )
    violated = threading.Event()

    def evil_wait(h: object, ms: int) -> int:
        violated.set()
        return launcher.WAIT_OBJECT_0

    monkeypatch.setattr(launcher, "_wait_for_single_object", evil_wait)
    finished: list[launcher.AdminRescanExit] = []
    rc = launcher.request_admin_rescan(
        r"C:\scope\x",
        tmp_dir=str(tmp_path),
        executable=r"D:\py\python.exe",
        script=r"E:\repo\launcher.py",
        wait_completion=finished.append,
        after=lambda cb: cb(),
    )
    assert rc == launch_code  # 返回码原样透传（T4-01 契约）
    assert violated.wait(timeout=0.5) is False  # 有界探测：等待链未启动（零真实等待）
    assert finished == []


def test_launched_without_handle_never_enters_wait_chain(monkeypatch, tmp_path):
    """防御：发起成功但句柄不可用（None）→ 不进等待链（火后不管，T4-01 语义回退）、
    返回码仍为哨兵 33。"""
    monkeypatch.setattr(
        launcher, "_shell_execute_runas",
        lambda lp_file, lp_verb, lp_parameters: (launcher.ADMIN_RESCAN_LAUNCHED_CODE, None),
    )
    violated = threading.Event()

    def evil_wait(h: object, ms: int) -> int:
        violated.set()
        return launcher.WAIT_OBJECT_0

    monkeypatch.setattr(launcher, "_wait_for_single_object", evil_wait)
    finished: list[launcher.AdminRescanExit] = []
    rc = launcher.request_admin_rescan(
        r"C:\scope\x",
        tmp_dir=str(tmp_path),
        executable=r"D:\py\python.exe",
        script=r"E:\repo\launcher.py",
        wait_completion=finished.append,
        after=lambda cb: cb(),
    )
    assert rc == launcher.ADMIN_RESCAN_LAUNCHED_CODE
    assert violated.wait(timeout=0.5) is False
    assert finished == []


def test_wait_completion_default_none_keeps_t401_semantics(monkeypatch, tmp_path):
    """默认（未接线 wait_completion）保持 T4-01 火后不管语义：等待链零启动。"""
    handle = object()
    _wire_real_launch(monkeypatch, handle)
    monkeypatch.setattr(
        launcher, "_wait_for_single_object",
        lambda h, ms: pytest.fail("未接线不得进入等待链"),
    )
    rc = launcher.request_admin_rescan(
        r"C:\scope\x",
        tmp_dir=str(tmp_path),
        executable=r"D:\py\python.exe",
        script=r"E:\repo\launcher.py",
    )
    assert rc == launcher.ADMIN_RESCAN_LAUNCHED_CODE


def test_abnormal_exit_reports_hash_unchanged_and_done_untouched(monkeypatch, tmp_path):
    """验收②等效（单测层）：异常退出路径既有报告 hash 前后一致、不新建报告文件、
    done 标记不写不删（宿主等待链零触碰 reports\\ 与 done；done=failed 由替身
    等待函数模拟提权实例退出前写入，其 error 字段并入 tmp 日志）。"""
    handle = object()
    _wire_real_launch(monkeypatch, handle)
    done_path = tmp_path / elevated.DONE_FILENAME
    done_hashes: list[str] = []

    def fake_wait(h: object, ms: int) -> int:
        # 模拟提权实例：流水线失败退出前写 done=failed（T4-01 契约，含 error 字段）
        elevated.write_done_marker(
            request_id="a" * 32, status="failed", report_path=None,
            error="流水线失败：save 环节异常", tmp_dir=str(tmp_path),
        )
        done_hashes.append(_file_hash(done_path))
        return launcher.WAIT_OBJECT_0

    monkeypatch.setattr(launcher, "_wait_for_single_object", fake_wait)
    monkeypatch.setattr(launcher, "_get_exit_code_process", lambda h: 5)

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    for i in range(3):
        p = reports_dir / f"report-2026110{i}-090000.html"
        p.write_text(f"<html>report {i}</html>", encoding="utf-8")
    before = _reports_snapshot(reports_dir)

    done_evt = threading.Event()
    launcher.request_admin_rescan(
        r"C:\scope\x",
        tmp_dir=str(tmp_path),
        executable=r"D:\py\python.exe",
        script=r"E:\repo\launcher.py",
        now=_NOW,
        wait_completion=lambda outcome: done_evt.set(),
        after=lambda cb: cb(),
    )
    assert done_evt.wait(timeout=5)
    assert _reports_snapshot(reports_dir) == before  # 既有报告 hash 零改动
    assert _file_hash(done_path) == done_hashes[0]  # 宿主等待链对 done 零写零删
    log_content = (tmp_path / launcher.ADMIN_RESCAN_FAILURE_LOG_FILENAME).read_text(
        encoding="utf-8"
    )
    assert "流水线失败：save 环节异常" in log_content  # done.error 并入日志


# ---------- AST 结构断言：零弹窗 / 零重试 / 等待链不可再发起（E-5 风格） ----------


def test_wait_chain_has_zero_selfstart_calls_and_zero_relaunch_refs():
    """等待链（等待/判定/呈现/日志/编排）零自启动调用、零重启自身引用——
    等待环节结构上不可能再次发起提权（U-3 单点发起语义不变）。"""
    tree = _launcher_tree()
    for name in (
        "wait_admin_rescan_exit",
        "_admin_rescan_failed",
        "admin_rescan_finish_text",
        "_write_admin_rescan_failure_log",
        "_watch_admin_rescan_async",
    ):
        node = _function(tree, name)
        assert node is not None, f"缺少函数 {name}"
        selfstarts = [c for c in _calls_of(node) if c in _SELFSTART_CALL_NAMES]
        assert selfstarts == [], f"{name} 出现自启动调用 {selfstarts}"
        for relaunch in _RELAUNCH_NAMES:
            assert _ref_count(node, relaunch) == 0, f"{name} 不得引用 {relaunch}"


def test_watch_orchestration_single_wait_zero_retry():
    """编排恰一次等待、零循环/零定时再触发/零线程重试引用（零重试 AST 固化）。"""
    watcher = _function(_launcher_tree(), "_watch_admin_rescan_async")
    assert watcher is not None
    calls = _calls_of(watcher)
    assert calls.count("wait_admin_rescan_exit") == 1  # 恰一次等待
    loops = [n for n in ast.walk(watcher) if isinstance(n, (ast.For, ast.While, ast.AsyncFor))]
    assert loops == []  # 零循环重试
    assert calls.count("after") == 1  # 恰一次主线程派发（零定时再触发）
    assert "request_admin_rescan" not in calls  # 零第二次发起
    inner = [n for n in ast.walk(watcher) if isinstance(n, ast.FunctionDef)]
    for node in inner:
        for relaunch in _RELAUNCH_NAMES:
            assert _ref_count(node, relaunch) == 0


def test_presentation_and_wait_chain_zero_dialog_calls():
    """X-4/完成呈现与等待链零对话框调用（E-5 风格：提示只走非阻塞状态栏）。"""
    tree = _launcher_tree()
    for name in (
        "_on_admin_rescan",
        "_on_admin_rescan_finished",
        "_dispatch_admin_finish",
        "admin_rescan_finish_text",
        "wait_admin_rescan_exit",
        "_watch_admin_rescan_async",
    ):
        node = _function(tree, name)
        assert node is not None, f"缺少函数 {name}"
        dialog_calls = [c for c in _calls_of(node) if c in _DIALOG_CALL_NAMES]
        assert dialog_calls == [], f"{name} 出现对话框调用 {dialog_calls}"


def test_finish_text_is_pure():
    """呈现判定纯函数：零 I/O/零调度调用（仅格式化、字典取值、内建 str 转换、
    子谓词）。"""
    node = _function(_launcher_tree(), "admin_rescan_finish_text")
    assert node is not None
    assert set(_calls_of(node)) <= {
        "format", "get", "isinstance", "str", "_admin_rescan_failed"
    }


def test_wait_chain_wiring_into_click_callback():
    """回调接线：wait_completion/after 注入单次；呈现函数走状态栏（G2 先例）。"""
    tree = _launcher_tree()
    click = _function(tree, "_on_admin_rescan")
    assert click is not None
    assert _ref_count(click, "_on_admin_rescan_finished") == 1
    assert _ref_count(click, "_dispatch_admin_finish") == 1
    finished = _function(tree, "_on_admin_rescan_finished")
    assert finished is not None
    assert "admin_rescan_finish_text" in _calls_of(finished)
    assert "set" in _calls_of(finished)  # status_var.set —— 非阻塞状态栏
    dispatcher = _function(tree, "_dispatch_admin_finish")
    assert dispatcher is not None
    assert "after" in _calls_of(dispatcher)  # 等待线程 → 主线程派发（G2 run_audit_async 先例）


# ---------- 归一化契约回归（T4-02 既有判定零改动的事实源锚点） ----------


@pytest.mark.parametrize("code", [0, 2, 5, 8, 11, 26, 31, 32, -1])
def test_launch_failure_codes_keep_t402_texts(code: int):
    """发起失败码（≤32）→ T4-02 既有失败文案（归一化不改变既有映射）。"""
    assert launcher.admin_rescan_status_text(code) == texts.H2_TEXTS["status_admin_launch_failed"].format(code=code)


def test_cancel_code_keeps_t402_text():
    """1223 → T4-02 取消文案（取消语义归 T4-02，H3 不重做）。"""
    assert (
        launcher.admin_rescan_status_text(elevated.ERROR_CANCELLED)
        == texts.H2_TEXTS["status_admin_cancelled"]
    )


# ---------- H3 文案区块（texts.py 文末 append-only；Q3 禁词同款） ----------


def test_h3_texts_required_keys_exist():
    assert set(texts.H3_TEXTS) == {
        "status_admin_rescan_failed",
        "status_admin_rescan_completed",
    }


def test_h3_texts_no_forbidden_terms():
    blob = "".join(texts.H3_TEXTS.values())
    assert "可回收" not in blob


def test_completed_text_carries_report_path_and_admin_marker():
    """完成文案呈现 admin- 报告路径并含"管理员"标注语境（衔接 S-3 独立记录口径）。"""
    text = texts.H3_TEXTS["status_admin_rescan_completed"].format(
        path=r"E:\demo\admin-report-20261105.html"
    )
    assert r"E:\demo\admin-report-20261105.html" in text
    assert "管理员" in text
