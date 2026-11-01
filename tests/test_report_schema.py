"""T-09（待办 F1）报告 JSON Schema v1 草案单元测试。

覆盖验收①（合法完整样例，含受保护项与低置信项）、
②（含"可回收"字段 / 缺 schema_version 的非法样例被拒绝）、Q3/Q7 负例与
枚举完整性。校验器实现抽至 tests/_mini_schema.py 共用（T2-02 判定引擎复用）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests._mini_schema import mini_validate

_REPO = Path(__file__).resolve().parents[1]
SCHEMA_PATH = _REPO / "docs" / "schemas" / "report-v1.schema.json"
EXAMPLE_PATH = _REPO / "docs" / "schemas" / "report-v1.example.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
EXAMPLE = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


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


# ---------- F1 定稿（T2-07）：枚举收紧 / incomplete / 版本语义 ----------


def test_finalized_schema_not_draft():
    assert "草案" not in SCHEMA["title"]


def test_evidence_source_enum_aligned_with_evidence_v1():
    """证据链 source 收紧为枚举（与 evidence.v1 六源对齐 + 判定层三源）。

    evidence.v1 六源映射：注册表卸载项↔uninstall、Appx↔appx、进程↔processes、
    服务↔services、自启动↔autostart、文件枚举↔文件枚举器（9.2 大小/陈旧度依据）；
    硬保护/知识库/启发式为架构③判定层依据来源。
    """
    enum = SCHEMA["$defs"]["candidate"]["properties"]["evidence_chain"]["items"][
        "properties"
    ]["source"]["enum"]
    assert enum == [
        "硬保护", "知识库", "注册表卸载项", "进程", "服务", "自启动",
        "Appx", "启发式", "文件枚举",
    ]


def test_illegal_evidence_source_rejected():
    data = _clone_with_candidate_mutated(
        lambda c: c["evidence_chain"][0].update({"source": "猜测"})
    )
    assert mini_validate(data, SCHEMA) != []


def test_incomplete_optional_field():
    """X-2/C7：incomplete 为可选 boolean（部分结果标记，totals 由其判无效）。"""
    prop = SCHEMA["properties"]["incomplete"]
    assert prop["type"] == "boolean"
    assert "incomplete" not in SCHEMA["required"]


def test_incomplete_example_accepted_and_bad_type_rejected():
    data = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    data["incomplete"] = True
    assert mini_validate(data, SCHEMA) == []
    bad = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    bad["incomplete"] = "yes"
    assert mini_validate(bad, SCHEMA) != []


def test_schema_version_semantics_documented():
    """Q7 版本语义写入 schema：结构破坏 major+1（联动"旧记录不可比"）；非破坏 minor+1。"""
    desc = SCHEMA["properties"]["schema_version"]["description"]
    assert "major" in desc
    assert "minor" in desc
    assert "旧记录不可比" in desc
