"""logic 类节点：条件分支 / 延迟。"""
from datetime import datetime, timedelta
from types import SimpleNamespace

from ...pyquery import match_filters
from ..registry import register
from .base import NodeContext, NodeResult, NodeType, WorkflowNodeError


def _infer_fields(record: dict) -> dict:
    """无表元数据时按记录值推断字段类型（int/decimal/bool，其余按字符串），供 match_filters 用。"""
    fbn = {}
    for k, v in (record or {}).items():
        if isinstance(v, bool):
            dt = "bool"
        elif isinstance(v, int):
            dt = "int"
        elif isinstance(v, float):
            dt = "decimal"
        else:
            dt = "varchar"
        fbn[k] = SimpleNamespace(field_name=k, label=k, data_type=dt)
    return fbn


@register
class ConditionNode(NodeType):
    type = "condition"
    name = "条件分支"
    category = "logic"
    description = "对一条记录按条件判断，走「是/否」两个分支"
    config_schema = {
        "type": "object",
        "required": ["record", "rules"],
        "properties": {
            "record": {"type": "object", "title": "判断对象", "description": "整体注入，如 {trigger.record}"},
            "table_id": {"type": "integer", "format": "table-ref", "title": "关联数据表（提供字段类型，可选）"},
            "logic": {"type": "string", "enum": ["AND", "OR"], "default": "AND", "title": "条件组合"},
            "rules": {"type": "array", "title": "条件规则", "description": "[{field, op, value}]，操作符与数据表筛选一致"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {"matched": {"type": "boolean"}, "branch": {"type": "string", "enum": ["true", "false"]}},
    }

    def execute(self, ctx: NodeContext) -> NodeResult:
        record = ctx.config.get("record")
        if not isinstance(record, dict):
            raise WorkflowNodeError("判断对象为空或不是记录（请用 {trigger.record} 这类整体引用）")
        table_id = ctx.config.get("table_id")
        if table_id:
            from ... import dyn_engine
            _, fields = dyn_engine.load_meta(ctx.db, table_id)
            fbn = {f.field_name: f for f in fields}
        else:
            fbn = _infer_fields(record)
        filters = {"logic": ctx.config.get("logic") or "AND", "rules": ctx.config.get("rules") or []}
        matched = match_filters(record, fbn, filters)
        return NodeResult(output={"matched": matched, "branch": "true" if matched else "false"})


@register
class DelayNode(NodeType):
    type = "delay"
    name = "延迟等待"
    category = "logic"
    description = "暂停流程，到期后自动继续（如「1 小时后再检查一次」）"
    config_schema = {
        "type": "object",
        "required": ["minutes"],
        "properties": {
            "minutes": {"type": "integer", "title": "等待分钟数", "minimum": 1, "maximum": 43200},
        },
    }
    output_schema = {"type": "object", "properties": {"until": {"type": "string"}}}

    def execute(self, ctx: NodeContext) -> NodeResult:
        minutes = ctx.config.get("minutes")
        if not isinstance(minutes, int) or minutes < 1:
            raise WorkflowNodeError("等待分钟数必须 ≥ 1")
        until = datetime.now() + timedelta(minutes=minutes)
        return NodeResult(status="waiting", resume_after=until,
                          output={"until": until.isoformat(sep=" ")})
