"""data 类节点：查询 / 新增 / 更新记录 / 汇总统计，全部走 dyn_engine（含校验与审计日志）。"""
import json

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
            "filters": {"type": "object", "title": "筛选条件", "description": "{logic: AND|OR, rules: [{field, op, value}]}，field/value 可插入 {模板变量}"},
            "limit": {"type": "integer", "title": "条数上限", "default": 100, "minimum": 1, "maximum": 500},
            "order_by": {"type": "string", "title": "排序字段", "description": "字段名，可插入 {模板变量}"},
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


# ---------- 汇总统计 ----------

AGG_OPS = {
    "count": "计数", "count_distinct": "去重计数", "sum": "求和",
    "avg": "平均", "max": "最大", "min": "最小",
}


def _nums(records: list[dict], field: str) -> list[float]:
    """取数值列：跳过 None/bool/无法转数的值（含非标量项——列表元素不一定是 dict）。"""
    out = []
    for r in records:
        v = r.get(field) if isinstance(r, dict) else None
        if v is None or isinstance(v, bool):
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            continue
    return out


def _agg_value(op: str, records: list[dict], field: str | None):
    if op == "count":
        return len(records)
    if op == "count_distinct":
        return len({json.dumps(r.get(field) if isinstance(r, dict) else r, ensure_ascii=False, default=str)
                    for r in records})
    vals = _nums(records, field or "")
    if not vals:
        return 0 if op == "sum" else None
    if op == "sum":
        return round(sum(vals), 4)
    if op == "avg":
        return round(sum(vals) / len(vals), 4)
    if op == "max":
        return max(vals)
    if op == "min":
        return min(vals)
    raise WorkflowNodeError(f"未知统计方式：{op}")


def _run_aggs(records: list[dict], aggs: list[dict]) -> dict:
    """stats 键：优先用显示名（模板里好认），否则 op_field 自动生成。"""
    stats = {}
    for a in aggs:
        if not isinstance(a, dict):
            continue
        op = a.get("op")
        if op not in AGG_OPS:
            raise WorkflowNodeError(f"未知统计方式：{op}（可选：{'/'.join(AGG_OPS)}）")
        field = a.get("field") or None
        if op not in ("count",) and not field:
            raise WorkflowNodeError(f"统计方式「{AGG_OPS[op]}」需要选择字段")
        key = str(a.get("title") or "").strip() or (f"{op}_{field}" if field else op)
        stats[key] = _agg_value(op, records, field)
    return stats


@register
class DedupeNode(NodeType):
    type = "dedupe"
    name = "去重"
    category = "data"
    description = "对任意列表去重（表记录、LLM 输出的数组、分组统计结果等）：按字段值保留第一条，不填字段则整项完全相同才去重"
    config_schema = {
        "type": "object",
        "required": ["records"],
        "properties": {
            "records": {"type": "string", "format": "template", "title": "记录列表",
                        "description": "整体引用，如 {nodes.q_1.records}"},
            "field": {"type": "string", "title": "去重字段（可选）",
                      "description": "记录里的字段名（如 customer），按该字段值去重；不是列表变量——列表填在「记录列表」；留空 = 整条记录去重"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {"records": {"type": "array"}, "count": {"type": "integer"}, "removed": {"type": "integer"}},
    }

    def execute(self, ctx: NodeContext) -> NodeResult:
        records = ctx.config.get("records")
        if isinstance(records, str):
            try:
                records = json.loads(records)
            except ValueError:
                records = None
        if not isinstance(records, list):
            raise WorkflowNodeError("记录列表为空或不是列表（请用 {nodes.查询节点.records} 整体引用）")
        field = (ctx.config.get("field") or "").strip()
        seen, out = set(), []
        for r in records:
            # 字段去重只对 dict 项生效；标量项（字符串/数字列表）或留空字段 → 整项判重
            if field and isinstance(r, dict):
                key = json.dumps(r.get(field), ensure_ascii=False, default=str)
            else:
                key = json.dumps(r, ensure_ascii=False, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return NodeResult(output={"records": out, "count": len(out), "removed": len(records) - len(out)})


@register
class AggregateNode(NodeType):
    type = "aggregate"
    name = "汇总统计"
    category = "data"
    description = "对上游查询出的记录列表做求和/计数/平均等统计，可选按字段分组"
    config_schema = {
        "type": "object",
        "required": ["records", "aggs"],
        "properties": {
            "records": {"type": "string", "format": "template", "title": "记录列表",
                        "description": "整体引用，如 {nodes.q_1.records}"},
            "group_by": {"type": "string", "title": "分组字段（可选）",
                         "description": "记录里的字段名（如 salesperson），按该字段分组统计；不是列表变量"},
            "aggs": {"type": "array", "title": "统计项",
                     "description": "[{op: count|sum|avg|max|min|count_distinct, field, title}]"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {"count": {"type": "integer"}, "stats": {"type": "object"},
                       "groups": {"type": "array"}},
    }

    def execute(self, ctx: NodeContext) -> NodeResult:
        records = ctx.config.get("records")
        if isinstance(records, str):
            try:
                records = json.loads(records)
            except ValueError:
                records = None
        if not isinstance(records, list):
            raise WorkflowNodeError("记录列表为空或不是列表（请用 {nodes.查询节点.records} 整体引用）")
        aggs = ctx.config.get("aggs")
        if not isinstance(aggs, list) or not aggs:
            raise WorkflowNodeError("请至少配置一个统计项")

        stats = _run_aggs(records, aggs)
        groups = []
        group_by = (ctx.config.get("group_by") or "").strip()
        if group_by:
            by_key: dict[str, list] = {}
            for r in records:
                by_key.setdefault(str(r.get(group_by) if isinstance(r, dict) else None), []).append(r)
            groups = [{"key": k, **_run_aggs(rs, aggs)} for k, rs in by_key.items()]
        return NodeResult(output={"count": len(records), "stats": stats, "groups": groups})
