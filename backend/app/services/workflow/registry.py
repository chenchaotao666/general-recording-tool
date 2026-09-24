"""节点注册表：引擎只通过 REGISTRY 找节点实现，不含任何具体节点类型的分支逻辑。规范 §4.2。"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .nodes.base import NodeType

REGISTRY: dict[str, type[NodeType]] = {}


def register(node_cls: type[NodeType]) -> type[NodeType]:
    """类装饰器：@register 后节点类型即被引擎/前端目录/AI 生成自动发现。"""
    assert node_cls.type, "节点类型必须定义 type"
    assert node_cls.type not in REGISTRY, f"节点类型重复注册: {node_cls.type}"
    REGISTRY[node_cls.type] = node_cls
    return node_cls


def get_node_types() -> list[dict]:
    """供 GET /api/workflows/node-types：前端画布与 AI 生成都从这里取。"""
    return [
        {
            "type": t.type, "name": t.name, "category": t.category,
            "description": t.description,
            "config_schema": t.config_schema, "output_schema": t.output_schema,
        }
        for t in REGISTRY.values()
    ]


_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
}


def validate_config(node_label: str, schema: dict, config: dict) -> list[str]:
    """按 config_schema（JSON Schema 子集）做轻量校验，返回错误信息列表（空 = 通过）。

    含 { 的字符串视为模板表达式，跳过类型/枚举校验（渲染发生在执行前）。
    """
    errors = []
    config = config or {}
    props = (schema or {}).get("properties") or {}
    for req in (schema or {}).get("required") or []:
        v = config.get(req)
        if v is None or (isinstance(v, str) and not v.strip()):
            errors.append(f"{node_label}：缺少必填配置 {req}")
    for key, spec in props.items():
        if key not in config or config[key] is None:
            continue
        v = config[key]
        if isinstance(v, str) and "{" in v:
            continue  # 模板字段
        expected = spec.get("type")
        if expected in _TYPE_CHECKS and not _TYPE_CHECKS[expected](v):
            errors.append(f"{node_label}：配置 {key} 应为 {expected}")
        if "enum" in spec and v not in spec["enum"]:
            errors.append(f"{node_label}：配置 {key} 取值无效（可选：{'/'.join(map(str, spec['enum']))}）")
    return errors
