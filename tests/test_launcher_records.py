"""T5-02-A 记录保存接线测试（I1b 保存环；契约 T502A-v1 / DR-012）。

覆盖：
- save → record → prune → open 顺序与"至多一次"；
- incomplete / scan/judge/render/save 失败时记录环零调用；
- 记录失败（RecordError/OSError/一般 Exception）与通知回调异常不破坏报告、
  返回值与 prune/open 后续路径；不捕获 BaseException；不吞其它环错误；
- on_record 载荷（saved/record_id/report_path/error）成功与失败不混；
- 真实 save_record/read_record 往返（普通 / admin 前缀），records_dir 与
  reports_dir 独立注入；
- run_audit_async 经 after 回主线程、窗口销毁与回调异常；
- admin 合成流水线（run_elevated_rescan）记录失败但报告成功仍 completed/EXIT0。

全部使用 tmp_path / 替身，不写真实 RECORDS_DIR，不扫描真实用户目录。
"""
from __future__ import annotations

import copy
import threading
from pathlib import Path

import pytest

import launcher
from disk_audit import elevated, records


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


def _valid_report(admin: bool = False) -> dict:
    report: dict = {
        "schema_version": "1.1",
        "generated_at": "2026-11-15T19:00:00+08:00",
        "scan_root": r"C:\scope",
        "totals": {
            "allocated_bytes": 1024,
            "logical_bytes": 2048,
            "regenerable_subtotal": 0,
            "regenerable_confirm_subtotal": 0,
            "skipped_entries": 1,
        },
        "candidates": [
            {
                "path": r"C:\scope\demo",
                "logical_bytes": 2048,
                "allocated_bytes": 1024,
                "confidence": "中",
                "verdict_source": "知识库",
                "evidence_chain": [{"source": "知识库", "content": "合成样例"}],
                "suggested_action": "A5",
            }
        ],
    }
    if admin:
        report["admin_mode"] = True
    return report


def _deps(
    calls: list[tuple],
    *,
    report: dict | None = None,
    scan_result: dict | None = None,
    record=None,
    save_path: str = r"C:\reports\report-1.html",
    save_error: Exception | None = None,
):
    """六环 + 记录环替身；各环调用按序记录。"""
    payload = report if report is not None else _valid_report()

    def scan(path: str, progress_cb=None, abort_check=None):
        calls.append(("scan", path))
        if scan_result is not None:
            return scan_result
        return {"root": path, "entries": 0, "skipped": {}, "units": []}

    def judge(scan_data: dict) -> dict:
        calls.append(("judge", scan_data.get("root")))
        return payload

    def save(html: str) -> str:
        calls.append(("save", html))
        if save_error is not None:
            raise save_error
        return save_path

    kwargs = dict(
        scan=scan,
        judge=judge,
        render=lambda r: (calls.append(("render", r.get("scan_root"))), "<html></html>")[1],
        save=save,
        prune=lambda: (calls.append(("prune", None)), [])[1],
        open=lambda path: calls.append(("open", path)),
    )
    if record is not None:
        kwargs["record"] = record
    return launcher.AuditDeps(**kwargs)


# ---------------------------------------------------------------------------
# 顺序 / 至多一次
# ---------------------------------------------------------------------------


def test_execute_audit_calls_record_after_save_before_prune():
    calls: list[tuple] = []
    seen: dict = {}

    def record(report: dict) -> str:
        calls.append(("record", report.get("scan_root")))
        seen["report"] = report
        return "record-20261115-190000"

    deps = _deps(calls, record=record)
    got = launcher.execute_audit(r"C:\scope", deps=deps)

    assert got == r"C:\reports\report-1.html"
    assert [c[0] for c in calls] == ["scan", "judge", "render", "save", "record", "prune", "open"]
    assert seen["report"]["scan_root"] == r"C:\scope"


def test_execute_audit_record_is_called_at_most_once():
    calls: list[tuple] = []

    def record(report: dict) -> str:
        calls.append(("record", None))
        return "record-1"

    launcher.execute_audit(r"C:\scope", deps=_deps(calls, record=record))
    assert [c[0] for c in calls].count("record") == 1


def test_execute_audit_does_not_mutate_report():
    report = _valid_report()
    before = copy.deepcopy(report)
    calls: list[tuple] = []
    launcher.execute_audit(
        r"C:\scope", deps=_deps(calls, report=report, record=lambda r: "record-1")
    )
    assert report == before


# ---------------------------------------------------------------------------
# 零调用：不完整 / 前序失败 / 未接线
# ---------------------------------------------------------------------------


def test_execute_audit_skips_record_when_incomplete():
    calls: list[tuple] = []
    deps = _deps(calls, scan_result={"incomplete": True}, record=lambda r: "record-1")
    assert launcher.execute_audit(r"C:\scope", deps=deps) is None
    assert [c[0] for c in calls] == ["scan"]


def test_execute_audit_skips_record_when_ring_missing():
    calls: list[tuple] = []
    assert launcher.execute_audit(r"C:\scope", deps=_deps(calls)) == r"C:\reports\report-1.html"
    assert [c[0] for c in calls] == ["scan", "judge", "render", "save", "prune", "open"]


@pytest.mark.parametrize("stage", ["scan", "judge", "render", "save"])
def test_execute_audit_skips_record_when_earlier_stage_fails(stage: str):
    calls: list[tuple] = []
    boom = RuntimeError("boom-" + stage)
    deps = _deps(calls, record=lambda r: "record-1")

    def fail(*_args, **_kwargs):
        calls.append((stage + "-raise", None))
        raise boom

    object.__setattr__(deps, stage, fail)
    with pytest.raises(RuntimeError, match="boom-" + stage):
        launcher.execute_audit(r"C:\scope", deps=deps)
    assert "record" not in [c[0] for c in calls]


# ---------------------------------------------------------------------------
# 记录失败不破坏报告
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [records.RecordWriteError("写失败"), OSError("磁盘满"), RuntimeError("意外")],
    ids=["record-write-error", "os-error", "generic"],
)
def test_record_failure_keeps_report_and_continues(exc: Exception):
    calls: list[tuple] = []

    def record(report: dict) -> str:
        calls.append(("record", None))
        raise exc

    got = launcher.execute_audit(r"C:\scope", deps=_deps(calls, record=record))
    assert got == r"C:\reports\report-1.html"
    assert [c[0] for c in calls] == ["scan", "judge", "render", "save", "record", "prune", "open"]


class _SentinelAbort(BaseException):
    """测试专用 BaseException 哨兵：验证实现不吞 BaseException。

    不使用真实 KeyboardInterrupt / 信号（launcher.py 模块契约：产品侧同测试侧
    一律禁抛真 KeyboardInterrupt），避免影响 pytest 进程的中断语义。
    """


def test_record_base_exception_sentinel_is_not_swallowed():
    calls: list[tuple] = []

    def record(report: dict) -> str:
        raise _SentinelAbort("sentinel-not-a-real-interrupt")

    with pytest.raises(_SentinelAbort):
        launcher.execute_audit(r"C:\scope", deps=_deps(calls, record=record))


def test_other_ring_failure_is_not_swallowed():
    calls: list[tuple] = []

    def prune() -> list:
        calls.append(("prune", None))
        raise RuntimeError("prune-boom")

    def record(report: dict) -> str:
        calls.append(("record", None))
        return "record-1"

    deps = _deps(calls, record=record)
    object.__setattr__(deps, "prune", prune)
    with pytest.raises(RuntimeError, match="prune-boom"):
        launcher.execute_audit(r"C:\scope", deps=deps)
    assert "record" in [c[0] for c in calls]  # 记录在 prune 之前执行


# ---------------------------------------------------------------------------
# on_record 载荷
# ---------------------------------------------------------------------------


def test_on_record_success_payload():
    got: list[dict] = []
    launcher.execute_audit(
        r"C:\scope",
        deps=_deps([], record=lambda r: "record-20261115-190000"),
        on_record=got.append,
    )
    assert got == [
        {
            "saved": True,
            "record_id": "record-20261115-190000",
            "report_path": r"C:\reports\report-1.html",
            "error": None,
        }
    ]


def test_on_record_failure_payload_has_no_record_id():
    got: list[dict] = []

    def record(report: dict) -> str:
        raise records.RecordValidationError("坏报告")

    launcher.execute_audit(r"C:\scope", deps=_deps([], record=record), on_record=got.append)
    assert got[0]["saved"] is False
    assert got[0]["record_id"] is None
    assert got[0]["report_path"] == r"C:\reports\report-1.html"
    assert "坏报告" in got[0]["error"]


def test_on_record_not_called_when_ring_disabled_or_incomplete():
    got: list[dict] = []
    launcher.execute_audit(r"C:\scope", deps=_deps([]), on_record=got.append)
    launcher.execute_audit(
        r"C:\scope",
        deps=_deps([], scan_result={"incomplete": True}, record=lambda r: "record-1"),
        on_record=got.append,
    )
    assert got == []


def test_on_record_not_called_when_save_fails():
    got: list[dict] = []
    deps = _deps([], record=lambda r: "record-1", save_error=OSError("写不进"))
    with pytest.raises(OSError):
        launcher.execute_audit(r"C:\scope", deps=deps, on_record=got.append)
    assert got == []


def test_on_record_callback_error_does_not_break_pipeline():
    calls: list[tuple] = []

    def on_record(payload: dict) -> None:
        calls.append(("on_record", payload["saved"]))
        raise RuntimeError("回调坏")

    got = launcher.execute_audit(
        r"C:\scope", deps=_deps(calls, record=lambda r: "record-1"), on_record=on_record
    )
    assert got == r"C:\reports\report-1.html"
    assert ("on_record", True) in calls
    assert calls[-1][0] == "open"


# ---------------------------------------------------------------------------
# 真实 save_record / read_record 往返
# ---------------------------------------------------------------------------


def test_default_deps_record_writes_under_injected_records_dir(tmp_path: Path):
    records_dir = tmp_path / "records"
    deps = launcher.default_deps(records_dir=str(records_dir))
    report = _valid_report()
    before = copy.deepcopy(report)

    record_id = deps.record(report)

    assert record_id.startswith("record-")
    assert (records_dir / (record_id + ".json")).is_file()
    assert records.read_record(record_id, records_dir=str(records_dir)) == before
    assert report == before


def test_admin_mode_record_uses_admin_prefix(tmp_path: Path):
    records_dir = tmp_path / "records"
    deps = launcher.default_deps(records_dir=str(records_dir))
    report_id = deps.record(_valid_report(admin=True))
    assert report_id.startswith("admin-record-")
    stored = records.read_record(report_id, records_dir=str(records_dir))
    assert stored["admin_mode"] is True


def test_elevated_deps_record_uses_injected_records_dir(tmp_path: Path):
    records_dir = tmp_path / "records"
    deps = launcher._elevated_deps(records_dir=str(records_dir))
    report_id = deps.record(_valid_report(admin=True))
    assert (records_dir / (report_id + ".json")).is_file()


def test_records_dir_default_uses_records_constant(tmp_path: Path, monkeypatch):
    default_dir = tmp_path / "default-records"
    monkeypatch.setattr(records, "RECORDS_DIR", str(default_dir))
    deps = launcher.default_deps()
    record_id = deps.record(_valid_report())
    assert (default_dir / (record_id + ".json")).is_file()


def test_reports_and_records_dirs_are_independent(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    records_dir = tmp_path / "records"
    deps = launcher.default_deps(reports_dir=str(reports_dir), records_dir=str(records_dir))
    report_path = deps.save("<html>wiring</html>")
    record_id = deps.record(_valid_report())
    assert Path(report_path).parent == reports_dir
    assert (records_dir / (record_id + ".json")).is_file()
    assert list(reports_dir.glob("record-*")) == []


# ---------------------------------------------------------------------------
# 异步通道
# ---------------------------------------------------------------------------


def test_run_audit_async_record_callback_dispatched_via_after():
    pending: list = []
    seen: list = []
    main_thread = threading.get_ident()

    def on_record(payload: dict) -> None:
        seen.append((threading.get_ident(), payload["saved"]))

    thread = launcher.run_audit_async(
        r"C:\scope",
        deps=_deps([], record=lambda r: "record-1"),
        stop=threading.Event(),
        after=pending.append,
        on_progress=lambda event: None,
        on_complete=lambda path: None,
        on_error=lambda exc: None,
        on_record=on_record,
    )
    thread.join(5)
    assert not thread.is_alive()
    assert seen == []  # worker 不直接回调 UI
    for callback in list(pending):
        callback()
    assert seen == [(main_thread, True)]


def test_run_audit_async_window_destroyed_does_not_break():
    def after(_callback) -> None:
        raise RuntimeError("窗口已销毁")

    thread = launcher.run_audit_async(
        r"C:\scope",
        deps=_deps([], record=lambda r: "record-1"),
        stop=threading.Event(),
        after=after,
        on_progress=lambda event: None,
        on_complete=lambda path: None,
        on_error=lambda exc: None,
        on_record=lambda payload: None,
    )
    thread.join(5)
    assert not thread.is_alive()


def test_run_audit_async_on_record_callback_error_does_not_block_complete():
    completed: list = []

    thread = launcher.run_audit_async(
        r"C:\scope",
        deps=_deps([], record=lambda r: "record-1"),
        stop=threading.Event(),
        after=lambda callback: callback(),
        on_progress=lambda event: None,
        on_complete=completed.append,
        on_error=lambda exc: None,
        on_record=lambda payload: (_ for _ in ()).throw(RuntimeError("回调坏")),
    )
    thread.join(5)
    assert completed == [r"C:\reports\report-1.html"]


# ---------------------------------------------------------------------------
# 管理员合成流水线：记录失败但 HTML 成功 → completed / EXIT_OK
# ---------------------------------------------------------------------------


def test_admin_pipeline_record_failure_keeps_completed_exit0(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    tmp_dir = tmp_path / "tmp"
    from datetime import datetime, timezone

    fixed_now = datetime(2026, 11, 15, 11, 0, 0, tzinfo=timezone.utc)
    elevated.write_rescan_request(r"C:\scope", tmp_dir=str(tmp_dir), now=fixed_now)

    def record(report: dict) -> str:
        raise records.RecordWriteError("记录写失败")

    deps = launcher.AuditDeps(
        scan=lambda path, progress_cb=None, abort_check=None: {
            "root": path, "units": [], "allocated_bytes": 0,
            "logical_bytes": 0, "skipped": {},
        },
        judge=lambda scan: _valid_report(admin=True),
        render=lambda report: "<html>admin</html>",
        save=lambda html: elevated.save_admin_report(html, reports_dir=str(reports_dir)),
        prune=lambda: [],
        open=lambda path: None,
        record=record,
    )
    rc = elevated.run_elevated_rescan(
        audit=launcher.execute_audit, deps=deps, tmp_dir=str(tmp_dir), now=fixed_now
    )
    assert rc == elevated.EXIT_OK
    done = elevated.read_done_marker(tmp_dir=str(tmp_dir))
    assert done is not None and done["status"] == "completed"
    assert done["schema_version"] == elevated.DONE_SCHEMA_VERSION  # 不改 done 协议
    assert done["report_path"] and Path(done["report_path"]).is_file()
    assert done["report_path"].startswith(str(reports_dir))
    assert list(reports_dir.glob("admin-record-*")) == []


def test_real_record_validation_failure_keeps_report(tmp_path: Path):
    """坏 report（未知版本）经真实 records 校验失败：报告保留、回执降级、不落盘。"""
    records_dir = tmp_path / "records"
    calls: list[tuple] = []
    bad = _valid_report()
    bad["schema_version"] = "0.9"
    got: list[dict] = []

    deps = launcher.default_deps(records_dir=str(records_dir))
    got_path = launcher.execute_audit(
        r"C:\scope", deps=_deps(calls, report=bad, record=deps.record), on_record=got.append
    )

    assert got_path == r"C:\reports\report-1.html"
    assert got[0]["saved"] is False
    assert got[0]["record_id"] is None
    assert "旧记录不可比" in got[0]["error"]
    assert not records_dir.exists() or list(records_dir.glob("*.json")) == []


def test_real_record_unsafe_root_degrades_without_writing(tmp_path: Path):
    """records 根不是目录（被占用为文件）→ 真实 RecordError 降级，不覆盖该文件。"""
    blocker = tmp_path / "records-as-file"
    blocker.write_text("occupied", encoding="utf-8")

    deps = launcher.default_deps(records_dir=str(blocker))
    got: list[dict] = []
    got_path = launcher.execute_audit(
        r"C:\scope", deps=_deps([], record=deps.record), on_record=got.append
    )

    assert got_path == r"C:\reports\report-1.html"
    assert got[0]["saved"] is False and got[0]["record_id"] is None
    assert blocker.read_text(encoding="utf-8") == "occupied"
    assert list(tmp_path.glob("*.json")) == []


# ---------------------------------------------------------------------------
# T5-02-A-R1：记录调用计数见证（零调用断言必须真能看到调用）
# ---------------------------------------------------------------------------


class _RecordCounter:
    """可调用记录环替身：真实累计调用次数与入参，供零调用/恰一次断言。"""

    def __init__(self, record_id: str = "record-counted") -> None:
        self.calls = 0
        self.reports: list[dict] = []
        self.record_id = record_id

    def __call__(self, report: dict) -> str:
        self.calls += 1
        self.reports.append(report)
        return self.record_id


def test_incomplete_never_calls_record_counter():
    counter = _RecordCounter()
    launcher.execute_audit(
        r"C:\scope", deps=_deps([], scan_result={"incomplete": True}, record=counter)
    )
    assert counter.calls == 0


def test_scan_failure_never_calls_record_counter():
    counter = _RecordCounter()
    deps = _deps([], record=counter)

    def scan(path: str, progress_cb=None, abort_check=None):
        raise RuntimeError("scan-boom")

    object.__setattr__(deps, "scan", scan)
    with pytest.raises(RuntimeError, match="scan-boom"):
        launcher.execute_audit(r"C:\scope", deps=deps)
    assert counter.calls == 0


def test_judge_failure_never_calls_record_counter():
    counter = _RecordCounter()
    deps = _deps([], record=counter)

    def judge(scan_data: dict) -> dict:
        raise RuntimeError("judge-boom")

    object.__setattr__(deps, "judge", judge)
    with pytest.raises(RuntimeError, match="judge-boom"):
        launcher.execute_audit(r"C:\scope", deps=deps)
    assert counter.calls == 0


def test_render_failure_never_calls_record_counter():
    counter = _RecordCounter()
    deps = _deps([], record=counter)

    def render(report: dict) -> str:
        raise RuntimeError("render-boom")

    object.__setattr__(deps, "render", render)
    with pytest.raises(RuntimeError, match="render-boom"):
        launcher.execute_audit(r"C:\scope", deps=deps)
    assert counter.calls == 0


def test_save_failure_never_calls_record_counter():
    counter = _RecordCounter()
    deps = _deps([], record=counter, save_error=OSError("save-boom"))
    with pytest.raises(OSError, match="save-boom"):
        launcher.execute_audit(r"C:\scope", deps=deps)
    assert counter.calls == 0


def test_cooperative_abort_never_calls_record_counter():
    """协作式中止（stop 已置位 → scan 返回 incomplete）不得落记录。"""
    counter = _RecordCounter()
    stop = threading.Event()
    stop.set()
    pending: list = []

    def scan(path: str, progress_cb=None, abort_check=None):
        assert abort_check is not None and abort_check() is True
        return {"incomplete": True, "root": path}

    deps = launcher.AuditDeps(
        scan=scan,
        judge=lambda scan_data: _valid_report(),
        render=lambda report: "<html></html>",
        save=lambda html: r"C:\reports\report-1.html",
        prune=lambda: [],
        open=lambda path: None,
        record=counter,
    )
    thread = launcher.run_audit_async(
        r"C:\scope",
        deps=deps,
        stop=stop,
        after=pending.append,
        on_progress=lambda event: None,
        on_complete=lambda path: None,
        on_error=lambda exc: None,
        on_record=lambda payload: None,
    )
    thread.join(5)
    assert not thread.is_alive()
    for callback in list(pending):
        callback()
    assert counter.calls == 0


# ---------------------------------------------------------------------------
# T5-02-A-R1：真实延期 after 队列（主线程逐条执行）
# ---------------------------------------------------------------------------


def _run_queued(deps, *, on_record, on_complete=None, on_error=None):
    """after 只排队（模拟 Tk）：worker 结束后由调用方在主线程逐条执行。"""
    pending: list = []
    thread = launcher.run_audit_async(
        r"C:\scope",
        deps=deps,
        stop=threading.Event(),
        after=pending.append,
        on_progress=lambda event: None,
        on_complete=on_complete if on_complete is not None else (lambda path: None),
        on_error=on_error if on_error is not None else (lambda exc: None),
        on_record=on_record,
    )
    thread.join(5)
    assert not thread.is_alive()
    return pending


def test_deferred_record_success_exactly_once_on_main_thread():
    ui: list = []
    completed: list = []
    main_thread = threading.get_ident()
    pending = _run_queued(
        _deps([], record=lambda r: "record-1"),
        on_record=lambda payload: ui.append((threading.get_ident(), payload["saved"])),
        on_complete=completed.append,
    )
    assert ui == [] and completed == []  # worker 只排队，不直接碰 UI
    for callback in list(pending):
        callback()
    assert ui == [(main_thread, True)]
    assert completed == [r"C:\reports\report-1.html"]


def test_deferred_record_failure_notification_exactly_once_on_main_thread():
    ui: list = []
    completed: list = []
    main_thread = threading.get_ident()

    def record(report: dict) -> str:
        raise records.RecordWriteError("写失败")

    pending = _run_queued(
        _deps([], record=record),
        on_record=lambda payload: ui.append(
            (threading.get_ident(), payload["saved"], payload["record_id"], payload["error"])
        ),
        on_complete=completed.append,
    )
    for callback in list(pending):
        callback()
    assert ui == [(main_thread, False, None, "写失败")]
    assert completed == [r"C:\reports\report-1.html"]


def test_deferred_on_record_error_does_not_escape_nor_block_complete():
    """回归（R1 缺陷）：延期执行的 on_record 抛普通异常不得漏给调度者/驱动者。"""
    completed: list = []
    pending = _run_queued(
        _deps([], record=lambda r: "record-1"),
        on_record=lambda payload: (_ for _ in ()).throw(RuntimeError("通知坏")),
        on_complete=completed.append,
    )
    for callback in list(pending):
        callback()  # 不应抛出
    assert completed == [r"C:\reports\report-1.html"]


def test_deferred_on_record_error_after_record_failure_does_not_escape():
    completed: list = []

    def record(report: dict) -> str:
        raise records.RecordWriteError("写失败")

    pending = _run_queued(
        _deps([], record=record),
        on_record=lambda payload: (_ for _ in ()).throw(RuntimeError("通知坏-失败路径")),
        on_complete=completed.append,
    )
    for callback in list(pending):
        callback()
    assert completed == [r"C:\reports\report-1.html"]


def test_deferred_on_record_base_exception_sentinel_not_swallowed():
    pending = _run_queued(
        _deps([], record=lambda r: "record-1"),
        on_record=lambda payload: (_ for _ in ()).throw(_SentinelAbort("sentinel")),
    )
    with pytest.raises(_SentinelAbort):
        for callback in list(pending):
            callback()


# ---------------------------------------------------------------------------
# T5-02-A-R1：普通 / admin 真实临时 HTML + JSON 联动
# ---------------------------------------------------------------------------


def _real_deps(reports_dir: Path, records_dir: Path, report: dict, html: str):
    import dataclasses

    base = launcher.default_deps(reports_dir=str(reports_dir), records_dir=str(records_dir))
    return dataclasses.replace(
        base,
        scan=lambda path, progress_cb=None, abort_check=None: {
            "root": path, "entries": 0, "skipped": {}, "units": []
        },
        judge=lambda scan_data: report,
        render=lambda r: html,
    )


def test_normal_execute_audit_writes_real_html_and_record(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    records_dir = tmp_path / "records"
    report = _valid_report()
    before = copy.deepcopy(report)
    deps = _real_deps(reports_dir, records_dir, report, "<html>normal-real</html>")

    got = launcher.execute_audit(r"C:\scope", deps=deps)

    html_path = Path(got)
    assert html_path.is_file()
    assert html_path.read_text(encoding="utf-8") == "<html>normal-real</html>"
    ids = sorted(p.stem for p in records_dir.glob("*.json"))
    assert len(ids) == 1 and ids[0].startswith("record-")
    assert records.read_record(ids[0], records_dir=str(records_dir)) == before
    assert report == before


def test_admin_execute_audit_writes_real_admin_html_and_record(tmp_path: Path):
    import dataclasses

    reports_dir = tmp_path / "reports"
    records_dir = tmp_path / "records"
    report = _valid_report(admin=True)
    base = launcher._elevated_deps(reports_dir=str(reports_dir), records_dir=str(records_dir))
    deps = dataclasses.replace(
        base,
        scan=lambda path, progress_cb=None, abort_check=None: {
            "root": path, "entries": 0, "skipped": {}, "units": []
        },
        judge=lambda scan_data: report,
        render=lambda r: "<html>admin-real</html>",
    )

    got = launcher.execute_audit(r"C:\scope", deps=deps)

    html_path = Path(got)
    assert html_path.is_file() and html_path.name.startswith("admin-")
    assert html_path.read_text(encoding="utf-8") == "<html>admin-real</html>"
    ids = sorted(p.stem for p in records_dir.glob("*.json"))
    assert len(ids) == 1 and ids[0].startswith("admin-record-")
    stored = records.read_record(ids[0], records_dir=str(records_dir))
    assert stored["admin_mode"] is True


# ---------------------------------------------------------------------------
# T5-02-A-R1：记录失败时真实 HTML 清单/字节/hash 保留、无记录残留
# ---------------------------------------------------------------------------


def test_record_failure_preserves_real_html_bytes_and_leaves_no_record(tmp_path: Path):
    import hashlib

    reports_dir = tmp_path / "reports"
    occupied = tmp_path / "records-occupied"
    occupied.write_text("occupied", encoding="utf-8")
    deps = _real_deps(reports_dir, occupied, _valid_report(), "<html>keep-me</html>")
    # records_dir 指向已存在文件：真实 RecordError（根不是目录），不会创建目录/文件。

    got = launcher.execute_audit(r"C:\scope", deps=deps)

    html_path = Path(got)
    assert html_path.is_file()
    body = html_path.read_bytes()
    assert body == b"<html>keep-me</html>"
    digest = hashlib.sha256(body).hexdigest()
    # 第二次失败运行也只是新增报告文件，不改既有 HTML 字节；这里校验清单与 hash 稳定。
    files = sorted(p.name for p in reports_dir.glob("*"))
    assert files == [html_path.name]
    assert hashlib.sha256(html_path.read_bytes()).hexdigest() == digest
    assert occupied.read_text(encoding="utf-8") == "occupied"
    assert list(tmp_path.rglob("*.json")) == []
    assert list(tmp_path.rglob(".tmp-record-*")) == []
