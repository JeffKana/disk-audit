"""知识库 schema v1 校验脚本（待办 E1，任务卡 T-07）。

零第三方依赖约束下自行实现的 JSON Schema 子集校验器（支持 type/required/
properties/additionalProperties/enum/const/items/minLength/minimum；不引入
jsonschema 包——依据《开发规范》§1 运行时零第三方依赖与 §2 白名单机制）。
用法：
  python tools/validate_knowledge.py <条目文件.json>   # 单对象或数组
  python tools/validate_knowledge.py --check-schema    # schema.json 自身合法性检查（验收①）
退出码：0=通过；1=校验失败；2=输入/环境错误。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = _REPO_ROOT / "knowledge" / "schema.json"


def load_schema(schema_path: Path) -> dict:
    return json.loads(schema_path.read_text(encoding="utf-8"))


def check_schema(schema: dict) -> list[str]:
    """schema 文件自身合法性检查（本脚本支持的子集结构）。"""
    errors: list[str] = []
    if not isinstance(schema, dict):
        return ["schema 根必须是对象"]
    if not str(schema.get("$schema", "")).startswith("https://json-schema.org/draft/2020-12"):
        errors.append("$schema 必须声明 draft 2020-12")
    if schema.get("type") != "object":
        errors.append("根 type 必须是 object")
    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        errors.append("properties 必须是非空对象")
        properties = {}
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(isinstance(k, str) for k in required):
        errors.append("required 必须是字符串数组")
        required = []
    for key in required:
        if key not in properties:
            errors.append(f"required 中的 {key} 未在 properties 定义")
    for name, spec in properties.items():
        if not isinstance(spec, dict) or "type" not in spec:
            errors.append(f"属性 {name} 缺少 type")
            continue
        enum = spec.get("enum")
        if enum is not None and (not isinstance(enum, list) or not enum):
            errors.append(f"属性 {name} 的 enum 必须是非空数组")
    return errors


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


def validate(instance, schema: dict, path: str = "$") -> list[str]:
    """按 schema 子集校验一个实例，返回违规清单（空=通过）。"""
    errors: list[str] = []
    expected_types = schema.get("type")
    if expected_types is not None:
        types = expected_types if isinstance(expected_types, list) else [expected_types]
        if not any(_type_ok(instance, t) for t in types):
            errors.append(
                f"{path}：类型应为 {'/'.join(types)}，实际为 {type(instance).__name__}"
            )
            return errors
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}：值 {instance!r} 不在枚举 {schema['enum']}")
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}：值 {instance!r} ≠ 常量 {schema['const']!r}")
    if isinstance(instance, str) and "minLength" in schema:
        if len(instance) < schema["minLength"]:
            errors.append(f"{path}：字符串长度 {len(instance)} < {schema['minLength']}")
    if (
        isinstance(instance, int)
        and not isinstance(instance, bool)
        and "minimum" in schema
        and instance < schema["minimum"]
    ):
        errors.append(f"{path}：数值 {instance} < 最小值 {schema['minimum']}")
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
                errors.extend(validate(value, properties[key], f"{path}.{key}"))
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}：数组元素数 {len(instance)} < {schema['minItems']}")
        items = schema.get("items")
        if isinstance(items, dict):
            for i, item in enumerate(instance):
                errors.extend(validate(item, items, f"{path}[{i}]"))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="知识库条目校验（schema v1，零依赖实现）")
    parser.add_argument("file", nargs="?", type=Path, help="条目 JSON 文件（单对象或数组）")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="schema 文件路径")
    parser.add_argument(
        "--check-schema", action="store_true", help="只检查 schema 文件自身合法性"
    )
    args = parser.parse_args(argv)

    try:
        schema = load_schema(args.schema)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[校验] schema 读取失败：{exc}")
        return 2

    if args.check_schema:
        errors = check_schema(schema)
        if errors:
            print(f"[校验] schema 自身不合法，{len(errors)} 处：")
            for item in errors:
                print(f"  - {item}")
            return 1
        print(f"[校验] schema 自身合法：{args.schema}")
        return 0

    if args.file is None:
        parser.print_help()
        return 2
    try:
        data = json.loads(args.file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[校验] 条目文件读取失败：{exc}")
        return 2
    # 支持三种装载形态：纯数组；带 entries 数组的容器（如 examples.v1.json、
    # entries.json）；单个条目对象。schema 本身只约束单个条目。
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and isinstance(data.get("entries"), list):
        items = data["entries"]
    else:
        items = [data]
    all_errors: list[str] = []
    for i, item in enumerate(items):
        all_errors.extend(validate(item, schema, path=f"$[{i}]"))
    if all_errors:
        print(f"[校验] {len(items)} 条中存在 {len(all_errors)} 处违规：")
        for item in all_errors:
            print(f"  - {item}")
        return 1
    print(f"[校验] 通过：{len(items)} 条条目符合 schema v1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
