"""T5-04-A 显式体检关联元数据基础库的单元测试（T504A-v1 / DR-016）。

覆盖：七字段严格 schema、版本/类型/命名/模式/XOR/机器码、纯 build/validate 无 I/O 与时钟、
save/read/list 往返、根与祖先重解析点守卫、叶不跟随、坏项逐项披露、外来项不动、原子不覆盖。
"""
from __future__ import annotations

import copy
import json
import os
import re
import stat
import subprocess
import sys
import types
from datetime import datetime as _REAL_DATETIME
from pathlib import Path

import pytest

from disk_audit import links
from disk_audit.engine import texts

SCHEMA = "checkup-link-v1"
CID = "0123456789abcdef0123456789abcdef"
OTHER_CID = "fedcba9876543210fedcba9876543210"
CREATED = "2026-11-16T00:56:30+08:00"
REPORT_N = "report-20261116-005630.html"
RECORD_N = "record-20261116-005630"
REPORT_A = "admin-report-20261116-005630.html"
RECORD_A = "admin-record-20261116-005630"
KEYS = (
    "schema_version",
    "checkup_id",
    "created_at",
    "mode",
    "report_filename",
    "record_id",
    "record_error",
)


def _raw(**overrides):
    data = {
        "schema_version": SCHEMA,
        "checkup_id": CID,
        "created_at": CREATED,
        "mode": "normal",
        "report_filename": REPORT_N,
        "record_id": RECORD_N,
        "record_error": None,
    }
    data.update(overrides)
    return data


def _link_name(checkup_id=CID):
    return "link-%s.json" % checkup_id


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _make_junction(link_path: Path, target: Path) -> None:
    """真实目录 junction（Windows 不需提权）；失败如实 skip 并带系统原因。"""
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link_path), str(target)],
        capture_output=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or b"").decode("mbcs", errors="replace").strip()
        pytest.skip("无法创建目录 junction（rc=%d）：%s" % (result.returncode, detail))


def _is_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


# ---------------------------------------------------------------------------
# 独立熵入口
# ---------------------------------------------------------------------------


def test_new_checkup_id_shape_and_uniqueness():
    ids = {links.new_checkup_id() for _ in range(64)}
    assert len(ids) == 64
    for value in ids:
        assert isinstance(value, str)
        assert re.fullmatch(r"[0-9a-f]{32}", value), value


def test_new_checkup_id_does_not_use_clock_or_sequence(monkeypatch):
    monkeypatch.setattr(links, "datetime", _ExplodingClock)
    assert re.fullmatch(r"[0-9a-f]{32}", links.new_checkup_id())


class _ExplodingClock:
    @staticmethod
    def now(*args, **kwargs):  # pragma: no cover - 仅用于断言未被调用
        raise AssertionError("pure API must not read the current time")

    @staticmethod
    def fromisoformat(value):
        return _REAL_DATETIME.fromisoformat(value)


# ---------------------------------------------------------------------------
# build_link / validate_link：形状与返回
# ---------------------------------------------------------------------------


def test_build_returns_exactly_seven_keys_in_stable_order():
    result = links.build_link(
        checkup_id=CID,
        created_at=CREATED,
        mode="normal",
        report_filename=REPORT_N,
        record_id=RECORD_N,
        record_error=None,
    )
    assert tuple(result) == KEYS
    assert result["schema_version"] == SCHEMA
    assert result["checkup_id"] == CID


@pytest.mark.parametrize(
    ("mode", "report", "record", "error"),
    [
        ("normal", REPORT_N, RECORD_N, None),
        ("normal", REPORT_N, None, "record-save-failed"),
        ("admin", REPORT_A, RECORD_A, None),
        ("admin", REPORT_A, None, "record-save-failed"),
    ],
)
def test_build_accepts_valid_matrix(mode, report, record, error):
    result = links.build_link(
        checkup_id=CID,
        created_at=CREATED,
        mode=mode,
        report_filename=report,
        record_id=record,
        record_error=error,
    )
    assert links.validate_link(result) == result


def test_build_does_not_generate_id_or_time():
    first = links.build_link(
        checkup_id=CID,
        created_at=CREATED,
        mode="normal",
        report_filename=REPORT_N,
        record_id=None,
        record_error="record-save-failed",
    )
    second = links.build_link(
        checkup_id=CID,
        created_at=CREATED,
        mode="normal",
        report_filename=REPORT_N,
        record_id=None,
        record_error="record-save-failed",
    )
    assert first == second == _raw(record_id=None, record_error="record-save-failed")


def test_validate_returns_new_dict_and_does_not_mutate_input():
    source = _raw()
    snapshot = copy.deepcopy(source)
    result = links.validate_link(source)
    assert result == source
    assert result is not source
    assert source == snapshot


def test_validate_rejects_non_dict_without_typeerror():
    for value in ([], (), "text", 1, 1.5, None, True, {0: "x"} and [], set()):
        with pytest.raises(links.LinkValidationError):
            links.validate_link(value)


def test_validate_reports_missing_fields_individually():
    for key in KEYS:
        data = _raw()
        data.pop(key)
        with pytest.raises(links.LinkValidationError):
            links.validate_link(data)


@pytest.mark.parametrize("extra", [{"note": "x"}, {1: "x"}, {None: "x"}, {("a",): 1}])
def test_validate_rejects_extra_and_non_string_keys(extra):
    data = _raw()
    data.update(extra)
    with pytest.raises(links.LinkValidationError):
        links.validate_link(data)


@pytest.mark.parametrize("value", [1, 1.0, True, None, [], {}, ()])
def test_validate_container_and_scalar_bad_values_are_wrapped(value):
    for key in ("created_at", "mode", "report_filename"):
        data = _raw()
        data[key] = value
        with pytest.raises(links.LinkError):
            links.validate_link(data)


# ---------------------------------------------------------------------------
# 版本
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "version", ["checkup-link-v2", "1.0", "", "CHECKUP-LINK-V1", "checkup-link-v1 "]
)
def test_unknown_version_is_version_error(version):
    with pytest.raises(links.LinkVersionError):
        links.validate_link(_raw(schema_version=version))


@pytest.mark.parametrize("version", [1, 1.0, None, True, [], {}, ("x",)])
def test_non_string_version_is_version_error_not_typeerror(version):
    with pytest.raises(links.LinkVersionError):
        links.validate_link(_raw(schema_version=version))


def test_version_error_is_link_error_and_value_error():
    assert issubclass(links.LinkVersionError, links.LinkError)
    assert issubclass(links.LinkError, ValueError)
    for cls in (links.LinkValidationError, links.LinkVersionError, links.LinkIOError):
        assert issubclass(cls, links.LinkError)


# ---------------------------------------------------------------------------
# checkup_id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "A" * 32,
        "a" * 31,
        "a" * 33,
        "g" * 32,
        "0123456789abcdef-123456789abcdef",
        "",
        " ",
        "0123456789abcdef0123456789abcde ",
        "0123456789ABCDEF0123456789abcdef",
    ],
)
def test_checkup_id_rejects_non_contract_forms(value):
    with pytest.raises(links.LinkValidationError):
        links.validate_link(_raw(checkup_id=value))


# ---------------------------------------------------------------------------
# created_at
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "2026-11-16T00:56:30",
        "2026-11-16",
        "2026-11-16 00:56:30",
        "2026-13-16T00:56:30+08:00",
        "2026-11-16T25:00:00+08:00",
        "2026-11-16T00:56:30+8:00",
        "2026-11-16T00:56:30+0800",
        "not-a-time",
        "",
        " 2026-11-16T00:56:30+08:00",
        "2026-11-16T00:56:30+08:00 ",
        "２０２６-11-16T00:56:30+08:00",
    ],
)
def test_created_at_requires_explicit_timezone_and_iso8601(value):
    with pytest.raises(links.LinkValidationError):
        links.validate_link(_raw(created_at=value))


@pytest.mark.parametrize(
    "value",
    [
        "2026-11-16T00:56:30+08:00",
        "2026-11-16T00:56:30Z",
        "2026-11-16T00:56:30-05:00",
        "2026-11-16 00:56:30+00:00",
        "2026-11-16T00:56:30.123456+08:00",
        "2026-11-16T00:56+08:00",
    ],
)
def test_created_at_accepts_iso8601_with_offset(value):
    assert links.validate_link(_raw(created_at=value))["created_at"] == value


# ---------------------------------------------------------------------------
# mode
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value", ["Normal", "ADMIN", "admin ", "", "both", "user", None, 1, [], {}]
)
def test_mode_is_strict_normal_or_admin(value):
    with pytest.raises(links.LinkError):
        links.validate_link(_raw(mode=value))


@pytest.mark.parametrize(
    ("mode", "report"),
    [
        ("normal", REPORT_A),
        ("admin", REPORT_N),
    ],
)
def test_report_prefix_must_match_mode(mode, report):
    with pytest.raises(links.LinkValidationError):
        links.validate_link(_raw(mode=mode, report_filename=report))


@pytest.mark.parametrize(
    ("mode", "report", "record"),
    [
        ("normal", REPORT_N, RECORD_A),
        ("admin", REPORT_A, RECORD_N),
    ],
)
def test_record_prefix_must_match_mode(mode, report, record):
    with pytest.raises(links.LinkValidationError):
        links.validate_link(_raw(mode=mode, report_filename=report, record_id=record))

# ---------------------------------------------------------------------------
# report_filename / record_id / record_error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "../report-20261116-005630.html",
        "sub/report-20261116-005630.html",
        "sub\\report-20261116-005630.html",
        "C:report-20261116-005630.html",
        r"C:\Users\x\report-20261116-005630.html",
        "/abs/report-20261116-005630.html",
        "report-20261116-005630.html:stream",
        "report-20261116-005630.html.exe",
        "report-20261116-005630.HTML",
        "report-2026-005630.html",
        "report-20261116-005630-.html",
        "report-20261116-005630 ",
        "报告-20261116-005630.html",
        "",
        "report.html",
        "admin-report-20261116-005630.html",
    ],
)
def test_report_filename_rejects_unsafe_or_off_contract(value):
    with pytest.raises(links.LinkValidationError):
        links.validate_link(_raw(report_filename=value))


@pytest.mark.parametrize(
    "value",
    [
        "report-20261116-005630.json",
        "record-20261116-005630.json",
        "../record-20261116-005630",
        "sub/record-20261116-005630",
        "record-20261116-5630",
        "record-20261116-005630 ",
        "RECORD-20261116-005630",
        "",
        "record-20261116-005630:ads",
    ],
)
def test_record_id_rejects_off_contract(value):
    with pytest.raises(links.LinkValidationError):
        links.validate_link(_raw(record_id=value))


def test_record_id_null_requires_machine_code():
    assert links.validate_link(_raw(record_id=None, record_error="record-save-failed"))


@pytest.mark.parametrize(
    "error",
    [None, "", " ", "record_save_failed", "Record-save-failed", "boom", "失败", 1, [], {}],
)
def test_record_error_accepts_only_fixed_machine_code(error):
    with pytest.raises(links.LinkError):
        links.validate_link(_raw(record_id=None, record_error=error))


@pytest.mark.parametrize("error", ["record-save-failed", "", "boom", 1, [], {}])
def test_record_success_requires_null_error(error):
    with pytest.raises(links.LinkError):
        links.validate_link(_raw(record_id=RECORD_N, record_error=error))


def test_record_and_report_need_not_share_timestamp():
    data = _raw(report_filename="report-20260101-010101.html", record_id="record-20260102-020202")
    assert links.validate_link(data)["record_id"] == "record-20260102-020202"


# ---------------------------------------------------------------------------
# 纯函数无 I/O、无时钟
# ---------------------------------------------------------------------------


def test_build_and_validate_perform_no_io(monkeypatch):
    class _NoIoOs:
        def __getattr__(self, name):
            def _boom(*args, **kwargs):
                raise AssertionError("pure API must not touch the filesystem")

            return _boom

    monkeypatch.setattr(links, "os", _NoIoOs())
    monkeypatch.setattr(links, "datetime", _ExplodingClock)
    data = _raw()
    assert links.build_link(
        checkup_id=CID,
        created_at=CREATED,
        mode="normal",
        report_filename=REPORT_N,
        record_id=RECORD_N,
        record_error=None,
    ) == data
    assert links.validate_link(data) == data


# ---------------------------------------------------------------------------
# save_link
# ---------------------------------------------------------------------------


def test_save_link_roundtrip_returns_id_and_writes_exact_name(tmp_path):
    root = tmp_path / "records" / "links"
    data = _raw()
    result = links.save_link(data, links_dir=str(root))
    assert result == CID
    target = root / _link_name()
    assert target.is_file()
    assert json.loads(target.read_text(encoding="utf-8")) == data
    assert not [p for p in root.iterdir() if p.name.startswith(".tmp-link-")]


def test_save_link_creates_missing_tail_but_not_outside_root(tmp_path):
    root = tmp_path / "a" / "b" / "links"
    assert links.save_link(_raw(), links_dir=str(root)) == CID
    assert (root / _link_name()).is_file()


def test_save_link_does_not_mutate_input(tmp_path):
    data = _raw()
    snapshot = copy.deepcopy(data)
    links.save_link(data, links_dir=str(tmp_path / "links"))
    assert data == snapshot


def test_save_link_validates_before_touching_disk(tmp_path, monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("validation must run before any filesystem action")

    monkeypatch.setattr(links.os, "makedirs", _boom)
    bad = _raw(mode="invalid")
    with pytest.raises(links.LinkValidationError):
        links.save_link(bad, links_dir=str(tmp_path / "links"))


def test_save_link_collision_keeps_old_bytes_and_no_temp(tmp_path):
    root = tmp_path / "links"
    root.mkdir()
    target = _write(root / _link_name(), "SENTINEL\n")
    before = target.read_bytes()
    with pytest.raises(links.LinkIOError):
        links.save_link(_raw(), links_dir=str(root))
    assert target.read_bytes() == before
    assert [p.name for p in root.iterdir()] == [target.name]


def test_save_link_publish_failure_cleans_only_own_temp(tmp_path, monkeypatch):
    root = tmp_path / "links"

    def _fail(src, dst):
        raise PermissionError("publish denied")

    monkeypatch.setattr(links.os, "rename", _fail)
    with pytest.raises(links.LinkIOError):
        links.save_link(_raw(), links_dir=str(root))
    assert not (root / _link_name()).exists()
    assert [p.name for p in root.iterdir() if p.name.startswith(".tmp-link-")] == []


def test_save_link_fsync_failure_cleans_temp(tmp_path, monkeypatch):
    root = tmp_path / "links"

    def _fail(fd):
        raise OSError("fsync denied")

    monkeypatch.setattr(links.os, "fsync", _fail)
    with pytest.raises(links.LinkIOError):
        links.save_link(_raw(), links_dir=str(root))
    assert [p.name for p in root.iterdir()] == []


def test_save_link_mkstemp_failure_is_link_error(tmp_path, monkeypatch):
    root = tmp_path / "links"

    def _fail(*args, **kwargs):
        raise OSError("no temp")

    monkeypatch.setattr(links.tempfile, "mkstemp", _fail)
    with pytest.raises(links.LinkIOError):
        links.save_link(_raw(), links_dir=str(root))


def test_save_link_root_is_file_rejected(tmp_path):
    root = tmp_path / "afile"
    _write(root, "x")
    with pytest.raises(links.LinkIOError):
        links.save_link(_raw(), links_dir=str(root / "links"))


def test_save_link_ancestor_is_file_rejected(tmp_path):
    blocker = _write(tmp_path / "blocker", "x")
    with pytest.raises(links.LinkIOError):
        links.save_link(_raw(), links_dir=str(blocker / "links"))


def test_module_never_uses_os_replace():
    source = Path(links.__file__).read_text(encoding="utf-8")
    assert "os.replace(" not in source
    assert "os.rename(" in source


# ---------------------------------------------------------------------------
# read_link
# ---------------------------------------------------------------------------


def test_read_link_roundtrip(tmp_path):
    root = tmp_path / "links"
    data = _raw()
    links.save_link(data, links_dir=str(root))
    assert links.read_link(CID, links_dir=str(root)) == data


def test_read_link_validates_id_before_io(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("id validation must run before filesystem access")

    monkeypatch.setattr(links.os, "lstat", _boom)
    with pytest.raises(links.LinkValidationError):
        links.read_link("../evil")


def test_read_link_missing_file_is_io_error(tmp_path):
    root = tmp_path / "links"
    root.mkdir()
    with pytest.raises(links.LinkIOError):
        links.read_link(CID, links_dir=str(root))


def test_read_link_bad_json(tmp_path):
    root = tmp_path / "links"
    root.mkdir()
    _write(root / _link_name(), "{not json")
    with pytest.raises(links.LinkIOError):
        links.read_link(CID, links_dir=str(root))


def test_read_link_unknown_version_is_version_error(tmp_path):
    root = tmp_path / "links"
    root.mkdir()
    _write(root / _link_name(), _dump(_raw(schema_version="checkup-link-v9")))
    with pytest.raises(links.LinkVersionError):
        links.read_link(CID, links_dir=str(root))


def test_read_link_body_id_mismatch_is_validation_error(tmp_path):
    root = tmp_path / "links"
    root.mkdir()
    _write(root / _link_name(), _dump(_raw(checkup_id=OTHER_CID)))
    with pytest.raises(links.LinkValidationError):
        links.read_link(CID, links_dir=str(root))


def test_read_link_directory_target_rejected(tmp_path):
    root = tmp_path / "links"
    (root / _link_name()).mkdir(parents=True)
    with pytest.raises(links.LinkIOError):
        links.read_link(CID, links_dir=str(root))


def test_read_link_missing_root_is_io_error(tmp_path):
    with pytest.raises(links.LinkIOError):
        links.read_link(CID, links_dir=str(tmp_path / "no" / "links"))


# ---------------------------------------------------------------------------
# list_links
# ---------------------------------------------------------------------------


def test_list_missing_root_returns_empty(tmp_path):
    assert links.list_links(links_dir=str(tmp_path / "none")) == []


def test_list_sorted_by_literal_filename_and_ignores_foreign(tmp_path):
    root = tmp_path / "links"
    root.mkdir()
    ids = ["f" * 32, "0" * 32, "a" * 32]
    for cid in ids:
        _write(root / _link_name(cid), _dump(_raw(checkup_id=cid)))
    _write(root / "notes.txt", "keep me")
    _write(root / ".tmp-link-x.json", "temp")
    _write(root / ("link-%s.json.bak" % ("b" * 32)), "backup")
    (root / "sub").mkdir()
    _write(root / "sub" / _link_name("c" * 32), _dump(_raw(checkup_id="c" * 32)))
    entries = links.list_links(links_dir=str(root))
    assert [e.filename for e in entries] == [_link_name(cid) for cid in sorted(ids)]
    assert all(e.problem is None and e.data is not None for e in entries)
    assert (root / "notes.txt").read_text(encoding="utf-8") == "keep me"


def test_list_discloses_bad_items_without_blocking_valid_ones(tmp_path):
    root = tmp_path / "links"
    root.mkdir()
    good = "a" * 32
    bad_json = "b" * 32
    bad_version = "c" * 32
    mismatch = "d" * 32
    directory = "e" * 32
    _write(root / _link_name(good), _dump(_raw(checkup_id=good)))
    _write(root / _link_name(bad_json), "{oops")
    _write(root / _link_name(bad_version), _dump(_raw(checkup_id=bad_version, schema_version="x")))
    _write(root / _link_name(mismatch), _dump(_raw(checkup_id=good)))
    (root / _link_name(directory)).mkdir()
    entries = links.list_links(links_dir=str(root))
    by_name = {e.filename: e for e in entries}
    assert len(entries) == 5
    assert by_name[_link_name(good)].data is not None
    for cid in (bad_json, bad_version, mismatch, directory):
        entry = by_name[_link_name(cid)]
        assert entry.data is None
        assert isinstance(entry.problem, str) and entry.problem


def test_link_entry_is_frozen():
    entry = links.LinkEntry(checkup_id=CID, filename=_link_name(), data=None, problem="x")
    with pytest.raises(Exception):
        entry.problem = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 重解析点守卫（真实 junction；文件 symlink 视策略条件 skip + lstat 替身）
# ---------------------------------------------------------------------------


def test_save_rejected_when_root_is_junction(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    junc = tmp_path / "junc"
    _make_junction(junc, real)
    with pytest.raises(links.LinkIOError):
        links.save_link(_raw(), links_dir=str(junc))
    assert list(real.iterdir()) == []


def test_read_rejected_when_root_is_junction(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    _write(real / _link_name(), _dump(_raw()))
    junc = tmp_path / "junc"
    _make_junction(junc, real)
    with pytest.raises(links.LinkIOError):
        links.read_link(CID, links_dir=str(junc))


def test_list_rejected_when_root_is_junction(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    _write(real / _link_name(), _dump(_raw()))
    junc = tmp_path / "junc"
    _make_junction(junc, real)
    with pytest.raises(links.LinkIOError):
        links.list_links(links_dir=str(junc))


def test_save_rejected_when_ancestor_is_junction_and_target_untouched(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    junc = tmp_path / "junc"
    _make_junction(junc, real)
    with pytest.raises(links.LinkIOError):
        links.save_link(_raw(), links_dir=str(junc / "links"))
    assert not (real / "links").exists()


def test_leaf_symlink_is_not_followed(tmp_path):
    root = tmp_path / "links"
    root.mkdir()
    outside = _write(tmp_path / "outside.json", "OUTSIDE\n")
    leaf = root / _link_name()
    try:
        os.symlink(outside, leaf)
    except OSError as exc:
        winerror = getattr(exc, "winerror", None)
        pytest.skip("文件 symlink 不可用（winerror=%s）：%s" % (winerror, exc))
    before = outside.read_bytes()
    entries = links.list_links(links_dir=str(root))
    assert entries and entries[0].problem
    assert entries[0].data is None
    with pytest.raises(links.LinkIOError):
        links.read_link(CID, links_dir=str(root))
    assert outside.read_bytes() == before


def test_read_rejected_when_ancestor_is_junction(tmp_path):
    real = tmp_path / "real"
    (real / "links").mkdir(parents=True)
    _write(real / "links" / _link_name(), _dump(_raw()))
    junc = tmp_path / "junc"
    _make_junction(junc, real)
    with pytest.raises(links.LinkIOError):
        links.read_link(CID, links_dir=str(junc / "links"))


def test_list_rejected_when_ancestor_is_junction(tmp_path):
    real = tmp_path / "real"
    (real / "links").mkdir(parents=True)
    _write(real / "links" / _link_name(), _dump(_raw()))
    junc = tmp_path / "junc"
    _make_junction(junc, real)
    with pytest.raises(links.LinkIOError):
        links.list_links(links_dir=str(junc / "links"))


def test_list_does_not_create_missing_root(tmp_path):
    root = tmp_path / "no" / "links"
    assert links.list_links(links_dir=str(root)) == []
    assert not root.exists()
    assert not root.parent.exists()


def test_leaf_reparse_guard_via_lstat_stub(tmp_path, monkeypatch):
    root = tmp_path / "links"
    root.mkdir()
    leaf = _write(root / _link_name(), _dump(_raw()))
    real_lstat = os.lstat
    flagged = types.SimpleNamespace(
        st_mode=stat.S_IFREG | 0o644,
        st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
    )

    def fake_lstat(path, *args, **kwargs):
        if os.path.normcase(os.fspath(path)) == os.path.normcase(os.fspath(leaf)):
            return flagged
        return real_lstat(path, *args, **kwargs)

    before = leaf.read_bytes()
    monkeypatch.setattr(links.os, "lstat", fake_lstat)
    entries = links.list_links(links_dir=str(root))
    assert entries[0].problem
    with pytest.raises(links.LinkIOError):
        links.read_link(CID, links_dir=str(root))
    assert leaf.read_bytes() == before


# ---------------------------------------------------------------------------
# 文案资源
# ---------------------------------------------------------------------------


def test_links_texts_are_nonempty_chinese():
    assert isinstance(texts.LINKS_TEXTS, dict) and texts.LINKS_TEXTS
    for key, value in texts.LINKS_TEXTS.items():
        assert isinstance(key, str) and key
        assert isinstance(value, str) and value
        assert _is_cjk(value), (key, value)


def test_user_facing_errors_use_texts_not_raw_exceptions(tmp_path):
    with pytest.raises(links.LinkError) as caught:
        links.validate_link(_raw(checkup_id="BAD"))
    message = str(caught.value)
    assert _is_cjk(message)
    assert "Traceback" not in message