"""查找引用（lookup）读时计算（设计文档 §8.2）：按条件匹配源表记录并引用/聚合其字段值。

MVP 口径：读时计算不落库（≤1 万行约定下，源表记录一次载入内存，逐行匹配）。
"""
from __future__ import annotations

from . import json_store
from .field_registry import LOOKUP_AGGS
from .meta_service import get_meta_fields


def _match(row: dict, src: dict, conditions: list, logic: str) -> bool:
    """条件行：{sourceFieldId, op, rightFieldId|rightValue}。op 对齐 pyquery 语义（eq/contains/gt…）。"""
    def one(c: dict) -> bool:
        sf = c.get("sourceFieldId")
        sv = src.get(sf)
        rv = row.get(c.get("rightFieldId")) if c.get("rightFieldId") else c.get("rightValue")
        op = c.get("op", "eq")
        if sv is None or rv is None:
            return False
        if isinstance(sv, list):   # 源为多选/人员：交集非空
            want = rv if isinstance(rv, list) else [rv]
            return bool({str(x) for x in sv} & {str(x) for x in want})
        try:
            if op == "eq":
                return sv == rv or str(sv) == str(rv)
            if op == "ne":
                return not (sv == rv or str(sv) == str(rv))
            if op == "contains":
                return str(rv).casefold() in str(sv).casefold()
            if op == "gt":
                return float(sv) > float(rv)
            if op == "gte":
                return float(sv) >= float(rv)
            if op == "lt":
                return float(sv) < float(rv)
            if op == "lte":
                return float(sv) <= float(rv)
        except (TypeError, ValueError):
            return False
        return False

    results = [one(c) for c in conditions or []]
    if not results:
        return True   # 无条件 = 全表匹配
    return any(results) if logic == "or" else all(results)


def compute_lookup(db, field, rows: list[dict], src_cache: dict) -> dict[int, object]:
    """对一批行计算某 lookup 字段的值。返回 {row_id: value}。src_cache 跨字段复用源表记录。"""
    cfg = field.options or {}
    src_table_id = cfg.get("sourceTableId")
    src_field = cfg.get("sourceFieldId")
    agg = cfg.get("aggregation", "raw")
    if not src_table_id or not src_field or agg not in LOOKUP_AGGS:
        return {}
    if src_table_id not in src_cache:
        src_fields = get_meta_fields(db, src_table_id)
        src_cache[src_table_id] = json_store.all_dicts(db, src_table_id, src_fields, normalized=True)
    src_rows = src_cache[src_table_id]
    logic = cfg.get("conditionLogic", "and")
    conditions = cfg.get("conditions") or []

    out = {}
    for row in rows:
        matched = [s.get(src_field) for s in src_rows if _match(row, s, conditions, logic)]
        matched = [v for v in matched if v is not None and v != ""]
        rid = row.get("id")
        if agg == "raw":
            out[rid] = matched or None
        elif agg == "rawDistinct":
            seen, uniq = set(), []
            for v in matched:
                k = str(v)
                if k not in seen:
                    seen.add(k)
                    uniq.append(v)
            out[rid] = uniq or None
        elif agg == "count":
            out[rid] = len(matched)
        elif agg == "countDistinct":
            out[rid] = len({str(v) for v in matched})
        else:
            nums = [v for v in matched if isinstance(v, (int, float)) and not isinstance(v, bool)]
            if not nums:
                out[rid] = None
            elif agg == "sum":
                out[rid] = sum(nums)
            elif agg == "avg":
                out[rid] = sum(nums) / len(nums)
            elif agg == "max":
                out[rid] = max(nums)
            elif agg == "min":
                out[rid] = min(nums)
    return out
