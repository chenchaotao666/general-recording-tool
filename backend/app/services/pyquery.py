"""Python 版记录筛选/排序：rule dict 与 SQL 路径（dyn_engine.build_condition）共同的语义源头。

对齐要点（与 build_condition 的差异即 bug）：
- SQL 三值逻辑：普通比较（含 ne）遇 NULL 一律排除，只有 null/not_null 判断 None；
- contains/startswith：SQLite LIKE / MySQL 默认校对集对 ASCII 大小写不敏感，两端 casefold 后比较；
- 相对日期操作符（today/past_days/older_than_days/within_days）的边界逐行照搬 build_condition；
- 排序：ASC 时 None 排最前（SQLite/MySQL 一致），按字段类型规范化后再比。
- LIKE 通配符（%/_）在 SQL 路径未转义、Python 端按纯子串处理，属已知边缘差异，不做复刻。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException

from .typemap import try_parse_datetime


def normalize_value(v, data_type: str):
    """存储值（JSON 标量）按字段类型还原为 date/datetime/int/float/bool/str/None。"""
    if v is None:
        return None
    if data_type == "date":
        dt = try_parse_datetime(v)
        return dt.date() if dt else None
    if data_type == "datetime":
        return try_parse_datetime(v)
    if data_type == "int":
        if isinstance(v, bool):
            return None
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None
    if data_type == "decimal":
        if isinstance(v, bool):
            return None
        try:
            return float(Decimal(str(v)))
        except (TypeError, ValueError, InvalidOperation):
            return None
    if data_type == "bool":
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in {"是", "true", "1", "yes", "y", "对", "√"}
    return str(v)


def normalize_record(rec: dict, fields_by_name: dict) -> dict:
    """把 records.data 的存储值规范化（含 id/created_at/updated_at 系统字段）。"""
    out = dict(rec)
    for name, f in fields_by_name.items():
        if name in out:
            out[name] = normalize_value(out[name], f.data_type)
    return out


def _cmp_ok(a, b, op: str) -> bool:
    if a is None:
        return False  # SQL 三值逻辑：NULL 参与比较即排除
    try:
        if op == "eq":
            return a == b
        if op == "ne":
            return a != b
        if op == "gt":
            return a > b
        if op == "gte":
            return a >= b
        if op == "lt":
            return a < b
        return a <= b  # lte
    except TypeError:
        return False


def match_rule(rec: dict, fields_by_name: dict, flt: dict) -> bool:
    """单条筛选规则，语义对齐 build_condition。rec 值须已 normalize_record。"""
    name = flt.get("field")
    op = flt.get("op")
    value = flt.get("value")
    if name not in fields_by_name and name not in ("id", "created_at", "updated_at"):
        raise HTTPException(400, f"未知筛选字段：{name}")
    v = rec.get(name)

    if op == "null":
        return v is None
    if op == "not_null":
        return v is not None

    f = fields_by_name.get(name)
    is_date = f is not None and f.data_type == "date"
    now = datetime.now()
    today = now.date()

    if op == "today":
        if is_date:
            return v == today
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return isinstance(v, datetime) and day_start <= v < day_start + timedelta(days=1)

    if op in ("older_than_days", "within_days", "past_days"):
        try:
            days = int(value)
        except (TypeError, ValueError):
            raise HTTPException(400, "天数必须是整数")
        if op == "older_than_days":
            threshold = now - timedelta(days=days)
            return _cmp_ok(v, threshold.date() if is_date else threshold, "lt")
        if op == "within_days":
            lo = today if is_date else now
            hi = now + timedelta(days=days)
            if v is None:
                return False
            try:
                return v >= lo and v <= (hi.date() if is_date else hi)
            except TypeError:
                return False
        # past_days：过去 N 天（含今天），N=1 即当天
        start_date = today - timedelta(days=max(days - 1, 0))
        if is_date:
            return v is not None and start_date <= v <= today
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(today + timedelta(days=1), datetime.min.time())
        return isinstance(v, datetime) and start_dt <= v < end_dt

    if op == "contains":
        return v is not None and str(value).casefold() in str(v).casefold()
    if op == "startswith":
        return v is not None and str(v).casefold().startswith(str(value).casefold())
    if op == "in":
        values = value if isinstance(value, list) else [s.strip() for s in str(value).split(",")]
        if v is None:
            return False
        norm = [normalize_value(x, f.data_type if f else "varchar") for x in values]
        return v in norm

    # eq/ne/gt/gte/lt/lte：筛选值按字段类型规范化后比较（与 build_condition 的 coerce 对齐）
    target = normalize_value(value, f.data_type if f else "varchar")
    if f is None and name in ("id",):
        try:
            target = int(value)
        except (TypeError, ValueError):
            raise HTTPException(400, "筛选值无效（id）：必须是整数")
    return _cmp_ok(v, target, op)


def match_filters(rec: dict, fields_by_name: dict, filters: dict | None) -> bool:
    """{logic, rules} 组合，对齐 combine_conditions：AND 全中 / OR 中一个；无规则恒真。"""
    rules = (filters or {}).get("rules") or []
    if not rules:
        return True
    results = (match_rule(rec, fields_by_name, r) for r in rules)
    return any(results) if (filters or {}).get("logic") == "OR" else all(results)


def sort_records(recs: list[dict], sort_by: str | None, sort_order: str | None,
                 fields_by_name: dict) -> list[dict]:
    """默认 id desc；sort_by 须在字段或系统字段内，否则回落 id desc（对齐 list_records）。
    None 视为最小值：ASC 时 None 最前、DESC 时 None 最后（与 SQLite/MySQL 的 NULL 排序一致）。"""
    sortable = set(fields_by_name) | {"id", "created_at", "updated_at"}
    key_name = sort_by if sort_by in sortable else "id"
    reverse = sort_order != "asc"

    def key(rec):
        v = rec.get(key_name)
        if v is None:
            return (-1, 0)
        if isinstance(v, bool):
            return (0, int(v))
        if isinstance(v, (int, float, Decimal)):
            return (0, float(v))
        if isinstance(v, datetime):
            return (0, v.timestamp())
        if isinstance(v, date):
            return (0, float(v.toordinal()))
        return (0, str(v))

    return sorted(recs, key=key, reverse=reverse)
