"""logic 类节点：条件分支 / 多路分支 / 逐条处理 / 延迟。"""
import json
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


def _eval_rule(record: dict, fbn: dict, rule: dict) -> bool:
    """评估单条规则。field 两种形态都兼容：
    - 键名（旧配置，如 urgency）：从判断对象里按键取值；
    - 模板表达式（如 {nodes.llm_1.data.urgency}）：render_config 已渲染成实际值，
      渲染结果不是判断对象的键 → 直接拿它当左值比较。
    """
    field = rule.get("field")
    if isinstance(record, dict) and isinstance(field, str) and field in record:
        return match_filters(record, fbn, {"logic": "AND", "rules": [rule]})
    fb = _infer_fields({"v": field})
    return match_filters({"v": field}, fb, {"logic": "AND", "rules": [{**rule, "field": "v"}]})


@register
class ConditionNode(NodeType):
    type = "condition"
    name = "条件分支"
    category = "logic"
    description = "对一条记录按条件判断，走「是/否」两个分支"
    disabled_branch = "true"
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
        rules = filters["rules"]
        # 无规则恒真，与 pyquery.match_filters 语义一致
        matched = True if not rules else (
            all(_eval_rule(record, fbn, r) for r in rules if isinstance(r, dict))
            if filters["logic"] == "AND"
            else any(_eval_rule(record, fbn, r) for r in rules if isinstance(r, dict))
        )
        return NodeResult(output={"matched": matched, "branch": "true" if matched else "false"})


@register
class SwitchNode(NodeType):
    type = "switch"
    name = "多路分支"
    category = "logic"
    description = "按条件把记录分到多条路径（从上到下第一个命中的分支生效，都不命中走「默认」）"
    disabled_branch = "default"
    config_schema = {
        "type": "object",
        "required": ["record", "cases"],
        "properties": {
            "record": {"type": "object", "title": "判断对象", "description": "整体注入，如 {trigger.record}"},
            "table_id": {"type": "integer", "format": "table-ref", "title": "关联数据表（提供字段类型，可选）"},
            "cases": {"type": "array", "title": "分支规则",
                      "description": "[{label: 分支名, field, op, value}]，操作符与数据表筛选一致"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {"case": {"type": "string"}, "branch": {"type": "string"}},
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
        cases = ctx.config.get("cases") or []
        labels = [str(c.get("label") or "").strip() for c in cases if isinstance(c, dict)]
        if not labels or any(not lb for lb in labels) or len(set(labels)) != len(labels):
            raise WorkflowNodeError("每个分支都要填分支名，且不能重复")
        for c in cases:
            if _eval_rule(record, fbn, c):
                label = str(c.get("label")).strip()
                return NodeResult(output={"case": label, "branch": label})
        return NodeResult(output={"case": "default", "branch": "default"})


@register
class ForeachNode(NodeType):
    """逐条处理：对列表逐项执行循环体。引擎据 is_loop 维护 context["loops"][node_id] 计数。

    画布接线：「每条」(branch=loop) 出口接循环体，循环体末尾用普通边连回本节点（回边），
    「完成」(branch=done) 出口接后续节点。每次执行输出当前条目，计数由引擎推进。
    """
    type = "foreach"
    name = "逐条处理"
    category = "logic"
    description = "对列表（如查询结果）逐条执行循环体分支：每条记录各走一遍下游节点"
    disabled_branch = "done"   # 停用时跳过循环，直接走「完成」
    is_loop = True
    config_schema = {
        "type": "object",
        "required": ["items"],
        "properties": {
            "items": {"type": "string", "format": "template", "title": "记录列表",
                      "description": "整体引用上游节点的列表输出，如 {nodes.q_1.records}（查询/更新节点的「记录列表」）"},
            "max_items": {"type": "integer", "title": "最多处理条数", "default": 50,
                          "minimum": 1, "maximum": 200},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {"item": {"type": "object"}, "index": {"type": "integer"}, "count": {"type": "integer"}},
    }

    MAX_ITEMS = 200   # 硬上限：循环每步都落库，防失控

    def execute(self, ctx: NodeContext) -> NodeResult:
        items = ctx.config.get("items")
        if isinstance(items, str):   # 非整体引用时被渲染成字符串，试按 JSON 还原（对齐 aggregate.records）
            try:
                items = json.loads(items)
            except ValueError:
                items = None
        if not isinstance(items, list):
            got = "空" if items is None else ("对象（单条记录）" if isinstance(items, dict) else "文本")
            raise WorkflowNodeError(
                f"记录列表收到的是{got}，无法逐条处理。请填上游节点的「记录列表」整体引用，如 {{nodes.q_1.records}}"
            )
        max_items = int(ctx.config.get("max_items") or 50)
        items = items[: max(1, min(max_items, self.MAX_ITEMS))]
        state = (ctx.context.get("loops") or {}).get(ctx.node_id) or {}
        index = int(state.get("index") or 0)
        count = len(items)
        if index >= count:
            return NodeResult(output={"count": count, "done": True, "branch": "done"})
        return NodeResult(output={"item": items[index], "index": index, "count": count, "branch": "loop"})


@register
class DateCalcNode(NodeType):
    type = "date_calc"
    name = "日期计算"
    category = "logic"
    description = "以某个时间为基准加减天数/小时，输出新的日期（供筛选条件、通知模板引用）"
    config_schema = {
        "type": "object",
        "properties": {
            "base": {"type": "string", "format": "template", "title": "基准时间（可选）",
                     "description": "如 {now.today} 或 {nodes.q_1.records.0.date}；留空 = 当前时间"},
            "offset_days": {"type": "integer", "title": "加减天数（可负）", "default": 0},
            "offset_hours": {"type": "integer", "title": "加减小时（可负）", "default": 0},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {"date": {"type": "string"}, "datetime": {"type": "string"}},
    }

    def execute(self, ctx: NodeContext) -> NodeResult:
        from ...typemap import try_parse_datetime
        base_raw = (ctx.config.get("base") or "").strip()
        base = datetime.now()
        if base_raw:
            parsed = try_parse_datetime(base_raw)
            if not parsed:
                raise WorkflowNodeError(f"基准时间无法解析：{base_raw}（支持 2026-01-01 / 2026-01-01 09:00:00）")
            base = parsed
        days = int(ctx.config.get("offset_days") or 0)
        hours = int(ctx.config.get("offset_hours") or 0)
        out = base + timedelta(days=days, hours=hours)
        return NodeResult(output={
            "date": out.date().isoformat(),
            "datetime": out.isoformat(sep=" ", timespec="seconds"),
        })


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
