r"""T5-01（I1a）体检记录 JSON 存储基础 —— 含反例的测试先行用例。

依据：任务卡 T5-01（T501-v1）实现约束与验收标准②~⑤、F1 定稿 Q7/U-2/X-2/S-3、
report-v1.schema.json（1.0/1.1 兼容声明）、《开发规范》§1/§3、exec-sop 第 4 步。

I/O 根全部可注入（tmp_path / monkeypatch），不写真实 %LOCALAPPDATA%\DiskAudit\records；
重解析点用替身（os.lstat / _read_raw 注入）验证，不创建真实 junction；不使用真
KeyboardInterrupt，不依赖 locale/argv 泄漏。本卡不接线 UI、不实现对比或淘汰。
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
import stat
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from disk_audit import records  # noqa: E402
from disk_audit import RECORDS_DIR as PACKAGE_RECORDS_DIR  # noqa: E402
from disk_audit.engine import texts  # noqa: E402
from disk_audit.engine.report import REPORT_SCHEMA_VERSION  # noqa: E402

FIXED_NOW = datetime(2026, 11, 1, 15, 30, 45)
FIXED_NOW_NEXT = datetime(2026, 11, 1, 15, 30, 46)


# ---------------------------------------------------------------------------
# 固定夹具：中文/Windows 路径、候选七字段、totals 双口径汇总
# ---------------------------------------------------------------------------


def _candidate() -> dict:
    return {
        "path": "C:\\Users\\<user>\\AppData\\Local\\缓存目录\\子项",
        "logical_bytes": 40960,
        "allocated_bytes": 45056,
        "confidence": "高",
        "verdict_source": "知识库",
        "evidence_chain": [
            {"source": "知识库", "content": "命中知识库条目：旧版组件，残留候选（中文证据内容）"},
            {"source": "注册表卸载项", "content": "HKLM/HKCU 卸载记录中无匹配"},
        ],
        "suggested_action": "A4",
    }


def valid_report(**overrides) -> dict:
    data = {
        "schema_version": "1.1",
        "generated_at": "2026-11-01T15:30:45+08:00",
        "scan_root": "C:\\Users\\<user>\\AppData\\Local",
        "totals": {
            "allocated_bytes": 53860000000,
            "logical_bytes": 57830000000,
            "regenerable_subtotal": 1200000000,
            "regenerable_confirm_subtotal": 3500000000,
            "skipped_entries": 63,
        },
        "candidates": [_candidate()],
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# 验收②：有效记录往返（保存 → 列举 → 读取语义逐项相同）
# ---------------------------------------------------------------------------


def test_save_list_read_roundtrip_preserves_all_semantics(tmp_path: Path):
    report = valid_report()
    rid = records.save_record(report, records_dir=str(tmp_path), now=FIXED_NOW)
    assert rid == "record-20261101-153045"

    entries = records.list_records(records_dir=str(tmp_path))
    assert len(entries) == 1
    entry = entries[0]
    assert entry.comparable is True
    assert entry.problem is None
    assert entry.filename == "record-20261101-153045.json"
    assert entry.admin_mode is False
    assert entry.schema_version == "1.1"

    got = records.read_record(rid, records_dir=str(tmp_path))
    assert got["schema_version"] == report["schema_version"] == "1.1"
    assert got["generated_at"] == report["generated_at"]
    assert got["scan_root"] == report["scan_root"]
    assert got["totals"] == report["totals"]  # 双口径逐项
    assert got["candidates"] == report["candidates"]  # 候选七字段逐项
    assert set(got) == set(report)  # 不增不减任何字段
    assert "缓存目录" in got["candidates"][0]["path"]  # 中文/Windows 路径保真

    raw = (tmp_path / (rid + ".json")).read_text(encoding="utf-8")
    assert json.loads(raw) == report
    assert "缓存目录" in raw  # ensure_ascii=False：中文未转义
    assert "<html" not in raw  # 不保存 HTML 全文


def test_empty_candidates_report_can_be_saved(tmp_path: Path):
    report = valid_report(candidates=[])
    rid = records.save_record(report, records_dir=str(tmp_path), now=FIXED_NOW)
    assert records.read_record(rid, records_dir=str(tmp_path))["candidates"] == []
    assert records.list_records(records_dir=str(tmp_path))[0].comparable is True


def test_default_dir_uses_records_dir_constant_standin(tmp_path: Path, monkeypatch):
    """默认写入位 = 包内 RECORDS_DIR 常量（经替身替换），不写真实用户数据。"""
    monkeypatch.setattr(records, "RECORDS_DIR", str(tmp_path / "records_default"))
    rid = records.save_record(valid_report(), now=FIXED_NOW)  # 不传 records_dir
    assert (tmp_path / "records_default" / "record-20261101-153045.json").is_file()
    assert records.read_record(rid)["schema_version"] == "1.1"
    assert records.list_records()[0].record_id == rid


def test_records_dir_constant_is_under_diskaudit_records():
    assert "DiskAudit" in PACKAGE_RECORDS_DIR
    assert PACKAGE_RECORDS_DIR.endswith("records")


# ---------------------------------------------------------------------------
# 验收②：普通/管理员记录 ID/文件名可区分；1.1 管理员状态保留
# ---------------------------------------------------------------------------


def test_admin_record_id_filename_distinct_and_state_preserved(tmp_path: Path):
    normal = records.save_record(valid_report(), records_dir=str(tmp_path), now=FIXED_NOW)
    admin = records.save_record(
        valid_report(admin_mode=True), records_dir=str(tmp_path), now=FIXED_NOW_NEXT
    )
    assert normal.startswith("record-") and not normal.startswith("admin-")
    assert admin.startswith("admin-record-")
    assert admin != normal

    got = records.read_record(admin, records_dir=str(tmp_path))
    assert got["admin_mode"] is True
    assert got["schema_version"] == "1.1"
    assert (tmp_path / (admin + ".json")).name.startswith("admin-record-")

    by_id = {e.record_id: e for e in records.list_records(records_dir=str(tmp_path))}
    assert by_id[normal].admin_mode is False
    assert by_id[admin].admin_mode is True
    assert by_id[normal].comparable is True and by_id[admin].comparable is True


# ---------------------------------------------------------------------------
# 验收③：版本边界（1.0/1.1 可读、不归一化、未知版本可区分拒绝）
# ---------------------------------------------------------------------------


def test_version_1_0_missing_admin_mode_kept_as_normal(tmp_path: Path):
    report = valid_report(schema_version="1.0")
    assert "admin_mode" not in report
    rid = records.save_record(report, records_dir=str(tmp_path), now=FIXED_NOW)
    got = records.read_record(rid, records_dir=str(tmp_path))
    assert got["schema_version"] == "1.0"  # 不默默归一化成 1.1
    assert "admin_mode" not in got  # 保持原字段
    assert set(got) == set(report)
    entry = records.list_records(records_dir=str(tmp_path))[0]
    assert entry.comparable is True
    assert entry.admin_mode is False  # 按普通模式消费
    assert entry.schema_version == "1.0"


def test_versions_are_not_silently_normalized(tmp_path: Path):
    for version in ("1.0", "1.1"):
        report = valid_report(schema_version=version)
        if version == "1.1":
            report["admin_mode"] = True
        directory = str(tmp_path / version)
        rid = records.save_record(report, records_dir=directory, now=FIXED_NOW)
        assert records.read_record(rid, records_dir=directory)["schema_version"] == version


def test_report_schema_version_constant_unchanged():
    """不改 REPORT_SCHEMA_VERSION（仍为 1.1）。"""
    assert REPORT_SCHEMA_VERSION == "1.1"


def test_known_versions_declared():
    assert set(records.KNOWN_VERSIONS) == {"1.0", "1.1"}


@pytest.mark.parametrize(
    "bad_version",
    ["2.0", "1.2", "0.9", "9.9", "abc", "", 2, None, True],
)
def test_unknown_or_incompatible_version_rejected_on_save(tmp_path: Path, bad_version):
    report = valid_report(schema_version=bad_version)
    with pytest.raises(records.RecordVersionError) as excinfo:
        records.save_record(report, records_dir=str(tmp_path), now=FIXED_NOW)
    assert "旧记录不可比" in str(excinfo.value)
    assert list(tmp_path.iterdir()) == []  # 未产生任何写入


def test_version_error_is_distinguishable_from_shape_error():
    """未知版本与坏形状用不同的异常类型，消费方可区分。"""
    with pytest.raises(records.RecordVersionError):
        records.validate_record(valid_report(schema_version="2.0"))
    with pytest.raises(records.RecordValidationError):
        records.validate_record({"schema_version": "1.1"})


# ---------------------------------------------------------------------------
# 验收③：损坏 JSON / 坏字段 / 不兼容版本可披露，且不阻断合法记录列举
# ---------------------------------------------------------------------------


def test_corrupt_and_incompatible_records_disclosed_without_blocking_legal(tmp_path: Path):
    good = records.save_record(valid_report(), records_dir=str(tmp_path), now=FIXED_NOW)
    (tmp_path / "record-20261101-153046.json").write_text("{ not json", encoding="utf-8")
    (tmp_path / "record-20261101-153047.json").write_text(
        json.dumps({"schema_version": "1.1"}), encoding="utf-8"
    )  # 合法 JSON 但缺必需字段
    (tmp_path / "record-20261101-153048.json").write_text(
        json.dumps(valid_report(schema_version="3.0"), ensure_ascii=False), encoding="utf-8"
    )  # 不兼容版本

    entries = records.list_records(records_dir=str(tmp_path))
    by_id = {e.record_id: e for e in entries}
    assert len(entries) == 4
    assert by_id[good].comparable is True  # 合法记录仍被列举
    for bad in (
        "record-20261101-153046",
        "record-20261101-153047",
        "record-20261101-153048",
    ):
        assert by_id[bad].comparable is False
        assert by_id[bad].record is None
        assert by_id[bad].problem  # 可披露、非空
    assert "旧记录不可比" in by_id["record-20261101-153048"].problem

    with pytest.raises(records.RecordError):
        records.read_record("record-20261101-153046", records_dir=str(tmp_path))
    with pytest.raises(records.RecordVersionError) as exc:
        records.read_record("record-20261101-153048", records_dir=str(tmp_path))
    assert "旧记录不可比" in str(exc.value)


def test_non_utf8_record_disclosed(tmp_path: Path):
    (tmp_path / "record-20261101-153045.json").write_bytes(b"\xff\xfe\x00bad")
    entries = records.list_records(records_dir=str(tmp_path))
    assert entries[0].comparable is False
    assert entries[0].problem


# ---------------------------------------------------------------------------
# 验收③/④：坏 schema / 非对象 / 缺字段 / 多余字段 / 非法候选 / incomplete
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [["not", "object"], "字符串", 123, None, True])
def test_non_object_report_rejected(bad):
    with pytest.raises(records.RecordValidationError):
        records.validate_record(bad)


@pytest.mark.parametrize(
    "drop", ["schema_version", "generated_at", "scan_root", "totals", "candidates"]
)
def test_missing_required_field_rejected(tmp_path: Path, drop):
    report = valid_report()
    del report[drop]
    with pytest.raises(records.RecordValidationError):
        records.save_record(report, records_dir=str(tmp_path), now=FIXED_NOW)
    assert list(tmp_path.iterdir()) == []


def test_extra_field_rejected_no_privacy_persistence(tmp_path: Path):
    """多余字段（原始采集 bundle / HTML 全文）明确拒绝，不悄悄持久化额外隐私数据。"""
    report = valid_report()
    report["raw_bundle"] = {"processes": ["p.exe"], "registry": ["HKLM\\x"]}
    report["html_full"] = "<html>报告全文</html>"
    with pytest.raises(records.RecordValidationError) as exc:
        records.save_record(report, records_dir=str(tmp_path), now=FIXED_NOW)
    assert "raw_bundle" in str(exc.value) or "html_full" in str(exc.value)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update({"totals": "not-object"}),
        lambda r: r["totals"].pop("allocated_bytes"),
        lambda r: r["totals"].update({"releasable_total_bytes": 1}),
        lambda r: r["totals"].update({"allocated_bytes": -1}),
        lambda r: r["totals"].update({"allocated_bytes": True}),
        lambda r: r["totals"].update({"logical_bytes": 1.5}),
        lambda r: r.update({"candidates": "not-list"}),
        lambda r: r["candidates"].append({"path": "C:\\x"}),
        lambda r: r["candidates"][0].pop("confidence"),
        lambda r: r["candidates"][0].update({"confidence": "极高"}),
        lambda r: r["candidates"][0].update({"verdict_source": "猜测"}),
        lambda r: r["candidates"][0].update({"suggested_action": "A6"}),
        lambda r: r["candidates"][0].update({"evidence_chain": []}),
        lambda r: r["candidates"][0]["evidence_chain"][0].update({"source": "猜测"}),
        lambda r: r["candidates"][0]["evidence_chain"][0].update({"content": 123}),
        lambda r: r["candidates"][0].update({"path": ""}),
        lambda r: r["candidates"][0].update({"extra": 1}),
        lambda r: r.update({"generated_at": ""}),
        lambda r: r.update({"scan_root": 5}),
        lambda r: r.update({"admin_mode": "yes"}),
        lambda r: r.update({"incomplete": "yes"}),
        lambda r: r.update({"incomplete": True}),
    ],
)
def test_bad_shape_and_illegal_candidate_rejected(tmp_path: Path, mutate):
    report = valid_report()
    mutate(report)
    with pytest.raises(records.RecordValidationError):
        records.save_record(report, records_dir=str(tmp_path), now=FIXED_NOW)
    assert list(tmp_path.iterdir()) == []


def test_incomplete_true_never_produces_complete_record(tmp_path: Path):
    report = valid_report(incomplete=True)
    with pytest.raises(records.RecordValidationError) as exc:
        records.save_record(report, records_dir=str(tmp_path), now=FIXED_NOW)
    assert "不完整" in str(exc.value)
    assert sorted(p.name for p in tmp_path.iterdir()) == []
    assert records.list_records(records_dir=str(tmp_path)) == []


def test_1_0_with_admin_mode_rejected():
    """1.0 不含 admin_mode 字段；出现即坏 schema，明确拒绝而非归一化。"""
    with pytest.raises(records.RecordValidationError):
        records.validate_record(valid_report(schema_version="1.0", admin_mode=True))


def test_validate_record_returns_copy_without_mutating_input():
    report = valid_report()
    got = records.validate_record(report)
    assert got == report and got is not report


# ---------------------------------------------------------------------------
# 验收④：同秒不覆盖；非法名/越界路径；伪装目录/重解析点替身；扫描根零操作
# ---------------------------------------------------------------------------


def test_same_second_two_distinct_records_both_kept_no_overwrite(tmp_path: Path):
    r1 = valid_report()
    r2 = valid_report(generated_at="2026-11-01T15:30:46+08:00")
    id1 = records.save_record(r1, records_dir=str(tmp_path), now=FIXED_NOW)
    id2 = records.save_record(r2, records_dir=str(tmp_path), now=FIXED_NOW)
    assert id1 == "record-20261101-153045"
    assert id2 == "record-20261101-153045-1"
    p1 = tmp_path / (id1 + ".json")
    p2 = tmp_path / (id2 + ".json")
    assert p1.is_file() and p2.is_file()
    assert json.loads(p1.read_text(encoding="utf-8")) == r1
    assert json.loads(p2.read_text(encoding="utf-8")) == r2
    assert hashlib.sha256(p1.read_bytes()).digest() != hashlib.sha256(p2.read_bytes()).digest()
    assert len(records.list_records(records_dir=str(tmp_path))) == 2


def test_three_same_second_records_get_increasing_sequence(tmp_path: Path):
    ids = [
        records.save_record(
            valid_report(generated_at=f"2026-11-01T15:30:4{i}+08:00"),
            records_dir=str(tmp_path),
            now=FIXED_NOW,
        )
        for i in range(3)
    ]
    assert ids == [
        "record-20261101-153045",
        "record-20261101-153045-1",
        "record-20261101-153045-2",
    ]


def test_resolve_record_path_accepts_valid_id(tmp_path: Path):
    assert Path(records.resolve_record_path(str(tmp_path), "record-20261101-153045")) == (
        tmp_path / "record-20261101-153045.json"
    )
    assert Path(
        records.resolve_record_path(str(tmp_path), "admin-record-20261101-153045-2")
    ) == (tmp_path / "admin-record-20261101-153045-2.json")


@pytest.mark.parametrize(
    "bad_id",
    [
        r"..\evil",
        "sub\\record-20261101-153045",
        "C:\\Windows\\record-20261101-153045",
        r"..\..\record-20261101-153045",
        "evil",
        "record-20261101-153045.html",
        "record-20261101-153045.json.exe",
        "record-20261101-153045.json/evil",
        "record-2026110-153045",
        "admin-record-20261101-153045.json",
        "",
        "record-20261101-153045-",
    ],
)
def test_illegal_names_and_path_escape_rejected(tmp_path: Path, bad_id):
    with pytest.raises(records.RecordValidationError) as exc:
        records.resolve_record_path(str(tmp_path), bad_id)
    assert str(exc.value)  # 中文文案非空
    with pytest.raises(records.RecordValidationError):
        records.read_record(bad_id, records_dir=str(tmp_path))
    assert list(tmp_path.rglob("*")) == []  # 拒绝路径未产生任何写入/越界读


def test_read_record_on_nonexistent_id_raises(tmp_path: Path):
    with pytest.raises(records.RecordError):
        records.read_record("record-20261101-153045", records_dir=str(tmp_path))


def test_save_record_does_not_accept_caller_supplied_path():
    """ID/文件名由模块生成；不接收任意文件名/路径注入。"""
    params = inspect.signature(records.save_record).parameters
    assert "records_dir" in params and "now" in params
    assert "filename" not in params and "path" not in params and "record_id" not in params
    read_params = inspect.signature(records.read_record).parameters
    assert "record_id" in read_params and "records_dir" in read_params
    assert "path" not in read_params


def test_disguised_directory_named_like_record_is_not_followed(tmp_path: Path):
    good = records.save_record(valid_report(), records_dir=str(tmp_path), now=FIXED_NOW)
    (tmp_path / "record-20261101-153046.json").mkdir()  # 伪装目录
    by_id = {e.record_id: e for e in records.list_records(records_dir=str(tmp_path))}
    assert by_id[good].comparable is True
    assert by_id["record-20261101-153046"].comparable is False
    assert by_id["record-20261101-153046"].problem


def test_reparse_point_standin_skipped_without_outside_read(tmp_path: Path, monkeypatch):
    """替身：os.lstat 返回 REPARSE_POINT 位；断言从未读取该项（不跟随、不越界）。"""
    name = "record-20261101-153045.json"
    (tmp_path / name).write_text("sentinel", encoding="utf-8")
    real_lstat = os.lstat
    fake_st = SimpleNamespace(
        st_mode=stat.S_IFREG | 0o644,
        st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
    )

    def fake_lstat(path, *args, **kwargs):
        if os.path.basename(str(path)) == name:
            return fake_st
        return real_lstat(path, *args, **kwargs)

    read_calls: list[str] = []

    def forbid_read(target):
        read_calls.append(str(target))
        raise AssertionError("不应读取重解析点")

    monkeypatch.setattr(records.os, "lstat", fake_lstat)
    monkeypatch.setattr(records, "_read_raw", forbid_read)

    entries = records.list_records(records_dir=str(tmp_path))
    assert entries[0].comparable is False
    assert entries[0].problem
    assert read_calls == []

    with pytest.raises(records.RecordError):
        records.read_record("record-20261101-153045", records_dir=str(tmp_path))
    assert read_calls == []


def test_no_filesystem_operation_on_scan_root(tmp_path: Path):
    scan_root = tmp_path / "scan_target"
    scan_root.mkdir()
    sentinel = scan_root / "sentinel.txt"
    sentinel.write_text("DO NOT TOUCH", encoding="utf-8")
    before = sorted(p.name for p in scan_root.iterdir())
    sentinel_bytes = sentinel.read_bytes()

    report = valid_report(scan_root=str(scan_root))
    records.save_record(report, records_dir=str(tmp_path / "records"), now=FIXED_NOW)

    assert sorted(p.name for p in scan_root.iterdir()) == before
    assert sentinel.read_bytes() == sentinel_bytes  # 被扫描路径零文件系统操作


@pytest.mark.parametrize("seam", ["_serialize", "_stage", "_publish"])
def test_injected_failures_leave_existing_unchanged_and_no_half_record(
    tmp_path: Path, monkeypatch, seam
):
    good = records.save_record(valid_report(), records_dir=str(tmp_path), now=FIXED_NOW)
    good_file = tmp_path / (good + ".json")
    hash_before = hashlib.sha256(good_file.read_bytes()).hexdigest()

    def boom(*args, **kwargs):
        if seam == "_serialize":
            raise TypeError("注入序列化失败")
        raise OSError("注入写盘/发布失败")

    monkeypatch.setattr(records, seam, boom)
    with pytest.raises((OSError, TypeError, records.RecordError)):
        records.save_record(
            valid_report(generated_at="2026-11-01T15:30:46+08:00"),
            records_dir=str(tmp_path),
            now=FIXED_NOW,
        )

    assert hashlib.sha256(good_file.read_bytes()).hexdigest() == hash_before
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        good + ".json"
    ]  # 既有记录不变、无半条正式记录、无临时残留


# ---------------------------------------------------------------------------
# 验收④：列举只认本模块严格命名普通文件；空/缺目录
# ---------------------------------------------------------------------------


def test_list_records_ignores_foreign_and_temp_files(tmp_path: Path):
    rid = records.save_record(valid_report(), records_dir=str(tmp_path), now=FIXED_NOW)
    for name in (
        "notes.txt",
        "report-20261101-153045.html",
        "other.json",
        ".tmp-record-abc123.json",
        "record-20261101-15304X.json",
        "admin-record-20261101-153045.json.bak",
    ):
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert [e.record_id for e in records.list_records(records_dir=str(tmp_path))] == [rid]


def test_list_records_empty_or_missing_dir(tmp_path: Path):
    assert records.list_records(records_dir=str(tmp_path / "missing")) == []
    assert records.list_records(records_dir=str(tmp_path)) == []


# ---------------------------------------------------------------------------
# 验收⑤/①：异常层次、公共签名类型标注与文档、文案资源区、既有区不变
# ---------------------------------------------------------------------------


def test_exception_types_are_distinguishable():
    assert issubclass(records.RecordError, ValueError)
    assert issubclass(records.RecordValidationError, records.RecordError)
    assert issubclass(records.RecordVersionError, records.RecordError)
    assert issubclass(records.RecordWriteError, records.RecordError)
    assert records.RecordValidationError is not records.RecordVersionError


def test_public_api_has_type_annotations_and_docstrings():
    for fn in (
        records.validate_record,
        records.resolve_record_path,
        records.save_record,
        records.read_record,
        records.list_records,
    ):
        assert fn.__annotations__, fn.__name__
        assert fn.__doc__, fn.__name__


def test_records_texts_zone_keys_and_no_forbidden_terms():
    required = [
        "records_err_bad_id",
        "records_err_outside_dir",
        "records_err_not_object",
        "records_err_missing_fields",
        "records_err_extra_fields",
        "records_err_bad_version",
        "records_err_incomplete",
        "records_err_incomplete_type",
        "records_err_bad_admin_mode",
        "records_err_bad_totals",
        "records_err_bad_candidates",
        "records_err_bad_field",
        "records_err_read",
        "records_err_json",
        "records_err_encode",
        "records_err_not_regular",
        "records_err_conflict",
    ]
    assert all(key in texts.RECORDS_TEXTS for key in required)
    blob = "".join(texts.RECORDS_TEXTS.values())
    assert "可回收" not in blob  # Q3 禁词
    assert "旧记录不可比" in texts.RECORDS_TEXTS["records_err_bad_version"]


def test_existing_texts_zones_untouched():
    """本卡仅向 texts.py 文末追加新资源区，既有区/判定文案不变。"""
    assert texts.CONFIDENCE_WORDING["高"] == "高度可能为残留；删除前请确认"
    assert texts.G3_TEXTS["reports_err_bad_filename"]
    assert texts.EVIDENCE_SOURCE_ENUM[0] == "硬保护"


# ============================================================================
# T501-RETURN-1 回归（第1次退回；先写后修，红为 f5e240 上的行为断言失败，
# 不是缺模块 ImportError）。DEF-1 坏容器类型 / DEF-2 根与祖先 junction /
# OBS-1 固定中文校验细节集中。保留上方原用例与语义。
# ============================================================================

_CMD_EXE = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe")


def _assert_within(path: str, sandbox: str) -> None:
    path_abs = os.path.abspath(path)
    root_abs = os.path.abspath(sandbox)
    assert os.path.commonpath([path_abs, root_abs]) == root_abs


def _junction_sandbox(tmp_path: Path, tag: str) -> tuple[Path, Path, Path]:
    """在 tmp_path 内自建授权沙箱：target/ 与 link 均在沙箱内，link 为真实 junction。

    创建前核对绝对路径、target 为已存在目录、link 不在 target 内；不指向真实目录。
    """
    import subprocess  # 仅测试侧；运行时 disk_audit/ 仍零外部进程

    sandbox = tmp_path / f"junction-{tag}"
    target = sandbox / "target"
    target.mkdir(parents=True)
    link = sandbox / "link"
    link_abs, target_abs, root_abs = str(link), str(target), str(sandbox)
    _assert_within(link_abs, root_abs)
    _assert_within(target_abs, root_abs)
    assert (
        os.path.commonpath([os.path.abspath(link_abs), os.path.abspath(target_abs)])
        != os.path.abspath(target_abs)
    )
    assert os.path.isdir(target_abs) and not os.path.lexists(link_abs)
    proc = subprocess.run(
        [_CMD_EXE, "/c", "mklink", "/J", link_abs, target_abs],
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert os.path.isjunction(link_abs)
    return sandbox, target, link


def _remove_junction(link: Path, sandbox: Path) -> None:
    """只删除已核实位于沙箱内、且确为 junction 的链接本身，不递归删除 target。"""
    link_abs, root_abs = str(link), str(sandbox)
    _assert_within(link_abs, root_abs)
    if not os.path.lexists(link_abs):
        return
    assert os.path.isjunction(link_abs)
    os.rmdir(link_abs)


def _tree_snapshot(root: Path) -> dict:
    """目录树快照（相对路径 -> 类别/字节 mtime/文件 sha256）；不跟随 junction。"""
    root_abs = os.path.abspath(str(root))
    snapshot: dict = {}
    for dirpath, dirnames, filenames in os.walk(root_abs, followlinks=False):
        for name in sorted(dirnames):
            full = os.path.join(dirpath, name)
            st = os.lstat(full)
            snapshot[os.path.relpath(full, root_abs)] = ("dir", st.st_mtime_ns, None)
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            st = os.lstat(full)
            with open(full, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            snapshot[os.path.relpath(full, root_abs)] = ("file", st.st_mtime_ns, digest)
    return snapshot


def _seed_record_file(directory: Path, record_id: str = "record-20260101-000001") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / (record_id + ".json")).write_text(
        json.dumps(valid_report(), ensure_ascii=False), encoding="utf-8"
    )


# ---------- DEF-1：四枚举位置的坏容器类型（list/dict）不得中断整批 ----------

_R1_ENUM_FIELDS = ("confidence", "verdict_source", "suggested_action")
_R1_BAD_CONTAINERS = [[], {}]


@pytest.mark.parametrize("field", _R1_ENUM_FIELDS)
@pytest.mark.parametrize("container", _R1_BAD_CONTAINERS, ids=["list", "dict"])
def test_r1_enum_bad_container_validate_rejected(field, container):
    report = valid_report()
    report["candidates"][0][field] = container
    with pytest.raises(records.RecordValidationError):
        records.validate_record(report)


@pytest.mark.parametrize(
    "container", [[], {}, 1, None], ids=["list", "dict", "int", "none"]
)
def test_r1_chain_source_bad_container_validate_rejected(container):
    report = valid_report()
    report["candidates"][0]["evidence_chain"][0]["source"] = container
    with pytest.raises(records.RecordValidationError):
        records.validate_record(report)


@pytest.mark.parametrize("field", _R1_ENUM_FIELDS)
@pytest.mark.parametrize("container", _R1_BAD_CONTAINERS, ids=["list", "dict"])
def test_r1_enum_bad_container_save_rejected_no_dir(tmp_path: Path, field, container):
    out = tmp_path / "records-not-created"
    report = valid_report()
    report["candidates"][0][field] = container
    with pytest.raises(records.RecordValidationError):
        records.save_record(report, records_dir=str(out), now=FIXED_NOW)
    assert not os.path.lexists(str(out)), "坏输入不得先创建记录目录"


def test_r1_chain_source_bad_container_save_rejected_no_dir(tmp_path: Path):
    out = tmp_path / "records-not-created"
    report = valid_report()
    report["candidates"][0]["evidence_chain"][0]["source"] = []
    with pytest.raises(records.RecordValidationError):
        records.save_record(report, records_dir=str(out), now=FIXED_NOW)
    assert not os.path.lexists(str(out))


def test_r1_bad_container_record_isolated_in_listing(tmp_path: Path):
    """合法 + 四个不同坏容器位置混排：合法项仍 comparable，坏项逐项披露。"""
    _seed_record_file(tmp_path, "record-20260101-000001")
    bad_reports: dict[str, dict] = {}
    for field, container in (
        ("confidence", []),
        ("verdict_source", {}),
        ("suggested_action", []),
    ):
        report = valid_report()
        report["candidates"][0][field] = container
        bad_reports[field] = report
    report = valid_report()
    report["candidates"][0]["evidence_chain"][0]["source"] = {}
    bad_reports["chain_source"] = report
    index = 2
    for bad in bad_reports.values():
        (tmp_path / f"record-20260101-00000{index}.json").write_text(
            json.dumps(bad, ensure_ascii=False), encoding="utf-8"
        )
        index += 1

    entries = records.list_records(records_dir=str(tmp_path))
    by_name = {entry.filename: entry for entry in entries}
    assert len(by_name) == 5, "整批列举不应中断"
    assert by_name["record-20260101-000001.json"].comparable is True
    for name, entry in by_name.items():
        if name == "record-20260101-000001.json":
            continue
        assert entry.comparable is False, name
        assert entry.record is None, name
        assert entry.problem, name  # 可披露


@pytest.mark.parametrize("field", _R1_ENUM_FIELDS)
@pytest.mark.parametrize("container", _R1_BAD_CONTAINERS, ids=["list", "dict"])
def test_r1_bad_container_read_raises_record_error(tmp_path: Path, field, container):
    report = valid_report()
    report["candidates"][0][field] = container
    (tmp_path / "record-20260101-000001.json").write_text(
        json.dumps(report, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(records.RecordError):
        records.read_record("record-20260101-000001", records_dir=str(tmp_path))


def test_r1_chain_source_bad_container_read_raises_record_error(tmp_path: Path):
    report = valid_report()
    report["candidates"][0]["evidence_chain"][0]["source"] = {}
    (tmp_path / "record-20260101-000001.json").write_text(
        json.dumps(report, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(records.RecordError):
        records.read_record("record-20260101-000001", records_dir=str(tmp_path))


# ---------- DEF-2：真实沙箱 root / ancestor junction，不得越逻辑授权根 ----------


@pytest.mark.parametrize("operation", ["list", "read", "save"])
def test_r1_root_junction_not_followed(tmp_path: Path, operation):
    sandbox, target, link = _junction_sandbox(tmp_path, f"root-{operation}")
    _seed_record_file(target)
    before = _tree_snapshot(target)
    try:
        if operation == "list":
            try:
                entries = records.list_records(records_dir=str(link))
            except records.RecordError:
                entries = []
            assert [entry.filename for entry in entries] == [], "根 junction 被 list 跟随"
        elif operation == "read":
            with pytest.raises(records.RecordError):
                records.read_record("record-20260101-000001", records_dir=str(link))
        else:
            try:
                records.save_record(
                    valid_report(generated_at="2026-11-01T15:30:46+08:00"),
                    records_dir=str(link),
                    now=FIXED_NOW,
                )
            except records.RecordError:
                pass
    finally:
        _remove_junction(link, sandbox)
    assert _tree_snapshot(target) == before, "根 junction 的 target 文件清单/字节/哈希被改动"


@pytest.mark.parametrize("operation", ["list", "read", "save"])
def test_r1_ancestor_junction_not_followed(tmp_path: Path, operation):
    sandbox, target, link = _junction_sandbox(tmp_path, f"ancestor-{operation}")
    sub = target / "sub"
    _seed_record_file(sub)
    records_dir = link / "sub"
    before = _tree_snapshot(target)
    try:
        if operation == "list":
            try:
                entries = records.list_records(records_dir=str(records_dir))
            except records.RecordError:
                entries = []
            assert [entry.filename for entry in entries] == [], "祖先 junction 被 list 跟随"
        elif operation == "read":
            with pytest.raises(records.RecordError):
                records.read_record("record-20260101-000001", records_dir=str(records_dir))
        else:
            try:
                records.save_record(valid_report(), records_dir=str(records_dir), now=FIXED_NOW)
            except records.RecordError:
                pass
    finally:
        _remove_junction(link, sandbox)
    assert _tree_snapshot(target) == before, "祖先 junction 的 target 被改动"


def test_r1_ancestor_junction_missing_leaf_save_rejected(tmp_path: Path):
    """祖先为 junction、末级目录不存在：不得只检查最终存在目录而放过创建。"""
    sandbox, target, link = _junction_sandbox(tmp_path, "ancestor-missing")
    (target / "sub").mkdir()
    before = _tree_snapshot(target)
    missing = link / "missing"
    try:
        try:
            records.save_record(valid_report(), records_dir=str(missing), now=FIXED_NOW)
        except records.RecordError:
            pass
        assert not os.path.lexists(str(missing)), "不得在 junction target 下新建目录"
    finally:
        _remove_junction(link, sandbox)
    assert _tree_snapshot(target) == before


def test_r1_normal_missing_root_can_be_created(tmp_path: Path):
    """控制组：普通不存在根（无 junction 祖先）仍可合法创建，避免放宽为过度拒绝。"""
    fresh = tmp_path / "fresh-records"
    record_id = records.save_record(valid_report(), records_dir=str(fresh), now=FIXED_NOW)
    assert (fresh / (record_id + ".json")).is_file()
    assert records.read_record(record_id, records_dir=str(fresh))["schema_version"] == "1.1"


def test_r1_real_file_symlink_or_documented_skip(tmp_path: Path):
    """真实文件 symlink：有特权则实测拒绝；WinError 1314 则如实 skip 并注明限制。"""
    target = tmp_path / "symlink-target.json"
    target.write_text(json.dumps(valid_report(), ensure_ascii=False), encoding="utf-8")
    records_dir = tmp_path / "records"
    records_dir.mkdir()
    link = records_dir / "record-20260101-000003.json"
    try:
        os.symlink(str(target), str(link))
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows 无创建文件符号链接特权（WinError 1314）；真实 junction 与 lstat 替身已覆盖")
        raise
    try:
        by_name = {
            entry.filename: entry
            for entry in records.list_records(records_dir=str(records_dir))
        }
        assert by_name["record-20260101-000003.json"].comparable is False
        with pytest.raises(records.RecordError):
            records.read_record("record-20260101-000003", records_dir=str(records_dir))
    finally:
        if os.path.lexists(str(link)):
            os.unlink(str(link))


# ---------- OBS-1：固定中文校验细节集中 texts，真实异常清晰无 Q3 禁词 ----------

_R1_DETAIL_KEYS = (
    "records_detail_not_object",
    "records_detail_not_array",
    "records_detail_missing_fields",
    "records_detail_extra_fields",
    "records_detail_nonneg_int",
    "records_detail_nonempty_str",
    "records_detail_bool",
    "records_detail_candidate_not_object",
    "records_detail_candidate_missing",
    "records_detail_candidate_extra",
    "records_detail_enum_invalid",
    "records_detail_chain_not_array",
    "records_detail_chain_item_shape",
    "records_detail_chain_source_invalid",
    "records_detail_chain_content_not_str",
    "records_err_root_reparse",
    "records_err_root_not_dir",
    "records_err_root_stat",
)


def test_r1_detail_templates_centralized_in_texts():
    assert all(key in texts.RECORDS_TEXTS for key in _R1_DETAIL_KEYS)
    blob = "".join(texts.RECORDS_TEXTS.values())
    assert "可回收" not in blob  # Q3 禁词


def test_r1_no_fixed_validation_details_inline_in_records():
    source = Path(records.__file__).read_text(encoding="utf-8")
    fixed_literals = [
        "应为对象",
        "缺少字段 {",
        "出现未定义字段 {",
        "应为非负整数",
        "应为非空字符串",
        "应为布尔值",
        "应为数组",
        "#{index} 应为对象",
        "应为至少 1 项的数组",
        "应为含 source/content 的对象",
        "条 source 非法",
        "条 content 应为字符串",
        " confidence 非法",
        " verdict_source 非法",
        " suggested_action 非法",
    ]
    for literal in fixed_literals:
        assert literal not in source, f"records.py 仍内联固定对外中文：{literal}"


def test_r1_bad_container_exception_message_clear_and_no_q3():
    report = valid_report()
    report["candidates"][0]["confidence"] = []
    with pytest.raises(records.RecordValidationError) as excinfo:
        records.validate_record(report)
    message = str(excinfo.value)
    assert message and "confidence" in message  # 真实异常输出仍清晰
    assert "可回收" not in message


# ============================================================================
# T5-03-R1 回归（父 T503 第1次退回 DEF-QA-01；T503R1-v1 + T503-v2 + T503-RETURN-1）。
# 三层（top/totals/candidate）非字符串额外键须文档化 RecordValidationError，不泄漏
# 裸 TypeError；未知字符串键仍拒绝；合法控制不误拒；输入深层不变；save 验证先行无写入。
# 先写后修：红为 c3 上的裸 TypeError 行为断言失败，非 ImportError/构造无效。仅追加。
# ============================================================================

_R1_NONSTRING_KEYS = [1, None, (1, 2)]  # 代表性内置非字符串键：int/None/tuple


def _r1_inject_extra(doc: dict, layer: str, keys: dict) -> dict:
    """把额外键注入指定层（top/totals/candidate）；keys 为 {键: 值}。"""
    if layer == "top":
        doc.update(keys)
    elif layer == "totals":
        doc["totals"].update(keys)
    elif layer == "candidate":
        doc["candidates"][0].update(keys)
    else:  # pragma: no cover - 防御参数拼写错误
        raise AssertionError(layer)
    return doc


@pytest.mark.parametrize("layer", ["top", "totals", "candidate"])
@pytest.mark.parametrize("key", _R1_NONSTRING_KEYS)
def test_r1_validate_nonstring_extra_key_rejected(layer, key):
    report = valid_report()
    _r1_inject_extra(report, layer, {key: "x"})
    with pytest.raises(records.RecordValidationError):
        records.validate_record(report)


@pytest.mark.parametrize("layer", ["top", "totals", "candidate"])
def test_r1_validate_mixed_extra_keys_rejected(layer):
    report = valid_report()
    _r1_inject_extra(report, layer, {"bogus_string": "x", 1: "y"})
    with pytest.raises(records.RecordValidationError):
        records.validate_record(report)


@pytest.mark.parametrize("layer", ["top", "totals", "candidate"])
def test_r1_validate_string_extra_key_still_rejected(layer):
    """对照：未知字符串键仍按原文案拒绝（行为不放宽）。"""
    report = valid_report()
    _r1_inject_extra(report, layer, {"unknown_string_key": "x"})
    with pytest.raises(records.RecordValidationError) as excinfo:
        records.validate_record(report)
    assert "unknown_string_key" in str(excinfo.value)


@pytest.mark.parametrize("layer", ["top", "totals", "candidate"])
@pytest.mark.parametrize("key", _R1_NONSTRING_KEYS)
def test_r1_save_nonstring_extra_key_validation_first_no_write(tmp_path, layer, key):
    report = valid_report()
    _r1_inject_extra(report, layer, {key: "x"})
    with pytest.raises(records.RecordValidationError):
        records.save_record(report, records_dir=str(tmp_path), now=FIXED_NOW)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("layer", ["top", "totals", "candidate"])
def test_r1_validate_nonstring_extra_key_input_unchanged(layer):
    report = valid_report()
    _r1_inject_extra(report, layer, {1: "x", "bogus": "y"})
    snapshot = copy.deepcopy(report)
    with pytest.raises(records.RecordValidationError):
        records.validate_record(report)
    assert report == snapshot


def test_r1_validate_nonstring_extra_key_message_uses_existing_resource():
    report = valid_report()
    report[1] = "x"
    with pytest.raises(records.RecordValidationError) as excinfo:
        records.validate_record(report)
    message = str(excinfo.value)
    assert "未定义字段" in message  # 复用既有 records_err_extra_fields 模板
    assert "可回收" not in message  # Q3 禁词


def test_r1_legal_report_still_validates():
    """合法控制：合法 1.1 报告校验通过（修复不放宽也不误拒）。"""
    validated = records.validate_record(valid_report())
    assert validated["schema_version"] == "1.1"
