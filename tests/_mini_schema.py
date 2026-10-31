"""JSON Schema 子集校验器（开发期专用，不进运行时、不引第三方包）。

自 tests/test_report_schema.py 抽出共用（T2-02 判定引擎输出校验复用），
支持本仓库 schema 用到的关键字：$defs / $ref / const / enum / type /
required / additionalProperties / minLength / minimum / minItems / items。
"""
from __future__ import annotations


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
