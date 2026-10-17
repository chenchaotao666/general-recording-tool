"""智能表条件求值（单行）：权限行条件（§13.3）与自动化过滤器（§11.2）共用。

条件 = 视图筛选 DSL 同构：{fieldId, operator, value}；fieldId 为 field_name。
扩展：value == "$viewer"（或数组含 "$viewer"）= 查看者本人，用于「创建人 包含查看者本人」。
系统字段（创建人/最后编辑人/创建时间/最后编辑时间）取记录系统列，normalized 记录里业务键为空需注入。
"""
from __future__ import annotations

from fastapi import HTTPException

from .field_registry import FIELD_TYPES
from .pyquery import match_rule
from .view_config import OP_MAP

VIEWER = "$viewer"
_MEMBER_TYPES = {"member", "createdBy", "lastModifiedBy"}
_NEG_OPS = {"neq", "ne", "notContains", "not_contains"}


def with_system_values(rec: dict, fields: list) -> dict:
    """normalized 记录 → 注入系统字段值的浅拷贝（创建人=owner_id 等）。"""
    out = dict(rec)
    for f in fields:
        sys_key = FIELD_TYPES.get(f.field_type or "", {}).get("sys_key")
        if sys_key:
            out[f.field_name] = rec.get(sys_key)
    return out


def _ids_of(v) -> set[str]:
    if v is None or v == "":
        return set()
    if isinstance(v, (list, tuple, set)):
        return {str(x.get("id") if isinstance(x, dict) else x) for x in v if x not in (None, "")}
    return {str(v)}


def _has_viewer(value) -> bool:
    if value == VIEWER:
        return True
    return isinstance(value, list) and VIEWER in value


def match_condition(rec: dict, fields_by_name: dict, cond: dict, viewer_id: int | None = None) -> bool:
    fn, op, value = cond.get("fieldId"), cond.get("operator"), cond.get("value")
    if fn not in fields_by_name:
        return False   # 引用已删除字段的条件按不命中处理（宁严勿松）
    member_like = (getattr(fields_by_name[fn], "field_type", None) or "") in _MEMBER_TYPES
    if _has_viewer(value) or (member_like and isinstance(value, list) and op not in ("isEmpty", "isNotEmpty")):
        # 人员集合语义；「查看者本人」可与具体成员并列：任一命中即算包含
        wanted = {str(viewer_id) if x == VIEWER else str(x)
                  for x in (value if isinstance(value, list) else [value]) if x != VIEWER or viewer_id is not None}
        have = _ids_of(rec.get(fn))
        if op in ("eq", "neq", "ne"):
            hit = bool(have) and have == wanted
        else:
            hit = bool(wanted & have)
        return not hit if op in _NEG_OPS else hit
    mop = OP_MAP.get(op)
    if not mop:
        raise HTTPException(400, f"不支持的条件运算符：{op}")
    rule = {"field": fn, "op": mop}
    if mop not in ("empty", "not_empty"):
        rule["value"] = value
    try:
        return match_rule(rec, fields_by_name, rule)
    except HTTPException:
        return False


def match_conditions(rec: dict, fields: list, conditions: list | None, match: str = "all",
                     viewer_id: int | None = None, prepared: bool = False) -> bool:
    """多条件组合：match=all（AND）/ any（OR）；无条件恒真。prepared=True 表示 rec 已注入系统字段。"""
    conds = [c for c in (conditions or []) if c.get("fieldId")]
    if not conds:
        return True
    by_name = {f.field_name: f for f in fields}
    r = rec if prepared else with_system_values(rec, fields)
    results = (match_condition(r, by_name, c, viewer_id) for c in conds)
    return any(results) if match in ("any", "or") else all(results)
