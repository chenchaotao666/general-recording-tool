"""智能表视图配置：config 白名单校验、个人覆盖合并、视图 DSL → dyn_engine 筛选协议适配、聚合计算。

视图 config 中字段一律以 field_name 标识（即 records.data 的键，稳定且可读）。
设计文档：§2.3 视图配置、§5.1 筛选 DSL、§5.6 配置总表。
"""
from __future__ import annotations

import json
from datetime import date, datetime

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

# 通用统计（所有字段类型可用，统计行按列配置）：行数/填写计数/去重/占比
GENERIC_AGGS = {"countRecords", "empty", "distinct", "filledRatio", "emptyRatio", "distinctRatio"}
AGGREGATIONS = {"count", "sum", "avg", "max", "min"} | GENERIC_AGGS

# V1 视图 config 允许的键（白名单，防注入脏数据）
CONFIG_KEYS = {"filters", "sorts", "groups", "fillRules", "rowHeight", "fieldVisibility",
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
    if filters.get("conjunction", "and") not in ("and", "or"):
        raise HTTPException(400, "筛选组合方式必须是 and/or")
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

    groups = cfg.get("groups") or []
    if not isinstance(groups, list) or len(groups) > 3:
        raise HTTPException(400, "分组层级格式无效（最多 3 级）")
    for g in groups:
        if g.get("fieldId") not in names:
            raise HTTPException(400, f"分组引用了不存在的字段：{g.get('fieldId')}")
        if g.get("direction", "asc") not in ("asc", "desc"):
            raise HTTPException(400, "分组方向必须是 asc/desc")

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
        if agg in GENERIC_AGGS:
            continue   # 通用统计对所有字段类型开放
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


def _is_empty(v) -> bool:
    return v is None or v == "" or v == []


def _distinct_key(v) -> str:
    """去重计数的值规范化：list/dict 结构按内容哈希，标量直接 JSON 化。"""
    return json.dumps(v, sort_keys=True, default=str, ensure_ascii=False)


def compute_stat(recs: list[dict], fn: str, agg: str):
    """单个字段在筛选后全集上的一种统计值。占比返回 0~1 小数（前端格式化 %）。"""
    total = len(recs)
    vals = [r.get(fn) for r in recs]
    filled = sum(1 for v in vals if not _is_empty(v))
    if agg == "countRecords":
        return total
    if agg == "count":
        return filled
    if agg == "empty":
        return total - filled
    if agg in ("distinct", "distinctRatio"):
        uniq = len({_distinct_key(v) for v in vals if not _is_empty(v)})
        return uniq if agg == "distinct" else (round(uniq / total, 6) if total else None)
    if agg in ("filledRatio", "emptyRatio"):
        if not total:
            return None
        return round((filled if agg == "filledRatio" else total - filled) / total, 6)
    nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if agg in ("max", "min") and not nums:
        # 日期/日期时间等可比非标量：按 ISO 文本序取最值后序列化输出
        pool = [v for v in vals if isinstance(v, (datetime, date)) or (isinstance(v, str) and v)]
        if not pool:
            return None
        best = (max if agg == "max" else min)(pool, key=lambda v: v.isoformat() if hasattr(v, "isoformat") else v)
        if isinstance(best, datetime):
            return best.isoformat(sep=" ")
        if isinstance(best, date):
            return best.isoformat()
        return best
    if not nums:
        return None
    if agg == "sum":
        return sum(nums)
    if agg == "avg":
        return sum(nums) / len(nums)
    if agg == "max":
        return max(nums)
    if agg == "min":
        return min(nums)
    return None


def field_stat_kinds(field) -> list[str]:
    """某字段可用的全部统计方式：注册表数值聚合 + 已填写(count) + 通用统计。"""
    reg = FIELD_TYPES.get(getattr(field, "field_type", None) or "")
    extras = [a for a in (reg["aggregations"] if reg else []) if a != "count"]
    return extras + ["count"] + sorted(GENERIC_AGGS)


def compute_aggregations(recs: list[dict], aggs_cfg: dict | None, fields: list) -> dict:
    """对筛选后的规范化全集计算聚合（json 模式内存求值）。返回 {field_name: value}。"""
    out = {}
    if not aggs_cfg:
        return out
    for fn, agg in aggs_cfg.items():
        out[fn] = compute_stat(recs, fn, agg)
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
        if any(g.get("fieldId") == field_name for g in cfg.get("groups") or []):
            usages.append("分组")
        if field_name in (cfg.get("aggregations") or {}):
            usages.append("汇总聚合")
        if cfg.get("frozenFieldId") == field_name:
            usages.append("冻结列")
        if usages:
            deps.append({"viewId": v.id, "viewName": v.name, "usages": usages})
    return deps


# ---------- 分组（设计文档 §5.2）：多级分桶 + 组内排序 + 自底向上聚合 ----------

def _group_sort_key(v, field):
    """分组键排序值：单选/多选按选项定义序，其余按值；空值排最前。"""
    if v is None or v == "" or v == []:
        return (-1, 0)
    opts = ((field.options or {}).get("options") or []) if field else []
    if opts:
        order = {str(o.get("id")): i for i, o in enumerate(opts)}
        if isinstance(v, list):
            return (0, min((order.get(str(x), 999) for x in v), default=999))
        return (0, order.get(str(v), 999))
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (0, float(v))
    if isinstance(v, list):
        return (0, str(v[0]) if v else "")
    return (0, str(v))


def flatten_grouped(recs: list[dict], levels: list[dict], fields_by_name: dict,
                    sorts: list[dict] | None, aggs_cfg: dict | None) -> list[dict]:
    """筛选后的规范化记录 → 扁平行序列：[{__rowType:'group', ...}, ...数据行]。
    分组桶按 direction 排序；组内行按 sorts 多级排序；每组计算聚合（记录数+数值列）。"""
    from .pyquery import sort_records_multi

    def build(rows: list[dict], depth: int, path: list) -> list[dict]:
        if depth >= len(levels):
            return sort_records_multi(rows, sorts, fields_by_name)
        lv = levels[depth]
        fn = lv["fieldId"]
        field = fields_by_name.get(fn)
        buckets: dict[str, list] = {}
        keys: dict[str, object] = {}
        for r in rows:
            v = r.get(fn)
            k = "__empty__" if v is None or v == "" or v == [] else (
                ",".join(map(str, v)) if isinstance(v, list) else str(v))
            buckets.setdefault(k, []).append(r)
            keys[k] = v
        ordered = sorted(buckets.keys(),
                         key=lambda k: _group_sort_key(keys[k], field),
                         reverse=(lv.get("direction") == "desc"))
        out = []
        for k in ordered:
            sub = buckets[k]
            aggs = compute_aggregations(sub, aggs_cfg, list(fields_by_name.values()))
            out.append({
                "__rowType": "group", "key": "|".join(path + [k]), "depth": depth,
                "fieldId": fn, "value": keys[k], "count": len(sub), "aggs": aggs,
            })
            out.extend(build(sub, depth + 1, path + [k]))
        return out

    return build(recs, 0, [])
