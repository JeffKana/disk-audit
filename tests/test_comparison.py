"""T5-03 I2a 两份体检记录纯比较的回归用例（测试先行：骨架期先红，实现后全绿）。

覆盖卡内六条验收标准：三态分类与同路径语义变化仍为不变、signed 每项差值、
净变化只用 totals 差（含父子重叠反例）、1.0/1.1 与同 admin 兼容、未知版本/
非字符串/不完整/坏 totals/坏容器/重复路径/跨 root/跨模式拒绝、字面路径身份、
输入不变、确定性、无文件系统 I/O 与文案区约束。
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import inspect

import pytest

from disk_audit import comparison, records
from disk_audit.comparison import (
    ComparisonDuplicatePathError,
    ComparisonIncompatibleError,
    ComparisonItem,
    RecordComparison,
    compare_records,
)
from disk_audit.engine import texts

ROOT = r"C:\Users\demo\AppData\Local"
OTHER_ROOT = r"D:\Users\demo\AppData\Local"
GEN_AT = "2026-11-14T22:00:00+08:00"


def _candidate(
    path: str,
    allocated: int,
    *,
    logical: int | None = None,
    confidence: str = "高",
    verdict_source: str = "知识库",
    suggested_action: str = "A2",
    chain: list[dict] | None = None,
) -> dict:
    """构造一条合法的报告候选（七字段）；默认证据链为固定中文内容。"""
    return {
        "path": path,
        "logical_bytes": allocated * 2 if logical is None else logical,
        "allocated_bytes": allocated,
        "confidence": confidence,
        "verdict_source": verdict_source,
        "evidence_chain": (
            [{"source": "知识库", "content": f"证据：{path}"}] if chain is None else chain
        ),
        "suggested_action": suggested_action,
    }


def _report(
    candidates: list[dict],
    *,
    root: str = ROOT,
    version: str = "1.1",
    admin: bool | None = None,
    allocated: int | None = None,
    logical: int | None = None,
    regenerable: int = 0,
    confirm: int = 0,
    skipped: int = 0,
    incomplete: bool | None = None,
    generated_at: str = GEN_AT,
) -> dict:
    """构造一份合法的 report/record 形状对象；默认 totals 与候选求和一致。"""
    totals = {
        "allocated_bytes": (
            sum(c["allocated_bytes"] for c in candidates) if allocated is None else allocated
        ),
        "logical_bytes": (
            sum(c["logical_bytes"] for c in candidates) if logical is None else logical
        ),
        "regenerable_subtotal": regenerable,
        "regenerable_confirm_subtotal": confirm,
        "skipped_entries": skipped,
    }
    doc = {
        "schema_version": version,
        "generated_at": generated_at,
        "scan_root": root,
        "totals": totals,
        "candidates": [copy.deepcopy(c) for c in candidates],
    }
    if admin is not None:
        doc["admin_mode"] = admin
    if incomplete is not None:
        doc["incomplete"] = incomplete
    return doc


def _paths(items: tuple[ComparisonItem, ...]) -> list[str]:
    return [item.path for item in items]


# ---------------------------------------------------------------------------
# 三态分类与每项差值
# ---------------------------------------------------------------------------


def test_three_state_basic() -> None:
    before = _report([_candidate(r"C:\A", 100), _candidate(r"C:\B", 200)])
    after = _report([_candidate(r"C:\B", 250), _candidate(r"C:\C", 50)])

    result = compare_records(before, after)

    assert _paths(result.added) == [r"C:\C"]
    assert _paths(result.removed) == [r"C:\A"]
    assert _paths(result.unchanged) == [r"C:\B"]


def test_added_item_has_none_before_and_positive_delta() -> None:
    after = _report([_candidate(r"C:\New", 123)])

    (item,) = compare_records(_report([]), after).added

    assert isinstance(item, ComparisonItem)
    assert item.path == r"C:\New"
    assert item.before is None
    assert item.after == _candidate(r"C:\New", 123)
    assert item.allocated_delta == 123


def test_removed_item_has_none_after_and_negative_delta() -> None:
    before = _report([_candidate(r"C:\Old", 500)])

    (item,) = compare_records(before, _report([])).removed

    assert item.path == r"C:\Old"
    assert item.before == _candidate(r"C:\Old", 500)
    assert item.after is None
    assert item.allocated_delta == -500


def test_unchanged_keeps_semantic_changes_and_both_candidates() -> None:
    before = _report([_candidate(r"C:\Same", 100, confidence="高", suggested_action="A2")])
    after = _report(
        [
            _candidate(
                r"C:\Same",
                100,
                confidence="低",
                verdict_source="启发式",
                suggested_action="A5",
                chain=[{"source": "启发式", "content": "新的启发式证据"}],
            )
        ]
    )

    result = compare_records(before, after)

    assert result.added == ()
    assert result.removed == ()
    (item,) = result.unchanged
    assert item.path == r"C:\Same"
    assert item.before["confidence"] == "高"
    assert item.after["confidence"] == "低"
    assert item.before["evidence_chain"] == [{"source": "知识库", "content": r"证据：C:\Same"}]
    assert item.after["evidence_chain"] == [{"source": "启发式", "content": "新的启发式证据"}]
    assert item.allocated_delta == 0


@pytest.mark.parametrize(
    ("before_alloc", "after_alloc", "expected"),
    [(100, 100, 0), (100, 40, -60), (40, 100, 60)],
)
def test_unchanged_delta_signs(before_alloc: int, after_alloc: int, expected: int) -> None:
    before = _report([_candidate(r"C:\X", before_alloc)])
    after = _report([_candidate(r"C:\X", after_alloc)])

    (item,) = compare_records(before, after).unchanged

    assert item.allocated_delta == expected


def test_empty_reports_have_empty_groups_and_zero_net() -> None:
    result = compare_records(_report([]), _report([]))

    assert result.added == ()
    assert result.removed == ()
    assert result.unchanged == ()
    assert result.net_allocated_delta == 0


def test_all_added() -> None:
    after = _report([_candidate(r"C:\A", 10), _candidate(r"C:\B", 20)])

    result = compare_records(_report([]), after)

    assert _paths(result.added) == [r"C:\A", r"C:\B"]
    assert result.removed == ()
    assert result.unchanged == ()
    assert result.net_allocated_delta == 30


def test_all_removed() -> None:
    before = _report([_candidate(r"C:\A", 10), _candidate(r"C:\B", 20)])

    result = compare_records(before, _report([]))

    assert _paths(result.removed) == [r"C:\A", r"C:\B"]
    assert result.added == ()
    assert result.unchanged == ()
    assert result.net_allocated_delta == -30


def test_all_unchanged() -> None:
    before = _report([_candidate(r"C:\A", 10), _candidate(r"C:\B", 20)])
    after = _report([_candidate(r"C:\A", 10), _candidate(r"C:\B", 20)])

    result = compare_records(before, after)

    assert _paths(result.unchanged) == [r"C:\A", r"C:\B"]
    assert result.added == ()
    assert result.removed == ()
    assert result.net_allocated_delta == 0


def test_groups_are_sorted_by_literal_path() -> None:
    before = _report([_candidate(r"C:\zeta", 1), _candidate(r"C:\alpha", 2)])
    after = _report(
        [
            _candidate(r"C:\zeta", 3),
            _candidate(r"C:\alpha", 2),
            _candidate(r"C:\Beta", 4),
            _candidate(r"C:\Apple", 5),
        ]
    )

    result = compare_records(before, after)

    assert _paths(result.added) == [r"C:\Apple", r"C:\Beta"]
    assert _paths(result.unchanged) == [r"C:\alpha", r"C:\zeta"]


def test_input_candidate_order_does_not_change_result() -> None:
    before_a = _report([_candidate(r"C:\A", 1), _candidate(r"C:\B", 2)])
    before_b = _report([_candidate(r"C:\B", 2), _candidate(r"C:\A", 1)])
    after_a = _report([_candidate(r"C:\A", 5), _candidate(r"C:\C", 3)])
    after_b = _report([_candidate(r"C:\C", 3), _candidate(r"C:\A", 5)])

    assert compare_records(before_a, after_a) == compare_records(before_b, after_b)


def test_every_path_appears_exactly_once_across_groups() -> None:
    before = _report([_candidate(r"C:\Keep", 1), _candidate(r"C:\Gone", 2)])
    after = _report([_candidate(r"C:\Keep", 4), _candidate(r"C:\Fresh", 3)])

    result = compare_records(before, after)
    seen = [
        item.path
        for group in (result.added, result.removed, result.unchanged)
        for item in group
    ]

    assert sorted(seen) == [r"C:\Fresh", r"C:\Gone", r"C:\Keep"]
    assert len(seen) == len(set(seen))


# ---------------------------------------------------------------------------
# 净变化：只能用 totals 差，不能把候选/父子项相加
# ---------------------------------------------------------------------------


def test_net_delta_uses_totals_not_candidate_sum() -> None:
    before = _report(
        [_candidate(r"C:\Parent", 100), _candidate(r"C:\Parent\Child", 60)],
        allocated=1000,
    )
    after = _report(
        [_candidate(r"C:\Parent", 120), _candidate(r"C:\Parent\Child", 90)],
        allocated=1020,
    )

    result = compare_records(before, after)
    candidate_sum = sum(
        item.allocated_delta
        for group in (result.added, result.removed, result.unchanged)
        for item in group
    )

    assert [item.allocated_delta for item in result.unchanged] == [20, 30]
    assert candidate_sum == 50
    assert result.net_allocated_delta == 20
    assert result.net_allocated_delta != candidate_sum


@pytest.mark.parametrize(
    ("before_alloc", "after_alloc", "expected"),
    [(10**18, 0, -(10**18)), (0, 10**18, 10**18), (7, 7, 0)],
)
def test_net_delta_negative_zero_and_large(
    before_alloc: int, after_alloc: int, expected: int
) -> None:
    result = compare_records(_report([], allocated=before_alloc), _report([], allocated=after_alloc))

    assert result.net_allocated_delta == expected


def test_bool_totals_value_is_not_a_number() -> None:
    bad = _report([])
    bad["totals"]["allocated_bytes"] = True

    with pytest.raises(records.RecordValidationError):
        compare_records(bad, _report([]))


def test_bool_candidate_value_is_not_a_number() -> None:
    bad_candidate = _candidate(r"C:\A", 1)
    bad_candidate["allocated_bytes"] = True
    after = _report([])
    after["candidates"] = [bad_candidate]

    with pytest.raises(records.RecordValidationError):
        compare_records(_report([]), after)


# ---------------------------------------------------------------------------
# 版本与模式兼容
# ---------------------------------------------------------------------------


def test_known_versions_1_0_and_1_1_are_compatible() -> None:
    before = _report([_candidate(r"C:\A", 10)], version="1.0")
    after = _report([_candidate(r"C:\A", 15)], version="1.1")

    result = compare_records(before, after)

    assert result.before_schema_version == "1.0"
    assert result.after_schema_version == "1.1"
    assert result.admin_mode is False
    assert result.unchanged[0].allocated_delta == 5


def test_admin_records_compare_when_both_admin() -> None:
    before = _report([_candidate(r"C:\A", 10)], admin=True)
    after = _report([_candidate(r"C:\A", 20)], admin=True)

    result = compare_records(before, after)

    assert result.admin_mode is True
    assert result.unchanged[0].allocated_delta == 10


def test_admin_false_or_absent_is_ordinary() -> None:
    before = _report([_candidate(r"C:\A", 10)], admin=False)
    after = _report([_candidate(r"C:\A", 12)], version="1.0")

    result = compare_records(before, after)

    assert result.admin_mode is False
    assert result.unchanged[0].allocated_delta == 2


@pytest.mark.parametrize("version", ["2.0", "0.9", "1.2", None, 1.1, [], {}])
def test_unknown_or_non_string_version_rejected(version: object) -> None:
    bad = _report([_candidate(r"C:\A", 1)])
    bad["schema_version"] = version

    with pytest.raises(records.RecordVersionError, match="旧记录不可比"):
        compare_records(bad, _report([]))


def test_1_0_with_admin_mode_rejected() -> None:
    bad = _report([_candidate(r"C:\A", 1)], version="1.0", admin=True)

    with pytest.raises(records.RecordValidationError):
        compare_records(bad, _report([]))


def test_incomplete_true_rejected() -> None:
    bad = _report([_candidate(r"C:\A", 1)], incomplete=True)

    with pytest.raises(records.RecordValidationError):
        compare_records(bad, _report([]))


def test_incomplete_false_is_accepted() -> None:
    doc = _report([_candidate(r"C:\A", 1)], incomplete=False)

    assert compare_records(doc, doc).unchanged[0].path == r"C:\A"


def _broken_report(kind: str) -> dict:
    doc = _report([_candidate(r"C:\A", 10)])
    if kind == "missing-totals-key":
        del doc["totals"]["logical_bytes"]
    elif kind == "extra-top-field":
        doc["raw_bundle"] = {"x": 1}
    elif kind == "confidence-list":
        doc["candidates"][0]["confidence"] = []
    elif kind == "verdict-dict":
        doc["candidates"][0]["verdict_source"] = {}
    elif kind == "evidence-chain-dict":
        doc["candidates"][0]["evidence_chain"] = {}
    elif kind == "action-list":
        doc["candidates"][0]["suggested_action"] = []
    else:  # pragma: no cover - 防御参数拼写错误
        raise AssertionError(kind)
    return doc


@pytest.mark.parametrize(
    "kind",
    [
        "missing-totals-key",
        "extra-top-field",
        "confidence-list",
        "verdict-dict",
        "evidence-chain-dict",
        "action-list",
    ],
)
def test_bad_shapes_rejected(kind: str) -> None:
    with pytest.raises(records.RecordValidationError):
        compare_records(_broken_report(kind), _report([]))


@pytest.mark.parametrize("bad", [None, [], "x", 42, (1,)])
def test_non_dict_inputs_rejected_with_record_error(bad: object) -> None:
    with pytest.raises(records.RecordValidationError):
        compare_records(bad, _report([]))
    with pytest.raises(records.RecordValidationError):
        compare_records(_report([]), bad)


# ---------------------------------------------------------------------------
# 跨范围 / 跨模式 / 重复路径
# ---------------------------------------------------------------------------


def test_cross_root_rejected() -> None:
    before = _report([], root=ROOT)
    after = _report([], root=OTHER_ROOT)

    with pytest.raises(ComparisonIncompatibleError) as excinfo:
        compare_records(before, after)

    message = str(excinfo.value)
    assert ROOT in message
    assert OTHER_ROOT in message


def test_cross_mode_rejected() -> None:
    before = _report([], admin=False)
    after = _report([], admin=True)

    with pytest.raises(ComparisonIncompatibleError) as excinfo:
        compare_records(before, after)

    message = str(excinfo.value)
    assert "admin_mode=True" in message
    assert "admin_mode=False" in message


def test_duplicate_path_in_before_rejected() -> None:
    before = _report([_candidate(r"C:\Dup", 1), _candidate(r"C:\Dup", 2)])

    with pytest.raises(ComparisonDuplicatePathError) as excinfo:
        compare_records(before, _report([]))

    message = str(excinfo.value)
    assert r"C:\Dup" in message
    assert "前一份" in message


def test_duplicate_path_in_after_rejected() -> None:
    after = _report([_candidate(r"C:\Dup", 1), _candidate(r"C:\Dup", 2)])

    with pytest.raises(ComparisonDuplicatePathError) as excinfo:
        compare_records(_report([]), after)

    message = str(excinfo.value)
    assert r"C:\Dup" in message
    assert "后一份" in message


# ---------------------------------------------------------------------------
# 字面路径身份 / 纯函数 / 输入不变
# ---------------------------------------------------------------------------


def test_literal_path_identity_does_not_merge_variants() -> None:
    before = _report([_candidate(r"C:\App\X", 10)])
    after = _report(
        [
            _candidate(r"c:\app\x", 20),
            _candidate(r"C:\App\X\\", 30),
            _candidate(r"C:\App\Sub\..\X", 40),
        ]
    )

    result = compare_records(before, after)

    assert _paths(result.added) == [
        r"C:\App\Sub\..\X",
        r"C:\App\X\\",
        r"c:\app\x",
    ]
    assert _paths(result.removed) == [r"C:\App\X"]
    assert result.unchanged == ()


def test_comparison_source_has_no_io_imports_or_file_calls() -> None:
    tree = ast.parse(inspect.getsource(comparison))
    allowed_absolute = {"__future__", "dataclasses"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".", 1)[0] in allowed_absolute
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                assert node.module in {"engine", "records"}
            else:
                assert (node.module or "").split(".", 1)[0] in allowed_absolute

    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert not (called & {"open", "eval", "exec", "compile", "input"})


def test_comparison_module_imports_no_io_modules() -> None:
    io_names = {
        "os",
        "os.path",
        "pathlib",
        "subprocess",
        "socket",
        "winreg",
        "tempfile",
        "json",
        "shutil",
        "glob",
    }

    assert not (io_names & set(comparison.__dict__))


def test_inputs_are_not_mutated() -> None:
    before = _report([_candidate(r"C:\A", 10), _candidate(r"C:\B", 20)])
    after = _report([_candidate(r"C:\B", 25), _candidate(r"C:\C", 30)])
    before_snapshot = copy.deepcopy(before)
    after_snapshot = copy.deepcopy(after)

    compare_records(before, after)

    assert before == before_snapshot
    assert after == after_snapshot


def test_repeated_calls_are_deterministic() -> None:
    before = _report([_candidate(r"C:\A", 10)])
    after = _report([_candidate(r"C:\A", 11), _candidate(r"C:\B", 12)])

    assert compare_records(before, after) == compare_records(before, after)


def test_result_is_frozen_and_groups_are_tuples() -> None:
    result = compare_records(_report([]), _report([_candidate(r"C:\A", 1)]))

    assert isinstance(result, RecordComparison)
    assert isinstance(result.added, tuple)
    assert isinstance(result.removed, tuple)
    assert isinstance(result.unchanged, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.net_allocated_delta = 1  # type: ignore[misc]


def test_result_carries_comparison_metadata() -> None:
    result = compare_records(_report([], version="1.0"), _report([], version="1.1"))

    assert result.scan_root == ROOT
    assert result.admin_mode is False
    assert result.before_schema_version == "1.0"
    assert result.after_schema_version == "1.1"


def test_public_signature_is_typed() -> None:
    signature = inspect.signature(compare_records)
    parameters = signature.parameters

    assert list(parameters) == ["before", "after"]
    assert all(p.annotation is not inspect.Signature.empty for p in parameters.values())
    assert signature.return_annotation is not inspect.Signature.empty
    assert inspect.signature(ComparisonItem).parameters  # dataclass 字段可自省


# ---------------------------------------------------------------------------
# 文案区与旧资源保真
# ---------------------------------------------------------------------------


def test_comparison_texts_zone_and_legacy_zones_intact() -> None:
    assert set(texts.COMPARISON_TEXTS) == {
        "comparison_side_before",
        "comparison_side_after",
        "comparison_err_root_mismatch",
        "comparison_err_mode_mismatch",
        "comparison_err_duplicate_path",
    }
    joined = "".join(texts.COMPARISON_TEXTS.values())
    assert "可回收" not in joined
    assert len(texts.RECORDS_TEXTS) == 37
    assert len(texts.T506_TEXTS) == 10
    assert (
        texts.RECORDS_TEXTS["records_err_bad_version"]
        == "不支持的体检记录版本 {version}：旧记录不可比，请使用对应版本的工具查看"
    )


# ---------------------------------------------------------------------------
# T5-03-R1 回归（DEF-QA-01；T503R1-v1 + T503-v2 + T503-RETURN-1）
# 比较 before/after 两侧 × top/totals/candidate 三层 × 单/混合非字符串额外键
# = 原 12 触发条件，均须文档化 RecordValidationError，不泄漏裸 TypeError；
# 未知字符串键仍拒绝；合法同模式可比；输入深层不变。仅追加，不改原用例/预期。
# ---------------------------------------------------------------------------

_R1_LAYERS = ["top", "totals", "candidate"]
_R1_NONSTRING_KEYS = [1, None, (1, 2)]


def _r1_inject(doc: dict, layer: str, keys: dict) -> dict:
    if layer == "top":
        doc.update(keys)
    elif layer == "totals":
        doc["totals"].update(keys)
    elif layer == "candidate":
        doc["candidates"][0].update(keys)
    else:  # pragma: no cover - 防御参数拼写错误
        raise AssertionError(layer)
    return doc


@pytest.mark.parametrize("layer", _R1_LAYERS)
@pytest.mark.parametrize("side", ["before", "after"])
@pytest.mark.parametrize("mixed", [False, True])
def test_r1_compare_nonstring_extra_key_rejected(layer, side, mixed):
    """原 12 触发条件：3层×2侧×单/混合非字符串额外键→RecordValidationError。"""
    good = _report([_candidate(r"C:\A", 10)])
    bad = _report([_candidate(r"C:\A", 10)])
    keys = {"bogus_string": "x", 1: "y"} if mixed else {1: "y"}
    _r1_inject(bad, layer, keys)
    before, after = (bad, good) if side == "before" else (good, bad)
    with pytest.raises(records.RecordValidationError):
        compare_records(before, after)


@pytest.mark.parametrize("layer", _R1_LAYERS)
@pytest.mark.parametrize("key", _R1_NONSTRING_KEYS)
def test_r1_compare_each_nonstring_key_both_sides(layer, key):
    """代表性内置键 int/None/tuple 在比较两侧均文档化拒绝。"""
    for side in ("before", "after"):
        good = _report([_candidate(r"C:\A", 10)])
        bad = _report([_candidate(r"C:\A", 10)])
        _r1_inject(bad, layer, {key: "x"})
        before, after = (bad, good) if side == "before" else (good, bad)
        with pytest.raises(records.RecordValidationError):
            compare_records(before, after)


@pytest.mark.parametrize("layer", _R1_LAYERS)
@pytest.mark.parametrize("side", ["before", "after"])
def test_r1_compare_string_extra_key_still_rejected(layer, side):
    good = _report([_candidate(r"C:\A", 10)])
    bad = _report([_candidate(r"C:\A", 10)])
    _r1_inject(bad, layer, {"unknown_string_key": "x"})
    before, after = (bad, good) if side == "before" else (good, bad)
    with pytest.raises(records.RecordValidationError) as excinfo:
        compare_records(before, after)
    assert "unknown_string_key" in str(excinfo.value)


@pytest.mark.parametrize("layer", _R1_LAYERS)
def test_r1_compare_nonstring_extra_key_input_unchanged(layer):
    good = _report([_candidate(r"C:\A", 10)])
    bad = _report([_candidate(r"C:\A", 10)])
    _r1_inject(bad, layer, {1: "x", "bogus": "y"})
    good_snap = copy.deepcopy(good)
    bad_snap = copy.deepcopy(bad)
    with pytest.raises(records.RecordValidationError):
        compare_records(bad, good)
    assert bad == bad_snap
    assert good == good_snap


def test_r1_compare_legal_same_mode_still_comparable():
    """合法控制：合法同模式 1.1 两份仍可比较（修复不误拒）。"""
    before = _report([_candidate(r"C:\A", 100)])
    after = _report([_candidate(r"C:\A", 150), _candidate(r"C:\B", 50)])
    result = compare_records(before, after)
    assert result.net_allocated_delta == 100
    assert _paths(result.added) == [r"C:\B"]
