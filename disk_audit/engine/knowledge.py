"""知识库装载与匹配（待办 D1，任务卡 T2-02；待办 E1/E2 已定稿 schema）。

依据：方案第四节架构③（知识库为判定第二层）、《项目治理》§6（来源登记字段、
生命周期只允许登记有公开依据的结论）。I/O 仅限 load_knowledge（采集层）；
build_knowledge / match_entry 为纯构造与纯查询。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class KnowledgeEntry:
    """knowledge.v1 单条条目（9 字段，见 knowledge/schema.json）。"""

    name: str
    product: str
    vendor: str
    aliases: tuple[str, ...]
    category: str
    lifecycle: str
    regex_family: str | None
    source: str
    notes: str


@dataclass(frozen=True)
class KnowledgeBase:
    """条目集合 + name/别名小写索引（构建后只读查询）。"""

    entries: tuple[KnowledgeEntry, ...]
    _index: dict[str, KnowledgeEntry] = field(default_factory=dict, repr=False, compare=False)


def build_knowledge(entries: list[dict]) -> KnowledgeBase:
    """纯构造：条目 dict 列表 → KnowledgeBase（name 与别名建小写索引）。"""
    parsed: list[KnowledgeEntry] = []
    index: dict[str, KnowledgeEntry] = {}
    for raw in entries:
        entry = KnowledgeEntry(
            name=raw["name"],
            product=raw["product"],
            vendor=raw.get("vendor", ""),
            aliases=tuple(raw.get("aliases") or []),
            category=raw["category"],
            lifecycle=raw["lifecycle"],
            regex_family=raw.get("regex_family"),
            source=raw["source"],
            notes=raw.get("notes", ""),
        )
        parsed.append(entry)
        index.setdefault(entry.name.lower(), entry)
        for alias in entry.aliases:
            index.setdefault(alias.lower(), entry)
    return KnowledgeBase(entries=tuple(parsed), _index=index)


def match_entry(kb: KnowledgeBase, name: str) -> KnowledgeEntry | None:
    """目录名精确匹配（name/别名，大小写不敏感）。

    包含匹配不在知识库层做（防子串误判，D6 口径：仅注册表/Appx 匹配按
    原型修复口径限制语境）。
    """
    return kb._index.get(name.lower())


def default_knowledge_path() -> Path:
    """仓库内知识库路径（打包形态在 J1 另行定址；当前引擎随仓库分发）。"""
    return Path(__file__).resolve().parents[2] / "knowledge" / "entries.json"


def load_knowledge(path: Path | None = None) -> KnowledgeBase:
    """装载知识库 JSON（采集层 I/O）；支持 {"entries": [...]} 容器或纯数组。"""
    data = json.loads((path or default_knowledge_path()).read_text(encoding="utf-8"))
    entries = data["entries"] if isinstance(data, dict) else data
    return build_knowledge(entries)
