"""data 类节点：查询 / 新增 / 更新记录，全部走 dyn_engine（含校验与审计日志）。"""
from sqlalchemy import or_, select

from ... import dyn_engine
from ...pyquery import match_filters, sort_records
from ..registry import register
from .base import NodeContext, NodeResult, NodeType, WorkflowNodeError


def query_table(db, table_id: int, filters: dict | None, limit: int,
                order_by: str | None, order_desc: bool) -> list[dict]:
    """双存储模式统一的查询路径，语义与 dyn_engine.list_records / pyquery 对齐。"""
    mt, fields = dyn_engine.load_meta(db, table_id)
    fbn = {f.field_name: f for f in fields}
    limit = max(1, min(int(limit or 100), 500))

    if mt.storage_mode == "json":
        from ... import json_store
        recs = json_store.all_dicts(db, mt.id, fields, normalized=True)
        recs = [r for r in recs if match_filters(r, fbn, filters)]
        recs = sort_records(recs, order_by, "desc" if order_desc else "asc", fbn)
        return [{k: dyn_engine.serialize_value(v) for k, v in r.items()} for r in recs[:limit]]

    _, fields, table = dyn_engine.load_business(db, table_id)
    rules = (filters or {}).get("rules") or []
    conds = [dyn_engine.build_condition(table, fbn, r) for r in rules]
    if (filters or {}).get("logic") == "OR" and len(conds) > 1:
        conds = [or_(*conds)]
    stmt = select(table).where(*conds)
    col = table.c[order_by] if order_by and order_by in table.c else table.c.id
    stmt = stmt.order_by(col.desc() if order_desc else col.asc()).limit(limit)
    return [dyn_engine.row_to_dict(r) for r in db.execute(stmt).mappings().all()]


@register
class QueryRecordsNode(NodeType):
    type = "query_records"
    name = "查询记录"
    category = "data"
    description = "从数据表按条件查询记录，供下游节点使用"
    config_schema = {
        "type": "object",
        "required": ["table_id"],
        "properties": {
            "table_id": {"type": "integer", "format": "table-ref", "title": "数据表"},
            "filters": {"type": "object", "title": "筛选条件", "description": "{logic: AND|OR, rules: [{field, op, value}]}"},
            "limit": {"type": "integer", "title": "条数上限", "default": 100, "minimum": 1, "maximum": 500},
            "order_by": {"type": "string", "title": "排序字段"},
            "order_desc": {"type": "boolean", "title": "倒序", "default": True},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {"records": {"type": "array"}, "count": {"type": "integer"}},
    }

    def execute(self, ctx: NodeContext) -> NodeResult:
        table_id = ctx.config.get("table_id")
        if not table_id:
            raise WorkflowNodeError("未配置数据表")
        records = query_table(
            ctx.db, table_id, ctx.config.get("filters"),
            ctx.config.get("limit") or 100,
            ctx.config.get("order_by"), bool(ctx.config.get("order_desc", True)),
        )
        return NodeResult(output={"records": records, "count": len(records)})


@register
class CreateRecordNode(NodeType):
    type = "create_record"
    name = "新增记录"
    category = "data"
    description = "向数据表写入一条新记录，字段值支持模板引用上游数据"
    config_schema = {
        "type": "object",
        "required": ["table_id", "field_mapping"],
        "properties": {
            "table_id": {"type": "integer", "format": "table-ref", "title": "数据表"},
            "field_mapping": {"type": "object", "title": "字段赋值", "description": "{field_name: 模板表达式}"},
        },
    }
    output_schema = {"type": "object", "properties": {"record": {"type": "object"}}}

    def execute(self, ctx: NodeContext) -> NodeResult:
        table_id = ctx.config.get("table_id")
        mapping = ctx.config.get("field_mapping")
        if not table_id or not isinstance(mapping, dict) or not mapping:
            raise WorkflowNodeError("未配置数据表或字段赋值")
        data = {k: v for k, v in mapping.items() if v is not None}
        record = dyn_engine.create_record(ctx.db, table_id, data, user=ctx.username)
        return NodeResult(output={"record": record})


@register
class UpdateRecordNode(NodeType):
    type = "update_record"
    name = "更新记录"
    category = "data"
    description = "按条件定位数据表记录并更新字段（最多 100 条）"
    config_schema = {
        "type": "object",
        "required": ["table_id", "match_filters", "field_mapping"],
        "properties": {
            "table_id": {"type": "integer", "format": "table-ref", "title": "数据表"},
            "match_filters": {"type": "object", "title": "定位条件", "description": "{logic, rules:[{field,op,value}]}"},
            "field_mapping": {"type": "object", "title": "字段赋值", "description": "{field_name: 模板表达式}"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {"count": {"type": "integer"}, "records": {"type": "array"}},
    }

    def execute(self, ctx: NodeContext) -> NodeResult:
        table_id = ctx.config.get("table_id")
        mapping = ctx.config.get("field_mapping")
        if not table_id or not isinstance(mapping, dict) or not mapping:
            raise WorkflowNodeError("未配置数据表或字段赋值")
        targets = query_table(ctx.db, table_id, ctx.config.get("match_filters"), 100, None, True)
        if not targets:
            return NodeResult(output={"count": 0, "records": []})
        data = {k: v for k, v in mapping.items() if v is not None}
        updated = [
            dyn_engine.update_record(ctx.db, table_id, r["id"], data, user=ctx.username)
            for r in targets
        ]
        return NodeResult(output={"count": len(updated), "records": updated})
