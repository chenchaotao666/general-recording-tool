"""智能表视图配置：config 白名单校验、个人覆盖合并、视图 DSL → dyn_engine 筛选协议适配、聚合计算。

视图 config 中字段一律以 field_name 标识（即 records.data 的键，稳定且可读）。
设计文档：§2.3 视图配置、§5.1 筛选 DSL、§5.6 配置总表。
"""
from __future__ import annotations

from fastapi import HTTPException

from .field_registry import FIELD_TYPES, ROW_HEIGHTS

# 视图 DSL → dyn_engine/pyquery 操作符映射（between 由前端拆为 gte+lte 两条）
OP_MAP = {
    "eq": "eq", "ne": "ne", "neq": "ne",
    "contains": "contains", "notContains": "not_contains", "not_contains": "not_contains",
    "gt": "gt", "gte": "gte", "lt": "lt", "lte": "lte",
    "isEmpty": "empty", "isNotEmpty": "not_empty", "empty": "empty", "not_empty": "not_empty",
    "in": "in", "null": "null", "notNull": "not_null",
    "today": "today", "pastDays": "past_days", "withinDays": "within_days",
}

AGGREGATIONS = {"count", "sum", "avg", "max", "min"}

# V1 视图 config 允许的键（白名单，防注入脏数据）
CONFIG_KEYS = {"filters", "sorts", "fillRules", "rowHeight", "fieldVisibility",
               "fieldOrder", "colWidths", "frozenFieldId", "aggregations", "autoSort"}

# 填色/筛选共用的无值运算符
_NO_VALUE_OPS = {"isEmpty", "isNotEmpty", "empty", "not_empty", "today"}


def _field_filter_ops(field) -> list[str]:
    reg = FIELD_TYPES.get(getattr(field, "field_type", None) or "")
    return reg["filter_ops"] if reg else list(OP_MAP)


def validate_view_config(config: dict | None, fields: list) -> dict:
    """校验并清洗视图 config：白名单键 + fieldId（实为 field_name）存在性 + 运算符合法性。"""
    cfg = {k: v for k, v in (config or {}).items() if k in CONFIG_KEYS}
    names = {f.field_name for f in fields}
    by_name = {f.field_name: f for f in fields}

    filters = cfg.get("filters") or {}
    conds = filters.get("conditions") or []
    if not isinstance(conds, list) or len(conds) > 20:
        raise HTTPException(400, "筛选条件格式无效（最多 20 条）")
    for c in conds:
        fn, op = c.get("fieldId"), c.get("operator")
        if fn not in names:
            raise HTTPException(400, f"筛选条件引用了不存在的字段：{fn}")
        if op not in OP_MAP or op not in _field_filter_ops(by_name[fn]):
            raise HTTPException(400, f"字段「{by_name[fn].label}」不支持运算符：{op}")
        if op not in _NO_VALUE_OPS and "value" not in c:
            raise HTTPException(400, "筛选条件缺少值")

    sorts = cfg.get("sorts") or []
    if not isinstance(sorts, list) or len(sorts) > 5:
        raise HTTPException(400, "排序规则格式无效（最多 5 级）")
    for s in sorts:
        if s.get("fieldId") not in names:
            raise HTTPException(400, f"排序引用了不存在的字段：{s.get('fieldId')}")
        if s.get("direction", "asc") not in ("asc", "desc"):
            raise HTTPException(400, "排序方向必须是 asc/desc")

    for rule in cfg.get("fillRules") or []:
        if rule.get("fieldId") not in names:
            raise HTTPException(400, f"填色规则引用了不存在的字段：{rule.get('fieldId')}")
        if not rule.get("color"):
            raise HTTPException(400, "填色规则缺少颜色")

    rh = cfg.get("rowHeight", "default")
    if isinstance(rh, str) and rh not in ROW_HEIGHTS:
        raise HTTPException(400, f"行高档位不支持：{rh}")

    if cfg.get("frozenFieldId") is not None and cfg["frozenFieldId"] not in names:
        raise HTTPException(400, f"冻结列引用了不存在的字段：{cfg['frozenFieldId']}")

    aggs = cfg.get("aggregations") or {}
    for fn, agg in aggs.items():
        if fn not in names:
            raise HTTPException(400, f"聚合配置引用了不存在的字段：{fn}")
        if agg not in AGGREGATIONS:
            raise HTTPException(400, f"不支持的聚合方式：{agg}")
        reg = FIELD_TYPES.get(getattr(by_name[fn], "field_type", None) or "")
        if reg and agg not in reg["aggregations"]:
            raise HTTPException(400, f"字段「{by_name[fn].label}」不支持聚合方式：{agg}")
    return cfg


def merge_pref(view_config: dict, pref_config: dict | None) -> dict:
    """个人覆盖合并语义：filters 整块替换，其余键用视图的。"""
    merged = dict(view_config or {})
    if pref_config and isinstance(pref_config.get("filters"), dict):
        merged["filters"] = pref_config["filters"]
        merged["filtersScope"] = "personal"
    return merged


def conditions_to_rules(filters_cfg: dict | None) -> list[dict]:
    """视图筛选 DSL → dyn_engine/pyquery 规则数组（顶层 AND）。"""
    conds = (filters_cfg or {}).get("conditions") or []
    rules = []
    for c in conds:
        op = OP_MAP.get(c.get("operator"))
        if not op:
            raise HTTPException(400, f"不支持的筛选运算符：{c.get('operator')}")
        rule = {"field": c["fieldId"], "op": op}
        if op not in ("empty", "not_empty"):
            rule["value"] = c.get("value")
        rules.append(rule)
    return rules


def compute_aggregations(recs: list[dict], aggs_cfg: dict | None, fields: list) -> dict:
    """对筛选后的规范化全集计算聚合（json 模式内存求值）。返回 {field_name: value}。"""
    out = {}
    if not aggs_cfg:
        return out
    for fn, agg in aggs_cfg.items():
        vals = [r.get(fn) for r in recs]
        if agg == "count":
            out[fn] = sum(1 for v in vals if v is not None and v != "" and v != [])
            continue
        nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if not nums:
            out[fn] = None
        elif agg == "sum":
            out[fn] = sum(nums)
        elif agg == "avg":
            out[fn] = sum(nums) / len(nums)
        elif agg == "max":
            out[fn] = max(nums)
        elif agg == "min":
            out[fn] = min(nums)
    return out


def scan_field_deps(views: list, field_name: str) -> list[dict]:
    """字段删除依赖检查：扫描各视图 config 中对该字段的引用。"""
    deps = []
    for v in views:
        cfg = v.config or {}
        usages = []
        if any(c.get("fieldId") == field_name for c in (cfg.get("filters") or {}).get("conditions") or []):
            usages.append("筛选")
        if any(s.get("fieldId") == field_name for s in cfg.get("sorts") or []):
            usages.append("排序")
        if any(r.get("fieldId") == field_name for r in cfg.get("fillRules") or []):
            usages.append("填色")
        if field_name in (cfg.get("aggregations") or {}):
            usages.append("汇总聚合")
        if cfg.get("frozenFieldId") == field_name:
            usages.append("冻结列")
        if usages:
            deps.append({"viewId": v.id, "viewName": v.name, "usages": usages})
    return deps
