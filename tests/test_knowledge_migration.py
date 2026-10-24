"""T-08（待办 E2）知识库种子迁移单元测试。

覆盖：ast 字面量提取（含 CAT_* 常量解析与非字面量赋值跳过）、字段映射语义保持、
重复键去重、形态错误中止、迁移产物通过 schema 校验；另含对真实原型的集成校验
（迁移条目数 ≥ 260 且全部通过校验，即验收①/②的可执行形态）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_TOOLS = _REPO / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
_SPEC = importlib.util.spec_from_file_location("migrate_knowledge", _TOOLS / "migrate_knowledge.py")
migrate_knowledge = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(migrate_knowledge)

vk = migrate_knowledge.vk
SCHEMA = vk.load_schema(_REPO / "knowledge" / "schema.json")
PROTOTYPE = _REPO / "docs" / "upstream" / "prototype" / "analyze_appdata.py"

SYNTHETIC = """
CAT_A = '系统组件'
CAT_B = '开发缓存'
LOCALAPPDATA = os.environ.get('LOCALAPPDATA')
KB_ROAM = {
    'alpha': ('Product A', CAT_A, '高', 'note a'),
    'dup': ('Dup via roam', CAT_A, '低', ''),
}
KB_LOCAL = {
    'beta': ('Product B', CAT_B, '中', 'note b'),
    'dup': ('Dup via local', CAT_B, '高', 'dup note'),
}
KB_ANY = {}
"""


@pytest.fixture(scope="module")
def synthetic():
    roam, local, any_ = migrate_knowledge.load_kb_dicts_from_text(SYNTHETIC)
    return roam, local, any_


def test_load_kb_dicts_resolves_constants(synthetic):
    roam, local, any_ = synthetic
    assert roam["alpha"] == ("Product A", "系统组件", "高", "note a")
    assert local["beta"][1] == "开发缓存"
    assert any_ == {}


def test_migrate_field_mapping(synthetic):
    roam, local, any_ = synthetic
    entries, dropped, errors = migrate_knowledge.migrate_entries(roam, local, any_)
    assert errors == []
    by_name = {e["name"]: e for e in entries}
    alpha = by_name["alpha"]
    assert alpha["product"] == "Product A"
    assert alpha["category"] == "系统组件"
    assert alpha["lifecycle"] == "未知"
    assert alpha["source"] == "本机实测"
    assert alpha["vendor"] == ""
    assert alpha["aliases"] == []
    assert alpha["regex_family"] is None
    assert alpha["notes"] == "note a；置信度：高（原型遗留字段）"
    beta = by_name["beta"]
    assert beta["notes"] == "note b；置信度：中（原型遗留字段）"


def test_migrate_empty_note_still_records_confidence(synthetic):
    roam, local, any_ = synthetic
    entries, _dropped, _errors = migrate_knowledge.migrate_entries(roam, local, any_)
    dup = next(e for e in entries if e["name"] == "dup")
    assert dup["notes"] == "置信度：低（原型遗留字段）"  # 保留首次出现（ROAM 优先）


def test_migrate_dedup_keeps_first(synthetic):
    roam, local, any_ = synthetic
    entries, dropped, errors = migrate_knowledge.migrate_entries(roam, local, any_)
    assert len(entries) == 3
    assert dropped == ["dup（KB_LOCAL）"]
    assert errors == []


def test_migrate_bad_arity_aborts():
    roam = {"bad": ("Product", "cat")}  # 3 元组
    entries, dropped, errors = migrate_knowledge.migrate_entries(roam, {}, {})
    assert entries == []
    assert errors and "4 元组" in errors[0]


def test_migrated_entries_pass_schema(synthetic):
    """合成条目逐条通过 schema 校验（与 T-07 校验器联通）。"""
    roam, local, any_ = synthetic
    entries, _dropped, errors = migrate_knowledge.migrate_entries(roam, local, any_)
    assert errors == []
    for entry in entries:
        assert vk.validate(entry, SCHEMA) == [], entry["name"]


def test_real_prototype_integration():
    """真实原型：迁移条目 ≥ 260 且全部通过 schema 校验（验收①②可执行形态）。"""
    if not PROTOTYPE.exists():
        pytest.skip("原型文件缺失")
    roam, local, any_ = migrate_knowledge.load_kb_dicts(PROTOTYPE)
    entries, dropped, errors = migrate_knowledge.migrate_entries(roam, local, any_)
    assert errors == []
    assert len(entries) >= 260
    assert all(e["source"] == "本机实测" for e in entries)
    assert all(e["lifecycle"] == "未知" for e in entries)
    for entry in entries:
        assert vk.validate(entry, SCHEMA) == [], entry["name"]
    categories = {e["category"] for e in entries}
    assert categories <= set(SCHEMA["properties"]["category"]["enum"])


def test_category_distribution_ordered_and_extra_exposed(synthetic):
    roam, local, any_ = synthetic
    entries, _dropped, _errors = migrate_knowledge.migrate_entries(roam, local, any_)
    dist_list = migrate_knowledge.category_distribution(
        entries, SCHEMA["properties"]["category"]["enum"]
    )
    dist = dict(dist_list)
    assert dist["开发缓存"] == 1  # beta
    assert dist["系统组件"] == 2  # alpha + dup（合成 KB 用的都是真实 12 类）
    # 12 类按固定顺序在前，超纲分类排末尾显式暴露
    assert dist_list[-1][0] in SCHEMA["properties"]["category"]["enum"]
    extra = dict(migrate_knowledge.category_distribution(
        [{"category": "开发缓存"}, {"category": "不存在的类目"}],
        SCHEMA["properties"]["category"]["enum"],
    ))
    assert extra["不存在的类目"] == 1  # 超纲分类不静默丢弃
