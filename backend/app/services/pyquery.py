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
    if data_type == "image":
        return v if isinstance(v, list) else None   # 图片字段存 file_id 列表，原样保留
    if data_type == "subform":
        return v if isinstance(v, list) else None   # 明细行存 JSON 数组，原样保留（不参与筛选语义）
    if data_type == "json":
        return v   # 智能表复合值（多选/人员/链接等）：原样保留 list/dict/str
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


# 日期筛选值的「日期模式」（筛选面板：具体日期 / 今天 / 本周 / 过去 7 天内…）：
# 条件值 = {"mode": ..., "date": "YYYY-MM-DD"（仅 exact）}，查询时按当天换算为闭区间 [lo, hi]，
# 再按运算符比较（等于=落在区间内，早于=早于区间首日，晚于=晚于区间末日…）。前端 format.js dateModeRange 同口径
DATE_MODES = {"exact", "today", "tomorrow", "yesterday", "thisWeek", "lastWeek", "thisMonth", "lastMonth",
              "past7", "next7", "past30", "next30"}


def date_mode_range(value: dict, today: date) -> tuple[date, date] | None:
    mode = value.get("mode")
    if mode == "exact":
        dt = try_parse_datetime(value.get("date"))
        return (dt.date(), dt.date()) if dt else None
    if mode == "today":
        return today, today
    if mode == "tomorrow":
        d = today + timedelta(days=1)
        return d, d
    if mode == "yesterday":
        d = today - timedelta(days=1)
        return d, d
    if mode in ("thisWeek", "lastWeek"):   # 周一 ~ 周日
        mon = today - timedelta(days=today.weekday()) - timedelta(days=7 if mode == "lastWeek" else 0)
        return mon, mon + timedelta(days=6)
    if mode in ("thisMonth", "lastMonth"):
        first = today.replace(day=1)
        if mode == "lastMonth":
            first = (first - timedelta(days=1)).replace(day=1)
        nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        return first, nxt - timedelta(days=1)
    if mode in ("past7", "past30"):        # 含今天
        return today - timedelta(days=(7 if mode == "past7" else 30) - 1), today
    if mode in ("next7", "next30"):        # 含今天
        return today, today + timedelta(days=(7 if mode == "next7" else 30) - 1)
    return None


def _date_mode_match(v, value: dict, op: str, today: date) -> bool:
    rng = date_mode_range(value, today)
    if rng is None or v is None:
        return False
    d = v.date() if isinstance(v, datetime) else v
    if not isinstance(d, date):
        return False
    lo, hi = rng
    if op == "eq":
        return lo <= d <= hi
    if op == "ne":
        return not (lo <= d <= hi)
    if op == "gt":
        return d > hi
    if op == "gte":
        return d >= lo
    if op == "lt":
        return d < lo
    return d <= hi   # lte


def _sys_int(x):
    """系统整型列（id/owner_id）的筛选值规范化：尽量转 int，转不了保留原值（永不命中）。"""
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return x


def match_rule(rec: dict, fields_by_name: dict, flt: dict) -> bool:
    """单条筛选规则，语义对齐 build_condition。rec 值须已 normalize_record。"""
    name = flt.get("field")
    op = flt.get("op")
    value = flt.get("value")
    if name not in fields_by_name and name not in ("id", "created_at", "updated_at", "owner_id"):
        raise HTTPException(400, f"未知筛选字段：{name}")
    v = rec.get(name)

    if op == "null":
        return v is None
    if op == "not_null":
        return v is not None
    # 空语义扩展（智能表视图 DSL isEmpty/isNotEmpty）：覆盖 None / 空串 / 空数组 / 空对象
    if op == "empty":
        return v is None or v == "" or v == [] or v == {}
    if op == "not_empty":
        return not (v is None or v == "" or v == [] or v == {})

    f = fields_by_name.get(name)

    # 集合语义：单元格是数组（多选/人员 json），或筛选值是列表（单选/多选/成员的选项多选编辑器）。
    # 缺这个分支时单选会拿 str(['opt_x']) 去做子串匹配，永远筛不中。
    if (isinstance(v, list) or isinstance(value, list)) and op in ("contains", "not_contains", "eq", "ne"):
        cell = {str(x) for x in v} if isinstance(v, list) else ({str(v)} if v is not None else set())
        want = value if isinstance(value, list) else [value]
        want_set = {str(x) for x in want}
        hit = bool(cell & want_set)
        if op == "contains":
            return hit            # 交集非空
        if op == "not_contains":
            return not hit
        if op == "eq":
            return len(want_set) == 1 and hit   # 单值归属
        return not (len(want_set) == 1 and hit)
    is_date = f is not None and f.data_type == "date"
    now = datetime.now()
    today = now.date()

    # 日期模式条件值（{"mode": ...}）：按当天换算区间后比较
    if isinstance(value, dict) and value.get("mode") in DATE_MODES and op in ("eq", "ne", "gt", "gte", "lt", "lte"):
        return _date_mode_match(v, value, op, today)

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
    if op == "not_contains":
        return v is not None and str(value).casefold() not in str(v).casefold()
    if op == "startswith":
        return v is not None and str(v).casefold().startswith(str(value).casefold())
    if op == "in":
        values = value if isinstance(value, list) else [s.strip() for s in str(value).split(",")]
        if v is None:
            return False
        # 系统整型列（id/owner_id）按 int 规范化，避免 varchar 化导致永不命中
        norm = [normalize_value(x, f.data_type) if f else _sys_int(x) for x in values]
        return v in norm

    # eq/ne/gt/gte/lt/lte：筛选值按字段类型规范化后比较（与 build_condition 的 coerce 对齐）
    target = normalize_value(value, f.data_type) if f else _sys_int(value)
    if f is None and name in ("id", "owner_id"):
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


def sort_records_multi(recs: list[dict], sorts: list[dict] | None,
                       fields_by_name: dict) -> list[dict]:
    """多级稳定排序：sorts=[{field, direction}]，数组序=优先级；direction 缺省 asc。
    None 视为最小值（与单列排序一致）。sorts 为空时回落 id desc。"""
    if not sorts:
        return sort_records(recs, None, None, fields_by_name)
    sortable = set(fields_by_name) | {"id", "created_at", "updated_at"}
    keys = [((s.get("fieldId") or s.get("field")), s.get("direction", "asc"))
            for s in sorts]
    keys = [(f, d) for f, d in keys if f in sortable]
    if not keys:
        return sort_records(recs, None, None, fields_by_name)

    def key_for(name):
        def k(rec):
            v = rec.get(name)
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
            if isinstance(v, list):   # 多选等：按选项序排序需 options 上下文，V1 取首个元素
                return (0, str(v[0]) if v else "")
            return (0, str(v))
        return k

    out = list(recs)
    for name, direction in reversed(keys):   # 稳定排序：从最低优先级键开始排
        out.sort(key=key_for(name), reverse=(direction == "desc"))
    return out
