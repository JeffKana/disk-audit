"""T-07（待办 E1）知识库 schema v1 单元测试。

覆盖验收①（schema 自身合法性检查）、②（5 条代表性样例通过校验）、
③（缺 source 字段被拒绝）、④（分类枚举与原型 12 类对照）。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("validate_knowledge", _REPO / "tools" / "validate_knowledge.py")
validate_knowledge = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(validate_knowledge)

SCHEMA = validate_knowledge.load_schema(_REPO / "knowledge" / "schema.json")
EXAMPLES = (_REPO / "knowledge" / "examples" / "examples.v1.json").read_text(encoding="utf-8")

# 原型 12 类 ground truth（docs/upstream/prototype/analyze_appdata.py 第 31~42 行常量）
PROTOTYPE_12_CATEGORIES = [
    "系统组件",
    "兼容链接·严禁删除",
    "已安装应用",
    "使用中(无安装记录)",
    "更新缓存",
    "开发缓存",
    "缓存/转储",
    "游戏数据",
    "残留候选·高置信",
    "残留候选·中置信",
    "残留候选·低置信",
    "容器(已下钻)",
]


def test_schema_self_check_passes():
    """验收①：JSON Schema 文件通过自身合法性检查。"""
    assert validate_knowledge.check_schema(SCHEMA) == []
    assert validate_knowledge.main(["--check-schema"]) == 0


def test_five_representative_samples_pass():
    """验收②：5 条代表性样例全部通过校验（容器格式整体过 CLI）。"""
    import json

    data = json.loads(EXAMPLES)
    assert len(data["entries"]) == 5
    for entry in data["entries"]:
        assert validate_knowledge.validate(entry, SCHEMA) == [], entry["name"]


def test_missing_source_rejected():
    """验收③：缺 source 字段的样例被校验拒绝。"""
    entry = {
        "name": "sample",
        "product": "示例产品",
        "category": "开发缓存",
        "lifecycle": "未知",
    }
    errors = validate_knowledge.validate(entry, SCHEMA)
    assert any("source" in e for e in errors)


def test_invalid_category_rejected():
    entry = {
        "name": "sample",
        "product": "示例产品",
        "category": "不存在的分类",
        "lifecycle": "未知",
        "source": "本机实测",
    }
    errors = validate_knowledge.validate(entry, SCHEMA)
    assert any("category" in e and "枚举" in e for e in errors)


def test_invalid_lifecycle_rejected():
    entry = {
        "name": "sample",
        "product": "示例产品",
        "category": "开发缓存",
        "lifecycle": "已停用",  # 枚举外（正确写法为"已停止"）
        "source": "公开软件名",
    }
    assert validate_knowledge.validate(entry, SCHEMA) != []


def test_unknown_field_rejected():
    entry = {
        "name": "sample",
        "product": "示例产品",
        "category": "开发缓存",
        "lifecycle": "未知",
        "source": "本机实测",
        "confidence": "高",  # schema v1 无此字段
    }
    errors = validate_knowledge.validate(entry, SCHEMA)
    assert any("confidence" in e for e in errors)


def test_regex_family_allows_null_and_string():
    base = {
        "name": "sample",
        "product": "示例产品",
        "category": "开发缓存",
        "lifecycle": "未知",
        "source": "本机实测",
    }
    assert validate_knowledge.validate({**base, "regex_family": None}, SCHEMA) == []
    assert validate_knowledge.validate({**base, "regex_family": "updater-suffix"}, SCHEMA) == []
    assert validate_knowledge.validate({**base, "regex_family": 3}, SCHEMA) != []


def test_category_enum_matches_prototype_12():
    """验收④：schema 的 category 枚举与原型 12 类一一对照（顺序无关、集合相等）。"""
    schema_enum = SCHEMA["properties"]["category"]["enum"]
    assert sorted(schema_enum) == sorted(PROTOTYPE_12_CATEGORIES)
    assert len(schema_enum) == 12


def test_cli_exit_codes(tmp_path, capsys):
    good = tmp_path / "good.json"
    good.write_text(EXAMPLES, encoding="utf-8")
    assert validate_knowledge.main([str(good)]) == 0
    bad = tmp_path / "bad.json"
    bad.write_text(
        '[{"name": "x", "product": "y", "category": "开发缓存", "lifecycle": "未知"}]',
        encoding="utf-8",
    )
    assert validate_knowledge.main([str(bad)]) == 1
    assert "source" in capsys.readouterr().out
    assert validate_knowledge.main([str(tmp_path / "nope.json")]) == 2
