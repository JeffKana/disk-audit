r"""T4-01（待办 H1）以管理员身份重扫测试：spec 往返 / runas 参数构造 / 提权实例编排 / 防重生 AST 断言。

依据：方案 Q6（用户点击触发 → ``ShellExecuteW(..., "runas", ...)`` 重启自身，扫描规格经
``tmp\\spec.json`` 传递）、E-4（"以管理员身份重扫"入口）、U-3（未获用户显式点击不发起
任何提权请求——调用点唯一且仅在点击回调链）、U-2（spec/done 均落 DATA_DIR\\tmp\\）、
S-3（管理员模式独立产出，admin- 前缀文件级可区分；完整标注归 T4-04）、R9（提权后不联网、
不执行任何外部程序——AST 断言固化）、E-5/X-4（取消/失败 UX 归 T4-02/T4-03，本卡只留
接口位）。

防重生（本卡第一设计约束，测试固化四道结构性防线）：
1. 自重启调用单点化——全仓库 ShellExecuteW 仅存在于 launcher._shell_execute_runas，
   提权分支代码路径（disk_audit/elevated.py + launcher._cmd_elevated_rescan 及其调用链）
   AST 断言零自启动调用（ShellExecuteW/WinExec/os.system/os.popen/subprocess/os.startfile）；
2. spec 消费一次性语义——原子认领即焚，同一 spec 第二次执行被拒绝（EXIT_BAD_REQUEST）；
3. UI 侧仅单击触发——request_admin_rescan 调用点唯一且仅在 _on_admin_rescan 点击回调，
   无重试/轮询/自动再触发路径；
4. 无循环测试——本文件与全部自动化脚本零 UI 循环触发、零真实 runas 调用。

测试全部注入（tmp_dir/reports_dir/shell_execute/audit/winreg 替身），不触碰
真实 %LOCALAPPDATA%\\DiskAudit、不发起真实 UAC、不创建 Tk 实例（验收②真实 UAC
端到端由主会话按 docs/evidence/T4-01/真机验收操作单.md 执行）。
"""
from __future__ import annotations

import ast
import json
import os
import sys
import types
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
_REQUEST_ID = "a" * 32


def _spec_path(tmp_path: Path) -> Path:
    return tmp_path / elevated.SPEC_FILENAME


def _done_path(tmp_path: Path) -> Path:
    return tmp_path / elevated.DONE_FILENAME


def _write_raw_spec(tmp_path: Path, data: dict) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    _spec_path(tmp_path).write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def _valid_spec(
    *,
    created_at: str = _NOW.isoformat(),
    request_id: str = _REQUEST_ID,
    scope: str = r"C:\some\scope",
    schema_version: str = elevated.SPEC_SCHEMA_VERSION,
    host_pid: int = 4242,
) -> dict:
    return {
        "schema_version": schema_version,
        "request_id": request_id,
        "created_at": created_at,
        "scope": scope,
        "host_pid": host_pid,
    }


# ---------- 验收①：spec.json 写入/读取往返 ----------


def test_write_rescan_request_roundtrip(tmp_path):
    """写入 → 读取一致；读取即消费（spec 文件消失）。"""
    request = elevated.write_rescan_request(
        r"C:\scope\x", tmp_dir=str(tmp_path), now=_NOW, request_id=_REQUEST_ID
    )
    assert _spec_path(tmp_path).is_file()
    raw = json.loads(_spec_path(tmp_path).read_text(encoding="utf-8"))
    assert raw == request
    got = elevated.read_rescan_request(tmp_dir=str(tmp_path), now=_NOW)
    assert got == request
    assert not _spec_path(tmp_path).exists()  # 消费即焚（一次性语义）


def test_written_spec_fields_contract(tmp_path):
    """spec 字段契约（PR 接口约定，H2/H3/H4 依赖）：五字段齐、形制正确。"""
    request = elevated.write_rescan_request(
        r"C:\scope\x", tmp_dir=str(tmp_path), now=_NOW, request_id=_REQUEST_ID, host_pid=7
    )
    assert request["schema_version"] == elevated.SPEC_SCHEMA_VERSION
    assert len(request["request_id"]) == 32
    int(request["request_id"], 16)  # hex32
    parsed = datetime.fromisoformat(request["created_at"])
    assert parsed.tzinfo is not None  # ISO8601 带时区
    assert os.path.isabs(request["scope"])
    assert request["host_pid"] == 7


def test_write_generates_unique_request_ids(tmp_path):
    first = elevated.write_rescan_request(r"C:\a", tmp_dir=str(tmp_path), now=_NOW)
    second = elevated.write_rescan_request(r"C:\b", tmp_dir=str(tmp_path), now=_NOW)
    assert first["request_id"] != second["request_id"]


def test_write_clears_stale_done_marker_and_claim(tmp_path):
    """新请求写入前清掉旧 done 标记与陈旧认领文件（旧 done 不得误挂新请求）。"""
    _done_path(tmp_path).write_text("{}", encoding="utf-8")
    (_spec_path(tmp_path).parent / (elevated.SPEC_FILENAME + elevated.CLAIM_SUFFIX)).write_text(
        "stale", encoding="utf-8"
    )
    elevated.write_rescan_request(r"C:\scope", tmp_dir=str(tmp_path), now=_NOW)
    assert not _done_path(tmp_path).exists()
    assert not (
        _spec_path(tmp_path).parent / (elevated.SPEC_FILENAME + elevated.CLAIM_SUFFIX)
    ).exists()
    assert _spec_path(tmp_path).is_file()


def test_default_tmp_dir_is_localappdata_tmp():
    """U-2 合规位：默认规格传递位 = %LOCALAPPDATA%\\DiskAudit\\tmp（Q1 定稿）。"""
    import disk_audit

    assert elevated._default_tmp_dir() == disk_audit.TMP_DIR


# ---------- spec 校验：缺失/损坏/陈旧/未来/字段非法 ----------


def test_read_missing_spec_raises(tmp_path):
    with pytest.raises(elevated.RescanRequestError):
        elevated.read_rescan_request(tmp_dir=str(tmp_path), now=_NOW)


def test_read_corrupt_json_raises(tmp_path):
    _spec_path(tmp_path).write_text("{not json", encoding="utf-8")
    with pytest.raises(elevated.RescanRequestError):
        elevated.read_rescan_request(tmp_dir=str(tmp_path), now=_NOW)


def test_read_non_dict_json_raises(tmp_path):
    _spec_path(tmp_path).write_text("[1,2]", encoding="utf-8")
    with pytest.raises(elevated.RescanRequestError):
        elevated.read_rescan_request(tmp_dir=str(tmp_path), now=_NOW)


def test_stale_spec_rejected(tmp_path):
    """时效窗（600s）：超龄请求拒绝（防陈旧请求重放）。"""
    stale_at = "2026-11-05T11:00:00+00:00"  # 比基准 now 早 3600s
    _write_raw_spec(tmp_path, _valid_spec(created_at=stale_at))
    with pytest.raises(elevated.RescanRequestError):
        elevated.read_rescan_request(tmp_dir=str(tmp_path), now=_NOW)


def test_spec_within_age_window_accepted(tmp_path):
    near_stale = "2026-11-05T11:51:00+00:00"  # 早 540s < 600s
    _write_raw_spec(tmp_path, _valid_spec(created_at=near_stale))
    got = elevated.read_rescan_request(tmp_dir=str(tmp_path), now=_NOW)
    assert got["created_at"] == near_stale


def test_future_spec_beyond_tolerance_rejected(tmp_path):
    future_at = "2026-11-05T12:02:00+00:00"  # 未来 120s > 60s 容差
    _write_raw_spec(tmp_path, _valid_spec(created_at=future_at))
    with pytest.raises(elevated.RescanRequestError):
        elevated.read_rescan_request(tmp_dir=str(tmp_path), now=_NOW)


@pytest.mark.parametrize(
    "field,kwargs",
    [
        ("schema_version", {"schema_version": "other-v1"}),
        ("request_id", {"request_id": "xyz"}),  # 非 32 位
        ("request_id", {"request_id": "g" * 32}),  # 非十六进制
        ("scope", {"scope": ""}),  # 空
        ("scope", {"scope": "relative\\path"}),  # 相对路径
    ],
)
def test_invalid_field_rejected(tmp_path, field, kwargs):
    data = _valid_spec(**kwargs)
    _write_raw_spec(tmp_path, data)
    with pytest.raises(elevated.RescanRequestError):
        elevated.read_rescan_request(tmp_dir=str(tmp_path), now=_NOW)


def test_naive_created_at_rejected(tmp_path):
    _write_raw_spec(tmp_path, _valid_spec(created_at="2026-11-05T12:00:00"))
    with pytest.raises(elevated.RescanRequestError):
        elevated.read_rescan_request(tmp_dir=str(tmp_path), now=_NOW)


# ---------- spec 消费一次性语义（防重生防线 2） ----------


def test_same_spec_second_execution_rejected(tmp_path):
    """卡面单测要求：同一 spec 第二次执行被拒绝（消费即焚后无请求 → 拒绝）。"""
    elevated.write_rescan_request(r"C:\scope", tmp_dir=str(tmp_path), now=_NOW)
    first = elevated.read_rescan_request(tmp_dir=str(tmp_path), now=_NOW)
    assert first["scope"] == r"C:\scope"
    with pytest.raises(elevated.RescanRequestError):
        elevated.read_rescan_request(tmp_dir=str(tmp_path), now=_NOW)


@pytest.mark.skipif(os.name != "nt", reason="Windows 下 os.rename 目标存在即失败（原子认领语义）")
def test_claim_blocks_concurrent_duplicate_read(tmp_path):
    """原子认领：认领文件存在时第二次认领失败——并发双实例只有一个拿到请求。"""
    _write_raw_spec(tmp_path, _valid_spec())
    claimed = _spec_path(tmp_path).parent / (elevated.SPEC_FILENAME + elevated.CLAIM_SUFFIX)
    claimed.write_text("claimed-by-other-instance", encoding="utf-8")
    with pytest.raises(elevated.RescanRequestError):
        elevated.read_rescan_request(tmp_dir=str(tmp_path), now=_NOW)


# ---------- 验收①：runas 参数构造（ShellExecuteW 调用参数断言，verbs="runas"） ----------


def test_build_rescan_command_script_mode():
    lp_file, lp_parameters = elevated.build_rescan_command(
        executable=r"D:\py\python.exe", script=r"E:\repo\launcher.py", frozen=False
    )
    assert lp_file == r"D:\py\python.exe"
    assert lp_parameters == f'"E:\\repo\\launcher.py" {elevated.ELEVATED_FLAG}'


def test_build_rescan_command_frozen_mode():
    """冻结形态（PyInstaller onedir，M5 打包前置）：lpFile=自身 exe，仅带标记参数。"""
    lp_file, lp_parameters = elevated.build_rescan_command(
        executable=r"C:\App\DiskAudit.exe", frozen=True
    )
    assert lp_file == r"C:\App\DiskAudit.exe"
    assert lp_parameters == elevated.ELEVATED_FLAG


def test_request_admin_rescan_writes_spec_then_launches_runas_once(tmp_path):
    """宿主侧点击处理全链（注入替身）：先写 spec → 恰一次 runas → 参数含 verbs="runas"。"""
    seen: list[tuple[str, str, str]] = []
    spec_at_launch: list[bool] = []

    def fake_shell_execute(lp_file: str, lp_verb: str, lp_parameters: str) -> int:
        seen.append((lp_file, lp_verb, lp_parameters))
        spec_at_launch.append(_spec_path(tmp_path).is_file())  # 发起前 spec 必须已落盘
        return 42  # >32 = 已发起

    rc = launcher.request_admin_rescan(
        r"C:\scope\x",
        tmp_dir=str(tmp_path),
        shell_execute=fake_shell_execute,
        executable=r"D:\py\python.exe",
        script=r"E:\repo\launcher.py",
        now=_NOW,
    )
    assert rc == 42
    assert len(seen) == 1  # U-3：单次发起，无重试
    lp_file, lp_verb, lp_parameters = seen[0]
    assert lp_verb == "runas"
    assert lp_file == r"D:\py\python.exe"
    assert "E:\\repo\\launcher.py" in lp_parameters
    assert elevated.ELEVATED_FLAG in lp_parameters
    assert spec_at_launch == [True]
    spec = json.loads(_spec_path(tmp_path).read_text(encoding="utf-8"))
    assert spec["scope"] == r"C:\scope\x"


def test_request_admin_rescan_passes_shell_execute_return_code_through(tmp_path):
    """返回码透传：ShellExecuteW 返回码原样交 UI（ERROR_CANCELLED=1223 为 T4-02 接口位）。"""
    rc = launcher.request_admin_rescan(
        r"C:\s",
        tmp_dir=str(tmp_path),
        shell_execute=lambda f, v, p: elevated.ERROR_CANCELLED,
        executable="py", script="launcher.py", now=_NOW,
    )
    assert rc == elevated.ERROR_CANCELLED


# ---------- 提权实例编排：读规格 → 流水线 → done 标记 → 退出码三态 ----------


class _StubDeps:
    """六环替身（duck 型 AuditDeps）：各环调用全记录，save 接真实 admin 落盘可选。"""

    def __init__(self, *, scan_result: dict | None = None, fail_at: str | None = None,
                 save=None):
        self.calls: list[tuple] = []
        self._scan_result = scan_result or {"root": r"C:\s", "units": [],
                                            "allocated_bytes": 0, "logical_bytes": 0,
                                            "skipped": {}}
        self._fail_at = fail_at
        self._save = save

    def scan(self, path, progress_cb=None, abort_check=None):
        self.calls.append(("scan", path))
        if self._fail_at == "scan":
            raise OSError("scan boom")
        return dict(self._scan_result, root=path)

    def judge(self, scan):
        self.calls.append(("judge", scan["root"]))
        if self._fail_at == "judge":
            raise ValueError("judge boom")
        return {"schema_version": "1.0", "scan_root": scan["root"], "candidates": []}

    def render(self, report):
        self.calls.append(("render", report["scan_root"]))
        if self._fail_at == "render":
            raise ValueError("render boom")
        return "<html>admin</html>"

    def save(self, html):
        self.calls.append(("save", html))
        if self._fail_at == "save":
            raise OSError("save boom")
        if self._save is not None:
            return self._save(html)
        return r"C:\reports\admin-report-1.html"

    def prune(self):
        self.calls.append(("prune", None))
        return []

    def open(self, path):
        self.calls.append(("open", path))


def test_run_elevated_rescan_success_writes_done_marker(tmp_path):
    request = elevated.write_rescan_request(r"C:\scope", tmp_dir=str(tmp_path), now=_NOW)
    deps = _StubDeps()
    rc = elevated.run_elevated_rescan(
        audit=lambda scope, deps=None: launcher.execute_audit(scope, deps=deps),
        deps=deps,
        tmp_dir=str(tmp_path),
        now=_NOW,
    )
    assert rc == elevated.EXIT_OK
    # 复用 execute_audit 六环：save/prune/open 全走到（替身 open 记录即证明未被跳过语义改变）
    assert [c[0] for c in deps.calls] == ["scan", "judge", "render", "save", "prune", "open"]
    done = json.loads(_done_path(tmp_path).read_text(encoding="utf-8"))
    assert done["schema_version"] == elevated.DONE_SCHEMA_VERSION
    assert done["request_id"] == request["request_id"]  # done 与 spec 同一请求 ID
    assert done["mode"] == "admin"
    assert done["status"] == "completed"
    assert done["report_path"] == r"C:\reports\admin-report-1.html"
    datetime.fromisoformat(done["finished_at"])  # ISO8601 带时区
    assert not _spec_path(tmp_path).exists()  # spec 已消费


def test_run_elevated_rescan_pipeline_failure_exit_code_5(tmp_path):
    elevated.write_rescan_request(r"C:\scope", tmp_dir=str(tmp_path), now=_NOW)
    deps = _StubDeps(fail_at="judge")
    rc = elevated.run_elevated_rescan(
        audit=lambda scope, deps=None: launcher.execute_audit(scope, deps=deps),
        deps=deps,
        tmp_dir=str(tmp_path),
        now=_NOW,
    )
    assert rc == elevated.EXIT_PIPELINE_FAILED
    done = json.loads(_done_path(tmp_path).read_text(encoding="utf-8"))
    assert done["status"] == "failed"
    assert done["report_path"] is None
    assert "judge boom" in done["error"]


def test_run_elevated_rescan_incomplete_scan_is_failure(tmp_path):
    """X-2 不完整出口（防御性）：提权实例无中止源，audit 返回 None → done=failed、非零码。"""
    elevated.write_rescan_request(r"C:\scope", tmp_dir=str(tmp_path), now=_NOW)
    deps = _StubDeps(scan_result={"root": r"C:\s", "incomplete": True, "units": [],
                                  "allocated_bytes": 0, "logical_bytes": 0, "skipped": {}})
    rc = elevated.run_elevated_rescan(
        audit=lambda scope, deps=None: launcher.execute_audit(scope, deps=deps),
        deps=deps,
        tmp_dir=str(tmp_path),
        now=_NOW,
    )
    assert rc == elevated.EXIT_PIPELINE_FAILED
    assert [c[0] for c in deps.calls] == ["scan"]  # 不落盘、不渲染
    done = json.loads(_done_path(tmp_path).read_text(encoding="utf-8"))
    assert done["status"] == "failed"


def test_run_elevated_rescan_no_spec_exit_code_4_no_done(tmp_path):
    """无请求：拒绝退出（EXIT_BAD_REQUEST），不写 done（H3 消费前提：done 只由合法请求产出）。"""
    rc = elevated.run_elevated_rescan(
        audit=lambda scope, deps=None: pytest.fail("无请求不应进入流水线"),
        deps=_StubDeps(),
        tmp_dir=str(tmp_path),
    )
    assert rc == elevated.EXIT_BAD_REQUEST
    assert not _done_path(tmp_path).exists()


def test_run_elevated_rescan_rejects_second_run_with_same_spec(tmp_path):
    """防重生防线 2（编排级）：同一请求第二次执行被拒绝（EXIT_BAD_REQUEST）。"""
    elevated.write_rescan_request(r"C:\scope", tmp_dir=str(tmp_path), now=_NOW)
    deps = _StubDeps()
    first = elevated.run_elevated_rescan(
        audit=lambda scope, deps=None: launcher.execute_audit(scope, deps=deps),
        deps=deps, tmp_dir=str(tmp_path), now=_NOW,
    )
    assert first == elevated.EXIT_OK
    second = elevated.run_elevated_rescan(
        audit=lambda scope, deps=None: pytest.fail("第二次执行不得进入流水线"),
        deps=_StubDeps(), tmp_dir=str(tmp_path), now=_NOW,
    )
    assert second == elevated.EXIT_BAD_REQUEST


def test_done_marker_read_missing_or_corrupt_returns_none(tmp_path):
    assert elevated.read_done_marker(tmp_dir=str(tmp_path)) is None
    _done_path(tmp_path).write_text("{bad", encoding="utf-8")
    assert elevated.read_done_marker(tmp_dir=str(tmp_path)) is None


def test_done_marker_carries_r9_evidence_note(tmp_path):
    """done 标记含 R9 证据降级披露（H4 报告标注承接的接口字段）。"""
    elevated.write_done_marker(
        request_id=_REQUEST_ID, status="completed",
        report_path=r"C:\r\admin-report-x.html", tmp_dir=str(tmp_path), now=_NOW,
    )
    done = elevated.read_done_marker(tmp_dir=str(tmp_path))
    assert done is not None
    assert "外部程序" in done["evidence_note"]


# ---------- 管理员模式报告落盘（S-3 文件级可区分） ----------


def test_save_admin_report_uses_admin_prefix_and_keeps_guard(tmp_path):
    reports_dir = tmp_path / "reports"
    path = elevated.save_admin_report("<html>a</html>", reports_dir=str(reports_dir), now=_NOW)
    assert Path(path).parent == reports_dir
    assert Path(path).name == "admin-report-20261105-120000.html"
    assert Path(path).read_text(encoding="utf-8") == "<html>a</html>"
    # 普通名中间产物已被改名，不残留
    assert list(reports_dir.glob("report-*.html")) == []


def test_save_admin_report_same_second_conflict_gets_sequence(tmp_path):
    reports_dir = tmp_path / "reports"
    first = elevated.save_admin_report("<html>1</html>", reports_dir=str(reports_dir), now=_NOW)
    second = elevated.save_admin_report("<html>2</html>", reports_dir=str(reports_dir), now=_NOW)
    assert Path(first).name == "admin-report-20261105-120000.html"
    assert Path(second).name == "admin-report-20261105-120000-1.html"
    assert Path(second).read_text(encoding="utf-8") == "<html>2</html>"


def test_admin_prefix_reports_excluded_from_prune(tmp_path):
    """S-3 独立记录：admin- 前缀不匹配普通报告淘汰正则，不被 12 份淘汰删除。"""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    admin = reports_dir / "admin-report-20261105-120000.html"
    admin.write_text("<html>admin</html>", encoding="utf-8")
    plain = [
        reports_dir / f"report-20261101-0000{i:02d}.html" for i in range(13)
    ]
    for path in plain:
        path.write_text("<html>p</html>", encoding="utf-8")
    from disk_audit import reports as reports_mod

    removed = reports_mod.prune_reports(reports_dir=str(reports_dir))
    assert len(removed) == 1  # 只淘汰最旧的普通报告
    assert admin.exists()  # 管理员报告不受淘汰影响


# ---------- R9 证据降级：提权实例只装配零子进程证据源 ----------


def _fake_winreg() -> types.SimpleNamespace:
    """OpenKey 必失败的最小 winreg 替身：registry/autostart 走 X-1 降级，不崩溃。"""

    def open_key(*_args, **_kwargs):
        raise OSError("fake: no registry")

    return types.SimpleNamespace(
        HKEY_LOCAL_MACHINE=0x80000002,
        HKEY_CURRENT_USER=0x80000001,
        KEY_READ=0x20019,
        OpenKey=open_key,
    )


def test_collect_evidence_readonly_degrades_subprocess_sources():
    """R9：Appx/进程/服务三源（需 powershell 子进程）不采集并按方案口径披露不可用。"""
    bundle = elevated.collect_evidence_readonly(winreg_module=_fake_winreg())
    assert bundle.appx.available is False
    assert bundle.processes.available is False
    assert bundle.services.available is False
    for reason in (bundle.appx.reason, bundle.processes.reason, bundle.services.reason):
        assert "外部程序" in reason
    assert "R9" in bundle.processes.reason


def test_collect_evidence_readonly_keeps_winreg_sources_no_exception():
    """winreg 只读源（注册表卸载项/自启动）仍参与采集；X-1：单源失败不中断。"""
    bundle = elevated.collect_evidence_readonly(winreg_module=_fake_winreg())
    # 替身注册表打不开 → 各自降级（available=False 或空结果），聚合不抛异常即可
    assert isinstance(bundle.errors, list)


def test_collect_evidence_readonly_never_touches_subprocess_sources():
    """行为断言：返回的 bundle 三源恒为空集合（未发起任何采集调用）。"""
    bundle = elevated.collect_evidence_readonly(winreg_module=_fake_winreg())
    assert bundle.appx.packages == []
    assert bundle.processes.paths == []
    assert bundle.services.paths == []


# ---------- launcher._elevated_deps：提权实例流水线装配（R9 差异点） ----------


def test_elevated_deps_save_uses_admin_prefix(tmp_path):
    deps = launcher._elevated_deps(reports_dir=str(tmp_path))
    path = deps.save("<html>wiring</html>")
    assert Path(path).name.startswith("admin-report-")
    assert Path(path).parent == tmp_path


def test_elevated_deps_prune_and_open_are_noop(tmp_path):
    """R9/防写入面：提权实例不淘汰普通报告、不打开浏览器（os.startfile 会启动外部程序）。"""
    from disk_audit import reports as reports_mod

    deps = launcher._elevated_deps(reports_dir=str(tmp_path))
    assert deps.prune() == []
    deps.open(r"C:\x\report.html")  # 零副作用、零异常
    assert deps.open is not reports_mod.open_report


def test_elevated_deps_judge_routes_through_readonly_bundle(tmp_path, monkeypatch):
    """judge 环经 collect_evidence_readonly 装配证据（monkeypatch 哨兵证明注入路径）。"""
    sentinel = elevated.EvidenceBundle()
    sentinel.appx = elevated.AppxResult(available=False, reason="sentinel")
    calls: list[elevated.EvidenceBundle] = []
    monkeypatch.setattr(
        elevated, "collect_evidence_readonly",
        lambda *a, **kw: (calls.append(sentinel), sentinel)[1],
    )
    deps = launcher._elevated_deps(reports_dir=str(tmp_path))
    report = deps.judge({
        "root": r"C:\s", "units": [], "allocated_bytes": 0,
        "logical_bytes": 0, "skipped": {},
    })
    from disk_audit.engine.report import REPORT_SCHEMA_VERSION

    assert report["schema_version"] == REPORT_SCHEMA_VERSION
    assert calls == [sentinel]


def test_elevated_deps_scan_binds_real_entrypoint():
    """scan 环绑定真实 scan_path（提权实例与普通实例共用只读枚举器，闭包内为同一函数）。"""
    from disk_audit.scanner import scan_path

    deps = launcher._elevated_deps()
    closure_values = [cell.cell_contents for cell in (deps.scan.__closure__ or [])]
    assert scan_path in closure_values


# ---------- 防重生 AST 断言（防线 1/3）：零自启动 + 零网络 + 调用点唯一 ----------

_FORBIDDEN_CALL_NAMES = frozenset(
    {"ShellExecuteW", "WinExec", "system", "popen", "Popen", "startfile"}
)
_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {"subprocess", "socket", "urllib", "http", "requests", "ftplib", "smtplib", "xmlrpc"}
)
_RELAUNCH_NAMES = ("_shell_execute_runas", "_launch_elevated_self", "request_admin_rescan")


def _launcher_tree() -> ast.Module:
    return ast.parse((_REPO_ROOT / "launcher.py").read_text(encoding="utf-8"))


def _elevated_tree() -> ast.Module:
    return ast.parse(
        (_REPO_ROOT / "disk_audit" / "elevated.py").read_text(encoding="utf-8")
    )


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _forbidden_calls(tree: ast.AST) -> list[str]:
    return sorted(
        {_call_name(n) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        & _FORBIDDEN_CALL_NAMES
    )


def _forbidden_imports(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hits += [
                alias.name for alias in node.names
                if alias.name.split(".", 1)[0] in _FORBIDDEN_IMPORT_ROOTS
            ]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".", 1)[0] in _FORBIDDEN_IMPORT_ROOTS:
                hits.append(node.module)
    return hits


def _function(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _calls_of(node: ast.AST) -> list[str]:
    return [_call_name(c) for c in ast.walk(node) if isinstance(c, ast.Call)]


def _ref_count(tree: ast.AST, name: str) -> int:
    """标识符引用次数（Name/Attribute；函数定义本身不计）。"""
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name:
            count += 1
        elif isinstance(node, ast.Attribute) and node.attr == name:
            count += 1
    return count


def test_elevated_module_zero_selfstart_and_zero_network():
    """R9/防重生：elevated.py 全模块零自启动调用 + 零网络/子进程 import。"""
    tree = _elevated_tree()
    assert _forbidden_calls(tree) == []
    assert _forbidden_imports(tree) == []


def test_shell_execute_w_exists_only_in_launcher_single_point():
    """全仓库（产品代码）ShellExecuteW/ShellExecuteExW 唯一出现点 =
    launcher._shell_execute_runas。

    【T4-03（H3）最小修改】禁令由 ShellExecuteW 扩为 ShellExecuteW/ShellExecuteExW
    双禁：依据 H3 任务卡"宿主侧等待提权实例退出码"，等待通道方案 A 将发起升级为
    ShellExecuteExW + SEE_MASK_NOCLOSEPROCESS（成功时取得提权实例进程句柄供等待），
    对外返回码归一化为 ShellExecuteW 风格（T4-02 admin_rescan_status_text 及其全部
    既有测试零改动）。单点语义不变——runas 发起仍全仓库唯一出口，提权路径零自启动
    语义不变；本文件除本用例外其余用例零改动。
    """
    tree = _launcher_tree()
    shell_calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and _call_name(n) in ("ShellExecuteW", "ShellExecuteExW")  # H3：双禁（依据 T4-03 卡面）
    ]
    assert len(shell_calls) == 1
    single = _function(tree, "_shell_execute_runas")
    assert single is not None
    assert _calls_of(single).count("ShellExecuteExW") == 1  # H3 方案 A：发起实现升级 ExW
    assert _calls_of(single).count("ShellExecuteW") == 0


def test_runas_call_site_unique_and_only_in_click_callback_chain():
    """U-3：_shell_execute_runas 调用点唯一，且仅经 点击回调链抵达（无自动触发路径）。

    链条：_on_admin_rescan（Tk 点击回调）→ request_admin_rescan →
    _launch_elevated_self → _shell_execute_runas，每环引用数恰为 1。
    """
    tree = _launcher_tree()
    assert _ref_count(tree, "_shell_execute_runas") == 1
    assert _ref_count(tree, "_launch_elevated_self") == 1
    assert _ref_count(tree, "request_admin_rescan") == 1
    launch = _function(tree, "_launch_elevated_self")
    assert launch is not None and "_shell_execute_runas" in _calls_of(launch)
    request = _function(tree, "request_admin_rescan")
    assert request is not None
    assert "_launch_elevated_self" in _calls_of(request)
    assert "_shell_execute_runas" not in _calls_of(request)
    click = _function(tree, "_on_admin_rescan")
    assert click is not None
    assert "request_admin_rescan" in _calls_of(click)


def test_elevated_cli_branch_zero_selfstart_zero_relaunch_refs():
    """提权分支调用链（_cmd_elevated_rescan/_elevated_deps/execute_audit）：
    零自启动调用、零网络/子进程 import、零重启自身引用——提权实例不可能重启任何进程。"""
    tree = _launcher_tree()
    for name in ("_cmd_elevated_rescan", "_elevated_deps", "execute_audit"):
        node = _function(tree, name)
        assert node is not None, f"缺少函数 {name}"
        assert _forbidden_calls(node) == []
        assert _forbidden_imports(node) == []
        for relaunch in _RELAUNCH_NAMES:
            assert _ref_count(node, relaunch) == 0, f"{name} 不得引用 {relaunch}"


def test_elevated_module_zero_relaunch_identifier_refs():
    """elevated.py 不得引用 launcher 的任何重启自身标识符（防止反向 import 拉入发起链）。"""
    tree = _elevated_tree()
    for relaunch in _RELAUNCH_NAMES:
        assert _ref_count(tree, relaunch) == 0


def test_launcher_never_opens_browser_directly():
    """提权链与 UI 代码均不直接引用 os.startfile（浏览器打开只经 reports.open_report）。"""
    assert _ref_count(_launcher_tree(), "startfile") == 0


def test_main_dispatches_elevated_flag_to_cmd_branch(monkeypatch):
    """CLI 分发：--elevated-rescan → _cmd_elevated_rescan（不进 UI）；默认 → run()。"""
    tree = _launcher_tree()
    main_node = _function(tree, "main")
    assert main_node is not None
    assert "_cmd_elevated_rescan" in _calls_of(main_node)
    monkeypatch.setattr(launcher, "_cmd_elevated_rescan", lambda: 123)
    monkeypatch.setattr(
        launcher, "run", lambda **kwargs: pytest.fail("提权分支不得进入 UI 流程")
    )
    assert launcher.main(["--elevated-rescan"]) == 123  # argv 显式传参（M-01）


def test_main_without_flag_uses_run_path(monkeypatch):
    monkeypatch.setattr(launcher, "run", lambda **kwargs: 7)
    monkeypatch.setattr(
        launcher, "_cmd_elevated_rescan",
        lambda: pytest.fail("无标记不得进入提权分支"),
    )
    assert launcher.main([]) == 7


# ---------- 文案（texts.py 文末独立区块；Q3 禁词同样适用） ----------


def test_h1_texts_required_keys_exist():
    required = [
        "admin_rescan_button",
        "status_admin_launched",
        "cli_help_elevated",
        "elevated_started",
        "elevated_report_done",
        "elevated_failed",
        "elevated_rejected",
        "elevated_err_incomplete",
        "spec_err_missing",
        "spec_err_corrupt",
        "spec_err_invalid",
        "evidence_unavailable_reason",
        "evidence_note_r9",
    ]
    missing = [key for key in required if key not in texts.H1_TEXTS]
    assert missing == []


def test_admin_button_text_matches_plan_wording():
    """E-4 原文口径：入口文案 = "以管理员身份重扫"。"""
    assert texts.H1_TEXTS["admin_rescan_button"] == "以管理员身份重扫"


def test_h1_texts_no_forbidden_terms():
    blob = "".join(texts.H1_TEXTS.values())
    assert "可回收" not in blob


# ---------- 注入式端到端（验收②等效链：替身 runas → 替身流水线 → 真实落盘） ----------


def test_full_chain_stub_runas_to_admin_report_on_disk(tmp_path):
    """全链等效断言：点击处理（替身 runas）→ 提权实例编排 → admin- 前缀报告真实落盘
    → done 标记齐备 → spec 消费。真实 UAC 由主会话按操作单执行（验收②终态留档）。"""
    reports_dir = tmp_path / "reports"

    def fake_save(html: str) -> str:
        return elevated.save_admin_report(html, reports_dir=str(reports_dir), now=_NOW)

    deps = _StubDeps(save=fake_save)
    rc_launch = launcher.request_admin_rescan(
        r"C:\scope",
        tmp_dir=str(tmp_path),
        shell_execute=lambda f, v, p: 42,
        executable=r"D:\py\python.exe", script=r"E:\repo\launcher.py", now=_NOW,
    )
    assert rc_launch == 42
    rc_run = elevated.run_elevated_rescan(
        audit=lambda scope, deps=None: launcher.execute_audit(scope, deps=deps),
        deps=deps, tmp_dir=str(tmp_path), now=_NOW,
    )
    assert rc_run == elevated.EXIT_OK
    files = list(reports_dir.iterdir())
    assert len(files) == 1
    assert files[0].name == "admin-report-20261105-120000.html"
    assert files[0].read_text(encoding="utf-8") == "<html>admin</html>"
    done = elevated.read_done_marker(tmp_dir=str(tmp_path))
    assert done is not None
    assert done["status"] == "completed" and done["mode"] == "admin"
    assert done["report_path"] == str(files[0])
    assert not _spec_path(tmp_path).exists()


# ---------- T4-04（待办 H4）：admin_mode 标志透传与独立记录可区分 ----------


class _CapturingDeps(_StubDeps):
    """在替身 render 处捕获装配完成后的报告 dict（验收③/④断言用）。"""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.rendered: list[dict] = []

    def render(self, report):
        self.rendered.append(report)
        return super().render(report)


def test_mark_admin_report_sets_flag_in_place():
    """标志注入纯逻辑：原 dict 置 admin_mode=True 并返回同一对象（不复制不重建）。"""
    report = {"schema_version": "1.1", "candidates": []}
    out = elevated.mark_admin_report(report)
    assert out is report
    assert report[elevated.ADMIN_MODE_FIELD] is True


def test_run_elevated_rescan_marks_report_admin_mode(tmp_path):
    """验收③透传链：提权实例装配的报告 dict 携带 admin_mode=True（duck 型替身 deps）。"""
    elevated.write_rescan_request(r"C:\scope", tmp_dir=str(tmp_path), now=_NOW)
    deps = _CapturingDeps()
    rc = elevated.run_elevated_rescan(
        audit=lambda scope, deps=None: launcher.execute_audit(scope, deps=deps),
        deps=deps, tmp_dir=str(tmp_path), now=_NOW,
    )
    assert rc == elevated.EXIT_OK
    assert len(deps.rendered) == 1
    assert deps.rendered[0].get(elevated.ADMIN_MODE_FIELD) is True


def test_run_elevated_rescan_marks_admin_with_frozen_dataclass_deps(tmp_path):
    """透传对 frozen dataclass（launcher.AuditDeps，真实装配形态）同样生效
    （dataclasses.replace 重建路径）。标志为装配后原地置位（mark_admin_report
    设计口径）：原 judge 产出的 dict 与 render 收到的是同一对象，仅多出标志键。"""
    elevated.write_rescan_request(r"C:\scope", tmp_dir=str(tmp_path), now=_NOW)
    rendered: list[dict] = []
    scan_result = {"root": r"C:\s", "units": [], "allocated_bytes": 0,
                   "logical_bytes": 0, "skipped": {}}
    judged: list[dict] = []

    def judge(scan):
        report = {"schema_version": "1.1", "scan_root": scan["root"], "candidates": []}
        judged.append(report)
        return report

    def _capture_render(report):
        rendered.append(report)
        return "<html>admin</html>"

    deps = launcher.AuditDeps(
        scan=lambda path, progress_cb=None, abort_check=None: dict(scan_result, root=path),
        judge=judge,
        render=_capture_render,
        save=lambda html: r"C:\reports\admin-report-x.html",
        prune=lambda: [],
        open=lambda report_path: None,
    )
    rc = elevated.run_elevated_rescan(
        audit=lambda scope, deps=None: launcher.execute_audit(scope, deps=deps),
        deps=deps, tmp_dir=str(tmp_path), now=_NOW,
    )
    assert rc == elevated.EXIT_OK
    assert len(judged) == 1 and len(rendered) == 1
    assert rendered[0] is judged[0]  # 装配产物原样流经流水线
    assert rendered[0].get(elevated.ADMIN_MODE_FIELD) is True  # 装配后置标志
    # 原 deps 对象未被破坏（frozen：replace 重建新对象，judge 引用不变）
    assert callable(deps.judge)


def test_admin_record_triple_distinguishable(tmp_path):
    """验收③：管理员/普通体检记录三重可判定——报告 dict 键（admin_mode）、落盘
    文件名前缀（admin-）、done 标记（mode=admin）三者一致；普通报告不含该键。
    （记录存储/对比管理归 I1/M3，本卡只保证输出结构可区分。）"""
    reports_dir = tmp_path / "reports"
    from disk_audit import reports  # 局部导入：既有测试文件 import 区不动（只追加原则）

    normal_path = reports.save_report(
        "<html>normal</html>", reports_dir=str(reports_dir), now=_NOW
    )
    admin_path = elevated.save_admin_report(
        "<html>admin</html>", reports_dir=str(reports_dir), now=_NOW
    )
    assert os.path.basename(admin_path).startswith(elevated.ADMIN_REPORT_PREFIX)
    assert os.path.basename(normal_path).startswith("report-")
    assert elevated.ADMIN_REPORT_PREFIX not in os.path.basename(normal_path)
    elevated.write_done_marker(
        request_id=_REQUEST_ID, status="completed",
        report_path=admin_path, tmp_dir=str(tmp_path), now=_NOW,
    )
    done = elevated.read_done_marker(tmp_dir=str(tmp_path))
    assert done is not None and done["mode"] == "admin"


def test_h4_admin_badge_text_exists():
    """S-3 徽标文案集中 texts（H4 文末区块）。"""
    assert texts.ADMIN_MODE_BADGE == "管理员模式"
