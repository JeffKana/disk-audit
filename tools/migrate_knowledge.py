"""知识库种子迁移（待办 E2，任务卡 T-08）：原型知识库迁入 schema v1，只迁移不修改语义。

依据：T-07 产物（knowledge/schema.json + tools/validate_knowledge.py）；
docs/upstream/prototype/analyze_appdata.py 内置知识库 KB_ROAM/KB_LOCAL/KB_ANY
（文档口径 ~260 条，条目为 4 元组：名称 -> (归属, 分类, 置信度, 说明)）。
逐条补全 source 登记字段（P10 来源铁律 /《项目治理》§6）。

语义保持决策（D-执行，随执行记录留档）：
  - lifecycle 全部"未知"：原型无公开生命周期依据，治理 §6 禁止登记无依据结论；
  - source 全部"本机实测"：原型 KB 依据本机 320 项长尾实测整理（方案 P10/第八节）；
  - 原型"置信度"无 schema v1 字段，以"置信度：X（原型遗留字段）"并入 notes，
    不改变判定语义；
  - 重复键保留首次出现（ROAM > LOCAL > ANY 顺序），丢弃者计入统计与未尽事项。
用法：python tools/migrate_knowledge.py [--out knowledge/entries.json]
退出码：0=迁移成功且全部通过 schema 校验；2=原型解析/条目形态错误；1=校验失败。
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TOOLS_DIR.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import validate_knowledge as vk  # noqa: E402  同目录校验脚本

DEFAULT_PROTOTYPE = _REPO_ROOT / "docs" / "upstream" / "prototype" / "analyze_appdata.py"
DEFAULT_OUT = _REPO_ROOT / "knowledge" / "entries.json"
KB_NAMES = ("KB_ROAM", "KB_LOCAL", "KB_ANY")
SCHEMA_VERSION = "knowledge.v1"


def _eval_node(node: ast.AST, env: dict[str, object]) -> object:
    """字面量求值：Constant/Name/Tuple/List/Dict/UnaryOp；其余拒绝（防执行任意代码）。"""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        raise ValueError(f"无法解析的名称：{node.id}")
    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(e, env) for e in node.elts)
    if isinstance(node, ast.List):
        return [_eval_node(e, env) for e in node.elts]
    if isinstance(node, ast.Dict):
        return {_eval_node(k, env): _eval_node(v, env) for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.Set):
        return {_eval_node(e, env) for e in node.elts}
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _eval_node(node.operand, env)
        return -value if isinstance(node.op, ast.USub) else +value
    raise ValueError(f"不支持的表达式：{type(node).__name__}")


def load_kb_dicts_from_text(source: str) -> tuple[dict, dict, dict]:
    """从原型脚本源码文本提取 KB_ROAM/KB_LOCAL/KB_ANY（ast 静态提取，不执行原型代码）。"""
    tree = ast.parse(source)
    env: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                env[node.targets[0].id] = _eval_node(node.value, env)
            except ValueError:
                continue  # 非字面量赋值（如 os.environ.get(...)）跳过
    found: dict[str, dict] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in KB_NAMES:
                value = _eval_node(node.value, env)
                if not isinstance(value, dict):
                    raise ValueError(f"{node.targets[0].id} 不是字面量 dict")
                found[node.targets[0].id] = value
    missing = [name for name in KB_NAMES if name not in found]
    if missing:
        raise ValueError(f"原型中缺少知识库定义：{', '.join(missing)}")
    return found["KB_ROAM"], found["KB_LOCAL"], found["KB_ANY"]


def load_kb_dicts(prototype_path: Path) -> tuple[dict, dict, dict]:
    return load_kb_dicts_from_text(prototype_path.read_text(encoding="utf-8"))


def migrate_entries(
    roam: dict, local: dict, any_: dict
) -> tuple[list[dict], list[str], list[str]]:
    """迁移为 schema v1 条目。返回（条目列表, 丢弃的重复键, 形态错误）。

    只迁移不修改语义：字段映射见模块 docstring；形态错误的条目不迁、整体报错。
    """
    entries: list[dict] = []
    dropped: list[str] = []
    errors: list[str] = []
    merged: dict[str, tuple] = {}
    for dict_name, source_dict in (("KB_ROAM", roam), ("KB_LOCAL", local), ("KB_ANY", any_)):
        for name, value in source_dict.items():
            key = str(name)
            if key in merged:
                dropped.append(f"{key}（{dict_name}）")
                continue
            if not isinstance(value, tuple) or len(value) != 4:
                errors.append(f"{dict_name}[{key!r}]：条目应为 4 元组，实际 {type(value).__name__}")
                continue
            merged[key] = value
    for name, (product, category, confidence, note) in merged.items():
        notes_parts: list[str] = []
        if str(note):
            notes_parts.append(str(note))
        notes_parts.append(f"置信度：{confidence}（原型遗留字段）")
        entries.append(
            {
                "name": name,
                "product": str(product),
                "vendor": "",
                "aliases": [],
                "category": str(category),
                "lifecycle": "未知",
                "regex_family": None,
                "source": "本机实测",
                "notes": "；".join(notes_parts),
            }
        )
    return entries, dropped, errors


def build_output(entries: list[dict]) -> dict:
    return {"schema_version": SCHEMA_VERSION, "entries": entries}


def category_distribution(entries: list[dict], ordered_categories: list[str]) -> list[tuple[str, int]]:
    counts = {category: 0 for category in ordered_categories}
    for entry in entries:
        counts[entry["category"]] = counts.get(entry["category"], 0) + 1
    extra = [c for c in counts if c not in ordered_categories]
    ordered = [(c, counts[c]) for c in ordered_categories]
    ordered.extend((c, counts[c]) for c in extra)  # 超纲分类排在末尾并显式暴露
    return ordered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="原型知识库 → schema v1 种子迁移（只迁移不修改语义）")
    parser.add_argument("--prototype", type=Path, default=DEFAULT_PROTOTYPE, help="原型脚本路径")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="输出 JSON 路径")
    args = parser.parse_args(argv)

    try:
        roam, local, any_ = load_kb_dicts(args.prototype)
    except (OSError, SyntaxError, ValueError) as exc:
        print(f"[迁移] 原型解析失败：{exc}")
        return 2
    entries, dropped, errors = migrate_entries(roam, local, any_)
    if errors:
        print(f"[迁移] {len(errors)} 条形态错误，中止（只迁移不修改语义）：")
        for item in errors:
            print(f"  - {item}")
        return 2

    try:
        schema = vk.load_schema(_REPO_ROOT / "knowledge" / "schema.json")
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[迁移] schema 读取失败：{exc}")
        return 2
    validation_errors: list[str] = []
    for i, entry in enumerate(entries):
        validation_errors.extend(vk.validate(entry, schema, path=f"$[{i}]"))
    if validation_errors:
        print(f"[迁移] {len(validation_errors)} 处校验违规，中止：")
        for item in validation_errors[:20]:
            print(f"  - {item}")
        return 1

    args.out.write_text(
        json.dumps(build_output(entries), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("== E2 知识库种子迁移统计 ==")
    print(
        f"原型条目：KB_ROAM {len(roam)} + KB_LOCAL {len(local)} + KB_ANY {len(any_)}"
        f" = {len(roam) + len(local) + len(any_)} 条"
    )
    print(f"迁移后：{len(entries)} 条（丢弃重复键 {len(dropped)} 个：{', '.join(dropped) or '无'}）")
    print("分类分布（12 类）：")
    for category, count in category_distribution(entries, schema["properties"]["category"]["enum"]):
        print(f"  {category}：{count}")
    print("正则族数：0（原型无条目级正则族标注；*-updater 为原型代码级规则，未迁为条目）")
    print(f"source 空值：{sum(1 for e in entries if not e['source'])}；lifecycle 非'未知'：{sum(1 for e in entries if e['lifecycle'] != '未知')}")
    print("== 抽样对照（按名称排序前 10 条，迁移前 → 迁移后）==")
    for entry in sorted(entries, key=lambda e: e["name"])[:10]:
        raw = [v for v in (roam.get(entry["name"]), local.get(entry["name"]), any_.get(entry["name"])) if v is not None][0]
        print(f"  {entry['name']!r}:")
        print(f"    前：{raw!r}")
        print(f"    后：{json.dumps(entry, ensure_ascii=False)}")
    print(f"[迁移] 输出已写入：{args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
