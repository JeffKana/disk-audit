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


def test_record_base_exception_is_not_swallowed():
    calls: list[tuple] = []

    def record(report: dict) -> str:
        raise KeyboardInterrupt("不可吞")

    with pytest.raises(KeyboardInterrupt):
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
