"""T-09（待办 F1）报告 JSON Schema v1 草案单元测试。

测试内实现一个支持 $defs/$ref 的 JSON Schema 子集校验器（开发期专用，
不进运行时、不引第三方包）。覆盖验收①（合法完整样例，含受保护项与低置信项）、
②（含"可回收"字段 / 缺 schema_version 的非法样例被拒绝）、Q3/Q7 负例与
枚举完整性。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
SCHEMA_PATH = _REPO / "docs" / "schemas" / "report-v1.schema.json"
EXAMPLE_PATH = _REPO / "docs" / "schemas" / "report-v1.example.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
EXAMPLE = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


# ---------- JSON Schema 子集校验器（开发期专用，支持本 schema 用到的关键字） ----------


def _type_ok(instance, expected: str) -> bool:
    if expected == "object":
        return isinstance(instance, dict)
    if expected == "array":
        return isinstance(instance, list)
    if expected == "string":
        return isinstance(instance, str)
    if expected == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if expected == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if expected == "boolean":
        return isinstance(instance, bool)
    if expected == "null":
        return instance is None
    return False


def _resolve_ref(schema: dict, ref: str) -> dict:
    assert ref.startswith("#/"), f"仅支持文档内引用：{ref}"
    node = schema
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def mini_validate(instance, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    root = root or schema
    errors: list[str] = []
    if "$ref" in schema:
        return mini_validate(instance, _resolve_ref(root, schema["$ref"]), root, path)
    expected_types = schema.get("type")
    if expected_types is not None:
        types = expected_types if isinstance(expected_types, list) else [expected_types]
        if not any(_type_ok(instance, t) for t in types):
            errors.append(f"{path}：类型应为 {'/'.join(types)}")
            return errors
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}：{instance!r} ≠ 常量 {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}：{instance!r} 不在枚举 {schema['enum']}")
    if isinstance(instance, str) and "minLength" in schema and len(instance) < schema["minLength"]:
        errors.append(f"{path}：长度 < {schema['minLength']}")
    if (
        isinstance(instance, int)
        and not isinstance(instance, bool)
        and "minimum" in schema
        and instance < schema["minimum"]
    ):
        errors.append(f"{path}：{instance} < 最小值 {schema['minimum']}")
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}：缺少必填字段 {key}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    errors.append(f"{path}：出现未定义字段 {key}")
        for key, value in instance.items():
            if key in properties:
                errors.extend(mini_validate(value, properties[key], root, f"{path}.{key}"))
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}：数组元素数 < {schema['minItems']}")
        items = schema.get("items")
        if isinstance(items, dict):
            for i, item in enumerate(instance):
                errors.extend(mini_validate(item, items, root, f"{path}[{i}]"))
    return errors


# ---------- 验收①：合法完整样例 ----------


def test_example_validates_and_covers_required_cases():
    """样例通过校验，且含受保护项与低置信项各一（验收①）。"""
    errors = mini_validate(EXAMPLE, SCHEMA)
    assert errors == []
    confidences = {c["confidence"] for c in EXAMPLE["candidates"]}
    assert "受保护" in confidences
    assert "低" in confidences


def test_protected_candidate_uses_a5():
    """受保护项固定 A5 无建议（5.3），且证据链来自硬保护（S-1 最前短路）。"""
    protected = next(c for c in EXAMPLE["candidates"] if c["confidence"] == "受保护")
    assert protected["suggested_action"] == "A5"
    assert protected["verdict_source"] == "硬保护"
    assert len(protected["evidence_chain"]) >= 1


def test_low_confidence_uses_a5_and_heuristic():
    low = next(c for c in EXAMPLE["candidates"] if c["confidence"] == "低")
    assert low["suggested_action"] == "A5"
    assert low["verdict_source"] == "启发式"


# ---------- 验收②：非法样例被拒绝 ----------


def _clone_with_candidate_mutated(mutate) -> dict:
    data = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    mutate(data["candidates"][0])
    return data


def test_recyclable_field_rejected():
    """Q3 硬规则：候选条目出现"可回收"字段 → 拒绝。"""
    data = _clone_with_candidate_mutated(lambda c: c.update({"可回收": True}))
    assert any("可回收" in e for e in mini_validate(data, SCHEMA))


def test_merged_releasable_total_rejected():
    """Q3 硬规则：totals 出现合并"可释放"总量字段 → 拒绝。"""
    data = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    data["totals"]["releasable_total_bytes"] = 4700000000
    assert any("releasable_total_bytes" in e for e in mini_validate(data, SCHEMA))


def test_missing_schema_version_rejected():
    data = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    del data["schema_version"]
    assert any("schema_version" in e for e in mini_validate(data, SCHEMA))


def test_wrong_schema_version_rejected():
    data = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    data["schema_version"] = "2.0"  # 草案阶段 const 锁定 1.0（Q7）
    assert any("schema_version" in e for e in mini_validate(data, SCHEMA))


# ---------- 枚举与字段完整性 ----------


def test_confidence_enum_four_levels():
    """5.1 置信度四档：高/中/低/受保护。"""
    assert SCHEMA["$defs"]["candidate"]["properties"]["confidence"]["enum"] == [
        "高", "中", "低", "受保护",
    ]


def test_action_enum_a1_to_a5():
    """5.3 动作固定 5 种，不新增。"""
    assert SCHEMA["$defs"]["candidate"]["properties"]["suggested_action"]["enum"] == [
        "A1", "A2", "A3", "A4", "A5",
    ]


def test_verdict_source_enum_matches_pipeline_order():
    """判定来源六枚举，与方案第四节流程③顺序一致。"""
    assert SCHEMA["$defs"]["candidate"]["properties"]["verdict_source"]["enum"] == [
        "硬保护", "知识库", "注册表", "进程服务", "Appx", "启发式",
    ]


def test_candidate_has_exactly_e2_fields():
    """E-2 每条候选 7 字段：路径/逻辑大小/占用空间/置信度/判定来源/证据链/建议动作。"""
    candidate_props = set(SCHEMA["$defs"]["candidate"]["properties"])
    assert candidate_props == {
        "path", "logical_bytes", "allocated_bytes", "confidence",
        "verdict_source", "evidence_chain", "suggested_action",
    }


def test_no_recyclable_wording_in_example_and_no_merged_total_field():
    """Q3：样例不出现"可回收"字样；totals 无合并"可释放"总量字段。

    （schema 的 description 中解释 Q3 规则时引用规则名不违规——约束对象是
    报告数据本身，故只查样例文本与字段名。）
    """
    assert "可回收" not in EXAMPLE_PATH.read_text(encoding="utf-8")
    totals_keys = set(SCHEMA["properties"]["totals"]["properties"])
    assert not any("releasable" in key.lower() or "可释放" in key for key in totals_keys)


def test_regenerable_two_buckets_present():
    """5.2：可再生两档分别列示小计字段。"""
    totals_props = SCHEMA["properties"]["totals"]["properties"]
    assert "regenerable_subtotal" in totals_props
    assert "regenerable_confirm_subtotal" in totals_props


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.update({"confidence": "极高"}),
        lambda c: c.update({"suggested_action": "A6"}),
        lambda c: c.update({"verdict_source": "猜测"}),
        lambda c: c.update({"evidence_chain": []}),  # minItems 1
        lambda c: c.update({"path": ""}),  # minLength 1
    ],
)
def test_candidate_enum_and_constraint_violations_rejected(mutate):
    data = _clone_with_candidate_mutated(mutate)
    assert mini_validate(data, SCHEMA) != []
