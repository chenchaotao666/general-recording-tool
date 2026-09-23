"""报表引擎：时间口径解析、模板校验、区块求值（统计卡片/图表/明细表/文本）、定时推送。"""
from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import MetaField, ReportRunLog, ReportTemplate
from . import dyn_engine
from .actions import get_setting, send_smtp_html

BLOCK_TYPES = {"stat", "chart", "table", "text"}
AGG_TYPES = {"count", "count_distinct", "sum", "avg", "max", "min", "ratio"}
CHART_AGG_TYPES = AGG_TYPES - {"ratio"}   # ratio（占比）仅统计卡：满足区块筛选数 / 口径内总数
NUMERIC_TYPES = {"int", "decimal"}
CHART_TYPES = {"bar", "line", "pie"}
GROUP_KINDS = {"field", "day", "week", "month"}
RANGE_MODES = {"today", "yesterday", "past_7d", "past_30d", "this_week", "last_week",
               "this_month", "last_month", "this_quarter", "this_year", "custom"}
SYSTEM_FIELDS = {"id", "created_at", "updated_at"}
TABLE_LIMIT_MAX = 500
CHART_TOP_N_DEFAULT = {"pie": 8, "bar": 30, "line": 30}
WEBHOOK_TYPES = {"wecom": "企业微信", "dingtalk": "钉钉", "custom": "自定义"}


class ReportError(Exception):
    pass


# ---------- 时间口径 ----------

def resolve_time_range(cfg: dict, now: datetime | None = None) -> tuple[datetime, datetime, str]:
    """把 range_json 解析为 [start, end) 区间和显示标签。this_* 口径 end 为当前时刻。"""
    now = now or datetime.now()
    mode = (cfg or {}).get("mode") or "this_week"
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if mode == "today":
        return today, now, f"今天（{today:%Y-%m-%d}）"
    if mode == "yesterday":
        y = today - timedelta(days=1)
        return y, today, f"昨天（{y:%Y-%m-%d}）"
    if mode == "past_7d":
        start = today - timedelta(days=6)
        return start, now, f"近7天（{start:%Y-%m-%d} ~ {now:%Y-%m-%d}）"
    if mode == "past_30d":
        start = today - timedelta(days=29)
        return start, now, f"近30天（{start:%Y-%m-%d} ~ {now:%Y-%m-%d}）"
    if mode == "this_quarter":
        start = today.replace(month=(now.month - 1) // 3 * 3 + 1, day=1)
        return start, now, f"本季度（{start:%Y-%m-%d} ~ {now:%Y-%m-%d}）"
    if mode == "this_year":
        start = today.replace(month=1, day=1)
        return start, now, f"今年（{start:%Y-%m-%d} ~ {now:%Y-%m-%d}）"
    if mode == "this_week":
        start = today - timedelta(days=now.weekday())
        return start, now, f"本周（{start:%Y-%m-%d} ~ {now:%Y-%m-%d}）"
    if mode == "last_week":
        this_monday = today - timedelta(days=now.weekday())
        start = this_monday - timedelta(days=7)
        end_display = this_monday - timedelta(days=1)
        return start, this_monday, f"上周（{start:%Y-%m-%d} ~ {end_display:%Y-%m-%d}）"
    if mode == "this_month":
        start = today.replace(day=1)
        return start, now, f"本月（{start:%Y-%m-%d} ~ {now:%Y-%m-%d}）"
    if mode == "last_month":
        this_first = today.replace(day=1)
        start = (this_first - timedelta(days=1)).replace(day=1)
        end_display = this_first - timedelta(days=1)
        return start, this_first, f"上月（{start:%Y-%m-%d} ~ {end_display:%Y-%m-%d}）"
    if mode == "custom":
        try:
            start = datetime.strptime(cfg.get("start") or "", "%Y-%m-%d")
            end = datetime.strptime(cfg.get("end") or "", "%Y-%m-%d") + timedelta(days=1)
        except (TypeError, ValueError):
            raise ReportError("自定义口径需要合法的 start/end 日期（YYYY-MM-DD）")
        if end <= start:
            raise ReportError("自定义口径结束日期不能早于开始日期")
        return start, end, f"{start:%Y-%m-%d} ~ {(end - timedelta(days=1)):%Y-%m-%d}"
    raise ReportError(f"不支持的时间口径：{mode}")


def _time_conds(table, fields_by_name: dict, date_field: str, start: datetime, end: datetime):
    """时间区间条件；date 类型字段与 date 比较。"""
    col = table.c[date_field]
    f = fields_by_name.get(date_field)
    if f is not None and f.data_type == "date":
        return [col >= start.date(), col < end.date()]
    return [col >= start, col < end]


# ---------- 模板校验 ----------

def _validate_filters(fields_by_name: dict, filters: dict) -> None:
    for r in (filters or {}).get("rules") or []:
        name = r.get("field")
        if name not in fields_by_name and name not in SYSTEM_FIELDS:
            raise HTTPException(400, f"筛选字段不存在：{name}")
        if r.get("op") not in dyn_engine.FILTER_OPS:
            raise HTTPException(400, f"不支持的筛选操作符：{r.get('op')}")
        if not dyn_engine.rule_value_ok(fields_by_name.get(name), r.get("op"), r.get("value")):
            label = fields_by_name[name].label if name in fields_by_name else name
            raise HTTPException(400, f"筛选值无效（{label}）：无法按字段类型转换")


def _check_numeric_field(fields_by_name: dict, agg: str, field: str | None) -> None:
    if agg in ("count", "ratio"):
        return
    if agg == "count_distinct":
        # 去重计数可用任意类型字段（含系统字段）
        if field not in fields_by_name and field not in SYSTEM_FIELDS:
            raise HTTPException(400, "去重计数需要选择统计字段")
        return
    f = fields_by_name.get(field or "")
    if f is None or f.data_type not in NUMERIC_TYPES:
        raise HTTPException(400, f"聚合方式 {agg} 需要选择数值类型字段")


def validate_template(db: Session, payload) -> None:
    from .meta_service import get_meta_fields, get_meta_table

    if not get_meta_table(db, payload.table_id):
        raise HTTPException(400, "目标数据表不存在")

    rng = payload.range or {}
    mode = rng.get("mode") or "this_week"
    if mode not in RANGE_MODES:
        raise HTTPException(400, f"不支持的时间口径：{mode}")
    if mode == "custom" and (rng.get("start") or rng.get("end")):
        resolve_time_range(rng)  # 校验日期格式（完整校验允许留空，运行时再要求）

    fields = get_meta_fields(db, payload.table_id)
    fields_by_name = {f.field_name: f for f in fields}
    date_field = rng.get("date_field") or "created_at"
    df = fields_by_name.get(date_field)
    if date_field not in ("created_at", "updated_at") and (df is None or df.data_type not in ("date", "datetime")):
        raise HTTPException(400, "统计日期字段必须是日期/日期时间类型")

    if not payload.blocks:
        raise HTTPException(400, "至少需要一个报表区块")
    ids = set()
    for b in payload.blocks:
        t = b.get("type")
        if t not in BLOCK_TYPES:
            raise HTTPException(400, f"未知区块类型：{t}")
        bid = b.get("id")
        if not bid or bid in ids:
            raise HTTPException(400, "区块 id 缺失或重复")
        ids.add(bid)
        _validate_filters(fields_by_name, b.get("filters"))
        if t == "stat":
            if b.get("agg") not in AGG_TYPES:
                raise HTTPException(400, f"不支持的聚合方式：{b.get('agg')}")
            _check_numeric_field(fields_by_name, b["agg"], b.get("field"))
        elif t == "chart":
            if b.get("chart_type") not in CHART_TYPES:
                raise HTTPException(400, f"不支持的图表类型：{b.get('chart_type')}")
            if (b.get("agg") or "count") not in CHART_AGG_TYPES:
                raise HTTPException(400, f"图表不支持的聚合方式：{b.get('agg')}")
            _check_numeric_field(fields_by_name, b.get("agg") or "count", b.get("field"))
            group = b.get("group") or {}
            gkind, gfield = group.get("kind") or "field", group.get("field")
            if gkind not in GROUP_KINDS:
                raise HTTPException(400, f"不支持的分组方式：{gkind}")
            gf = fields_by_name.get(gfield or "")
            if gfield not in ("created_at", "updated_at") and gf is None:
                raise HTTPException(400, f"分组字段不存在：{gfield}")
            if gkind in ("day", "week", "month"):
                is_date_type = (gf is not None and gf.data_type in ("date", "datetime")) or gfield in ("created_at", "updated_at")
                if not is_date_type:
                    raise HTTPException(400, "按日/周/月分组需要选择日期类型字段")
        elif t == "table":
            cols = b.get("columns") or []
            if not cols:
                raise HTTPException(400, "明细表区块至少需要一列")
            for c in cols:
                if c not in fields_by_name and c not in SYSTEM_FIELDS:
                    raise HTTPException(400, f"明细列不存在：{c}")

    # 查看端可筛选字段必须是表内字段
    for fn in getattr(payload, "filter_fields", None) or []:
        if fn not in fields_by_name:
            raise HTTPException(400, f"查看端筛选字段不存在：{fn}")

    # 定时推送配置校验
    s = payload.schedule or {}
    if s.get("type"):
        from . import scheduler as sched
        if sched.trigger_of(s) is None:
            raise HTTPException(400, "执行周期配置无效")
    for wh in (payload.push or {}).get("webhooks") or []:
        wtype = wh.get("type") or "wecom"
        if wtype not in WEBHOOK_TYPES:
            raise HTTPException(400, f"不支持的 Webhook 类型：{wtype}")
        if not (wh.get("url") or "").strip().startswith(("http://", "https://")):
            raise HTTPException(400, "Webhook 地址必须是 http(s) URL")


# ---------- 区块求值 ----------

def _agg_expr(table, agg: str, field: str | None):
    if agg == "count":
        return func.count()
    col = table.c[field]
    if agg == "count_distinct":
        return func.count(func.distinct(col))
    return {"sum": func.sum, "avg": func.avg, "max": func.max, "min": func.min}[agg](col)


def _round_num(v):
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, float):
        return round(v, 2)
    return v


def _base_conds(table, fields_by_name: dict, block_filters: dict, date_field: str,
                start: datetime, end: datetime, viewer_rules: list | None = None):
    conds = [dyn_engine.build_condition(table, fields_by_name, f) for f in (block_filters or {}).get("rules") or []]
    conds = dyn_engine.combine_conditions(conds, (block_filters or {}).get("logic"))
    # 查看端筛选恒为 AND，叠加在区块筛选之上
    conds += [dyn_engine.build_condition(table, fields_by_name, f) for f in viewer_rules or []]
    return conds + _time_conds(table, fields_by_name, date_field, start, end)


def _option_label(f: MetaField | None, key) -> str:
    """枚举字段的分组 key 回显为 option 的 label（兼容字符串和 {label,value} 两种形态）。"""
    if key is None:
        return "（空）"
    if f is not None and f.widget == "select":
        for o in (f.options or {}).get("options") or []:
            if isinstance(o, dict):
                if o.get("value") == key:
                    return str(o.get("label") or o.get("value"))
            elif o == key:
                return str(o)
    return str(dyn_engine.serialize_value(key))


def _stat_value_sql(db, table, fields_by_name: dict, block: dict, date_field: str,
                    start: datetime, end: datetime, viewer_rules: list | None):
    """统计卡数值。ratio（占比）= 满足区块筛选的记录数 / 口径内（含查看者筛选）总记录数 × 100。"""
    conds = _base_conds(table, fields_by_name, block.get("filters"), date_field, start, end, viewer_rules)
    if block["agg"] == "ratio":
        num = db.execute(select(func.count()).select_from(table).where(*conds)).scalar() or 0
        den_conds = _base_conds(table, fields_by_name, None, date_field, start, end, viewer_rules)
        den = db.execute(select(func.count()).select_from(table).where(*den_conds)).scalar() or 0
        return round(num / den * 100, 2) if den else 0
    v = db.execute(select(_agg_expr(table, block["agg"], block.get("field"))).select_from(table).where(*conds)).scalar()
    return _round_num(v if v is not None else 0)


def _compare_payload(cur, prev) -> dict:
    """环比：当前值 vs 等长上一期。prev 为 0 时无法计算百分比，返回 None。"""
    delta = _round_num(cur - prev)
    return {"prev": prev, "delta": delta, "delta_pct": round(delta / prev * 100, 1) if prev else None}


def _eval_stat(db, table, fields_by_name, block, date_field, start, end, viewer_rules=None) -> dict:
    v = _stat_value_sql(db, table, fields_by_name, block, date_field, start, end, viewer_rules)
    out = {"id": block["id"], "type": "stat", "title": block.get("title") or "", "value": v, "agg": block["agg"]}
    if block.get("compare"):
        span = end - start  # 环比：等长上一期
        prev = _stat_value_sql(db, table, fields_by_name, block, date_field, start - span, start, viewer_rules)
        out["compare"] = _compare_payload(v, prev)
    return out


def _eval_chart(db, table, fields_by_name, block, date_field, start, end, viewer_rules=None) -> dict:
    conds = _base_conds(table, fields_by_name, block.get("filters"), date_field, start, end, viewer_rules)
    group = block.get("group") or {}
    gkind, gfield = group.get("kind") or "field", group.get("field")
    gcol = table.c[gfield]
    if gkind == "field":
        gexpr = gcol
    else:
        # SQLite strftime：%W 周一为周首（跨年边界第 0 周有坑，业务周报够用）
        fmt = {"day": "%Y-%m-%d", "week": "%Y-%W", "month": "%Y-%m"}[gkind]
        gexpr = func.strftime(fmt, gcol)
    agg = block.get("agg") or "count"
    vexpr = _agg_expr(table, agg, block.get("field"))

    if gkind == "field":
        # 字段分组：按值降序取 top_n，其余合并为"其他"
        top_n = int(block.get("top_n") or CHART_TOP_N_DEFAULT.get(block.get("chart_type"), 30))
        rows = db.execute(
            select(gexpr.label("g"), vexpr.label("v")).select_from(table).where(*conds)
            .group_by(gexpr).order_by(func.count().desc() if agg == "count" else vexpr.desc())
        ).all()
        gf = fields_by_name.get(gfield)
        labels, values, other = [], [], 0
        for i, r in enumerate(rows):
            if i < top_n:
                labels.append(_option_label(gf, r.g))
                values.append(_round_num(r.v or 0))
            else:
                other += r.v or 0
        if other:
            labels.append("其他")
            values.append(_round_num(other))
    else:
        # 日期分组：按时间升序
        rows = db.execute(
            select(gexpr.label("g"), vexpr.label("v")).select_from(table).where(*conds)
            .group_by(gexpr).order_by(gexpr)
        ).all()
        labels = [str(r.g) if r.g is not None else "（空）" for r in rows]
        values = [_round_num(r.v or 0) for r in rows]
    return {
        "id": block["id"], "type": "chart", "title": block.get("title") or "",
        "chart_type": block.get("chart_type"), "labels": labels, "values": values,
        "agg": agg,
    }


def _eval_table(db, table, fields_by_name, block, date_field, start, end, viewer_rules=None) -> dict:
    conds = _base_conds(table, fields_by_name, block.get("filters"), date_field, start, end, viewer_rules)
    cols = block.get("columns") or []
    limit = min(max(int(block.get("limit") or 100), 1), TABLE_LIMIT_MAX)
    total = db.execute(select(func.count()).select_from(table).where(*conds)).scalar() or 0

    sort_by = block.get("sort_by")
    if sort_by in fields_by_name or sort_by in SYSTEM_FIELDS:
        order_col = table.c[sort_by]
        order = order_col.asc() if block.get("sort_order") == "asc" else order_col.desc()
    else:
        order = table.c.id.desc()
    sel_cols = [table.c[c] for c in cols] + [table.c.id]
    rows = db.execute(
        select(*sel_cols).select_from(table).where(*conds).order_by(order).limit(limit)
    ).mappings().all()

    def col_label(c):
        f = fields_by_name.get(c)
        return f.label if f else {"id": "ID", "created_at": "创建时间", "updated_at": "更新时间"}[c]

    # 枚举列值回显为 label
    select_fields = {c: fields_by_name[c] for c in cols
                     if c in fields_by_name and fields_by_name[c].widget == "select"}
    out_rows = []
    for r in rows:
        d = dyn_engine.row_to_dict(r)
        for c, f in select_fields.items():
            d[c] = _option_label(f, d.get(c)) if d.get(c) is not None else d.get(c)
        out_rows.append(d)
    return {
        "id": block["id"], "type": "table", "title": block.get("title") or "",
        "columns": [{"prop": c, "label": col_label(c)} for c in cols],
        "rows": out_rows, "total": total, "truncated": total > limit,
    }


def _eval_text(block: dict, context: dict) -> dict:
    import re

    def repl(m):
        key = m.group(1)
        v = context.get(key)
        return "" if v is None else str(v)
    content = re.sub(r"\{([a-zA-Z0-9_]+)\}", repl, block.get("content") or "")
    return {"id": block["id"], "type": "text", "title": block.get("title") or "", "content": content}


# ---------- json 模式：Python 侧求值（输出结构与 SQL 路径一致） ----------

def _py_agg(rows: list[dict], agg: str, field: str | None):
    """对齐 _agg_expr：count=len（count(*) 语义）；count_distinct 去重计数；sum/avg/max/min 跳过 None，空集 → 0。"""
    if agg == "count":
        return len(rows)
    if agg == "count_distinct":
        return len({r.get(field) for r in rows if r.get(field) is not None})
    vals = [r.get(field) for r in rows if r.get(field) is not None]
    if not vals:
        return 0
    if agg == "sum":
        return sum(vals)
    if agg == "avg":
        return sum(vals) / len(vals)
    if agg == "max":
        return max(vals)
    return min(vals)


def _run_py(db, mt, fields, tpl, date_field, start, end, label, viewer_rules=None) -> dict:
    from . import json_store
    from .pyquery import match_filters, sort_records

    fields_by_name = {f.field_name: f for f in fields}
    recs = json_store.all_dicts(db, mt.id, fields, normalized=True)
    viewer_filters = {"logic": "AND", "rules": viewer_rules or []}   # 查看端筛选恒 AND
    date_f = fields_by_name.get(date_field)

    def time_recs(s, e) -> list[dict]:
        """口径 [s,e) 内 + 查看端筛选的记录（不含区块自身筛选，供 ratio 分母/环比复用）。"""
        def in_range(r):
            v = r.get(date_field)
            if v is None:
                return False  # SQL 三值逻辑：NULL 比较即排除
            try:
                if date_f is not None and date_f.data_type == "date":
                    return s.date() <= v < e.date()
                return s <= v < e
            except TypeError:
                return False

        return [r for r in recs if match_filters(r, fields_by_name, viewer_filters) and in_range(r)]

    def base_recs(block, s=start, e=end) -> list[dict]:
        return [r for r in time_recs(s, e) if match_filters(r, fields_by_name, block.get("filters") or {})]

    def stat_value(block, s, e):
        if block["agg"] == "ratio":
            rows_all = time_recs(s, e)
            num = len([r for r in rows_all if match_filters(r, fields_by_name, block.get("filters") or {})])
            return round(num / len(rows_all) * 100, 2) if rows_all else 0
        return _py_agg(base_recs(block, s, e), block["agg"], block.get("field"))

    def eval_stat(block):
        v = _round_num(stat_value(block, start, end))
        out = {"id": block["id"], "type": "stat", "title": block.get("title") or "", "value": v, "agg": block["agg"]}
        if block.get("compare"):
            span = end - start  # 环比：等长上一期
            prev = _round_num(stat_value(block, start - span, start))
            out["compare"] = _compare_payload(v, prev)
        return out

    def eval_chart(block):
        rows = base_recs(block)
        group = block.get("group") or {}
        gkind, gfield = group.get("kind") or "field", group.get("field")
        agg = block.get("agg") or "count"
        gf = fields_by_name.get(gfield)
        if gkind == "field":
            buckets: dict = {}
            for r in rows:
                buckets.setdefault(r.get(gfield), []).append(r)
            ordered = sorted(
                buckets.items(),
                key=lambda kv: len(kv[1]) if agg == "count" else (_py_agg(kv[1], agg, block.get("field")) or 0),
                reverse=True,
            )
            top_n = int(block.get("top_n") or CHART_TOP_N_DEFAULT.get(block.get("chart_type"), 30))
            labels, values, other = [], [], 0
            for i, (k, rs) in enumerate(ordered):
                v = _py_agg(rs, agg, block.get("field")) or 0
                if i < top_n:
                    labels.append(_option_label(gf, k))
                    values.append(_round_num(v))
                else:
                    other += v
            if other:
                labels.append("其他")
                values.append(_round_num(other))
        else:
            # Python strftime('%Y-%W') 与 SQLite strftime('%Y-%W') 同为 C 库 %W 语义（周一为周首），结果等价
            fmt = {"day": "%Y-%m-%d", "week": "%Y-%W", "month": "%Y-%m"}[gkind]
            buckets = {}
            for r in rows:
                v = r.get(gfield)
                key = v.strftime(fmt) if isinstance(v, (date, datetime)) else None
                buckets.setdefault(key, []).append(r)
            ordered = sorted(buckets.items(), key=lambda kv: (kv[0] is not None, kv[0] or ""))
            labels = [k if k is not None else "（空）" for k, _ in ordered]
            values = [_round_num(_py_agg(rs, agg, block.get("field")) or 0) for _, rs in ordered]
        return {
            "id": block["id"], "type": "chart", "title": block.get("title") or "",
            "chart_type": block.get("chart_type"), "labels": labels, "values": values,
            "agg": agg,
        }

    def eval_table(block):
        rows = base_recs(block)
        cols = block.get("columns") or []
        limit = min(max(int(block.get("limit") or 100), 1), TABLE_LIMIT_MAX)
        total = len(rows)
        sort_by = block.get("sort_by")
        rows = sort_records(rows, sort_by if sort_by in (set(fields_by_name) | SYSTEM_FIELDS) else None,
                            block.get("sort_order"), fields_by_name)

        def col_label(c):
            f = fields_by_name.get(c)
            return f.label if f else {"id": "ID", "created_at": "创建时间", "updated_at": "更新时间"}[c]

        select_fields = {c: fields_by_name[c] for c in cols
                         if c in fields_by_name and fields_by_name[c].widget == "select"}
        out_rows = []
        for r in rows[:limit]:
            d = {c: dyn_engine.serialize_value(r.get(c)) for c in cols}
            d["id"] = r["id"]
            for c, f in select_fields.items():
                if d.get(c) is not None:
                    d[c] = _option_label(f, d.get(c))
            out_rows.append(d)
        return {
            "id": block["id"], "type": "table", "title": block.get("title") or "",
            "columns": [{"prop": c, "label": col_label(c)} for c in cols],
            "rows": out_rows, "total": total, "truncated": total > limit,
        }

    blocks = tpl.blocks_json or []
    results_by_id, stat_values = {}, {}
    for b in blocks:
        t = b.get("type")
        if t == "stat":
            r = eval_stat(b)
            stat_values[b["id"]] = r["value"]
            results_by_id[b["id"]] = r
        elif t == "chart":
            results_by_id[b["id"]] = eval_chart(b)
        elif t == "table":
            results_by_id[b["id"]] = eval_table(b)
    context = {"range_label": label, "start": f"{start:%Y-%m-%d}", "end": f"{end:%Y-%m-%d}", **stat_values}
    for b in blocks:
        if b.get("type") == "text":
            results_by_id[b["id"]] = _eval_text(b, context)
    blocks_out = [results_by_id[b["id"]] for b in blocks if b.get("id") in results_by_id]

    return {
        "template_id": tpl.id, "name": tpl.name, "table_label": mt.label,
        "range": {"start": f"{start:%Y-%m-%d}", "end": f"{end:%Y-%m-%d}", "label": label},
        "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "blocks": blocks_out,
    }


def _validate_viewer_filters(tpl: ReportTemplate, fields: list, viewer_filters: dict | None) -> list:
    """查看端筛选：只允许筛模板声明过（filters_json）的字段，防止越权过滤任意列。"""
    rules = (viewer_filters or {}).get("rules") or []
    if not rules:
        return []
    declared = set(tpl.filters_json or [])
    fields_by_name = {f.field_name: f for f in fields}
    for r in rules:
        name = r.get("field")
        if name not in declared:
            raise HTTPException(400, f"该字段未开放查看端筛选：{name}")
        if r.get("op") not in dyn_engine.FILTER_OPS:
            raise HTTPException(400, f"不支持的筛选操作符：{r.get('op')}")
        if not dyn_engine.rule_value_ok(fields_by_name.get(name), r.get("op"), r.get("value")):
            raise HTTPException(400, f"筛选值无效（{name}）")
    return rules


def run_template(db: Session, tpl: ReportTemplate, range_override: dict | None = None,
                 viewer_filters: dict | None = None) -> dict:
    """执行报表模板，返回结构化结果（前端渲染 / 导出共用）。viewer_filters 为查看端自助筛选。"""
    mt, fields = dyn_engine.load_meta(db, tpl.table_id)
    viewer_rules = _validate_viewer_filters(tpl, fields, viewer_filters)
    rng = dict(tpl.range_json or {})
    if range_override:
        rng.update({k: v for k, v in range_override.items() if v is not None})
    date_field = rng.get("date_field") or "created_at"
    try:
        start, end, label = resolve_time_range(rng)
    except ReportError as e:
        raise HTTPException(400, str(e))

    if mt.storage_mode == "json":
        return _run_py(db, mt, fields, tpl, date_field, start, end, label, viewer_rules)

    _, fields, table = dyn_engine.load_business(db, tpl.table_id)
    fields_by_name = {f.field_name: f for f in fields}

    blocks = tpl.blocks_json or []
    results_by_id, stat_values = {}, {}
    for b in blocks:
        t = b.get("type")
        if t == "stat":
            r = _eval_stat(db, table, fields_by_name, b, date_field, start, end, viewer_rules)
            stat_values[b["id"]] = r["value"]
            results_by_id[b["id"]] = r
        elif t == "chart":
            results_by_id[b["id"]] = _eval_chart(db, table, fields_by_name, b, date_field, start, end, viewer_rules)
        elif t == "table":
            results_by_id[b["id"]] = _eval_table(db, table, fields_by_name, b, date_field, start, end, viewer_rules)
    context = {"range_label": label, "start": f"{start:%Y-%m-%d}", "end": f"{end:%Y-%m-%d}", **stat_values}
    for b in blocks:
        if b.get("type") == "text":
            results_by_id[b["id"]] = _eval_text(b, context)
    blocks_out = [results_by_id[b["id"]] for b in blocks if b.get("id") in results_by_id]

    return {
        "template_id": tpl.id, "name": tpl.name, "table_label": mt.label,
        "range": {"start": f"{start:%Y-%m-%d}", "end": f"{end:%Y-%m-%d}", "label": label},
        "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "blocks": blocks_out,
    }


# ---------- 定时推送 ----------

def render_email_html(result: dict) -> str:
    """邮件正文：纯 HTML（邮件客户端禁 JS），stat 大数字 + 数据表，不出图。"""
    import html as html_mod

    def esc(v):
        return html_mod.escape("" if v is None else str(v))

    parts = [
        f'<h2 style="margin:0 0 4px">{esc(result["name"])}</h2>',
        f'<p style="color:#888;margin:0 0 16px">{esc(result["range"]["label"])} · 生成于 {esc(result["generated_at"])}</p>',
    ]
    stats = [b for b in result["blocks"] if b["type"] == "stat"]
    if stats:
        cells = "".join(
            f'<td style="padding:12px 20px;background:#f5f7fa;border-radius:8px;text-align:center">'
            f'<div style="font-size:12px;color:#888">{esc(b["title"])}</div>'
            f'<div style="font-size:24px;font-weight:600;color:#303133">{esc(b["value"])}</div></td>'
            f'<td style="width:12px"></td>'
            for b in stats
        )
        parts.append(f'<table cellpadding="0" cellspacing="0"><tr>{cells}</tr></table>')
    for b in result["blocks"]:
        if b["type"] == "chart":
            rows = "".join(
                f'<tr><td style="padding:4px 12px;border:1px solid #e4e7ed">{esc(l)}</td>'
                f'<td style="padding:4px 12px;border:1px solid #e4e7ed;text-align:right">{esc(v)}</td></tr>'
                for l, v in zip(b["labels"], b["values"])
            )
            parts.append(f'<h3 style="margin:20px 0 8px">{esc(b["title"])}</h3>'
                         f'<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13px">{rows}</table>')
        elif b["type"] == "table":
            head = "".join(f'<th style="padding:4px 12px;border:1px solid #e4e7ed;background:#f5f7fa">{esc(c["label"])}</th>' for c in b["columns"])
            rows = "".join(
                "<tr>" + "".join(f'<td style="padding:4px 12px;border:1px solid #e4e7ed">{esc(r.get(c["prop"]))}</td>' for c in b["columns"]) + "</tr>"
                for r in b["rows"][:50]
            )
            note = f'<p style="color:#888;font-size:12px">共 {b["total"]} 条，仅显示前 50 条</p>' if b["total"] > 50 else ""
            parts.append(f'<h3 style="margin:20px 0 8px">{esc(b["title"])}</h3>'
                         f'<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13px"><tr>{head}</tr>{rows}</table>{note}')
        elif b["type"] == "text":
            parts.append(f'<p style="margin:16px 0;color:#606266">{esc(b["content"])}</p>')
    return '<div style="font-family:Helvetica,Arial,sans-serif;max-width:720px">' + "".join(parts) + "</div>"


# ---------- Webhook 推送（企业微信/钉钉群机器人） ----------

def render_markdown(result: dict, max_rows: int = 10) -> str:
    """报表结果的 Markdown 摘要，供群机器人推送。企微 markdown 不支持表格/图片，统一用列表行。"""
    lines = [f"### 【{result['name']}】{result['range']['label']}"]
    stats = [b for b in result["blocks"] if b["type"] == "stat"]
    if stats:
        for b in stats:
            cell = f"**{b['title']}**：{b['value']}{'%' if b.get('agg') == 'ratio' else ''}"
            cmp_ = b.get("compare")
            if cmp_:
                cell += f"（较上期 {'↑' if cmp_['delta'] >= 0 else '↓'}{abs(cmp_['delta_pct'])}%）" if cmp_["delta_pct"] is not None else "（上期无对比基数）"
            lines.append(f"- {cell}")
    for b in result["blocks"]:
        if b["type"] == "chart":
            lines.append(f"\n**{b['title']}**")
            lines += [f"- {l}：{v}" for l, v in zip(b["labels"], b["values"])]
        elif b["type"] == "table":
            note = f"（共 {b['total']} 条，仅显示前 {min(len(b['rows']), max_rows)} 条）" if b["total"] > max_rows else ""
            lines.append(f"\n**{b['title']}**{note}")
            head = " | ".join(str(c["label"]) for c in b["columns"])
            lines.append(f"`{head}`")
            for r in b["rows"][:max_rows]:
                lines.append("- " + " | ".join(str(r.get(c["prop"]) or "—") for c in b["columns"]))
        elif b["type"] == "text":
            lines.append(f"\n{b['content']}")
    return "\n".join(lines)


def _post_webhook(wh: dict, subject: str, md: str) -> None:
    """按机器人协议 POST Markdown 消息，失败抛 ReportError。custom 类型直接 POST 原始 JSON。"""
    url = (wh.get("url") or "").strip()
    wtype = wh.get("type") or "wecom"
    label = WEBHOOK_TYPES.get(wtype, wtype)
    if wtype == "wecom":
        payload = {"msgtype": "markdown", "markdown": {"content": md}}
    elif wtype == "dingtalk":
        payload = {"msgtype": "markdown", "markdown": {"title": subject, "text": md}}
    else:
        payload = {"title": subject, "markdown": md}
    try:
        resp = httpx.post(url, json=payload, timeout=15)
    except httpx.HTTPError as e:
        raise ReportError(f"{label} Webhook 请求失败：{e}")
    if resp.status_code >= 400:
        raise ReportError(f"{label} Webhook 返回 {resp.status_code}")
    if wtype in ("wecom", "dingtalk"):
        try:
            errcode = resp.json().get("errcode", 0)
        except ValueError:
            return
        if errcode:
            raise ReportError(f"{label}机器人报错：{resp.text[:100]}")


def push_template(template_id: int, trigger: str = "schedule") -> dict | None:
    """生成报表并推送（邮件 + 群机器人 Webhook），写 ReportRunLog。供调度器和手动调用。"""
    from .report_export import export_xlsx

    db = SessionLocal()
    try:
        tpl = db.get(ReportTemplate, template_id)
        if not tpl:
            return None
        if trigger == "schedule" and not tpl.enabled:
            return None

        run = ReportRunLog(template_id=tpl.id, trigger=trigger, run_at=datetime.now())
        try:
            result = run_template(db, tpl)
            run.range_label = result["range"]["label"]
            push = tpl.push_json or {}
            recipients = [s.strip() for s in str(push.get("recipients") or "").replace("，", ",").split(",") if s.strip()]
            webhooks = [w for w in (push.get("webhooks") or []) if (w.get("url") or "").strip()]
            if not recipients and not webhooks:
                raise ReportError("未配置推送渠道（收件邮箱或群机器人 Webhook）")
            subject = (push.get("subject") or "【{name}】{range_label}").replace("{name}", tpl.name).replace("{range_label}", result["range"]["label"])

            errors = []
            sent = 0
            if recipients:  # 邮件渠道
                formats = push.get("formats") or ["html_inline"]
                attachments = []
                if "xlsx" in formats:
                    buf = export_xlsx(result)
                    attachments.append((f"{tpl.name}-{result['range']['label']}.xlsx", buf.getvalue(),
                                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
                body_html = render_email_html(result) if "html_inline" in formats else f"请查看附件报表。{result['range']['label']}"
                try:
                    send_smtp_html(get_setting(db, "smtp"), recipients, subject, body_html, attachments)
                    sent += len(recipients)
                except Exception as e:  # noqa: BLE001 — 单渠道失败不阻塞其他渠道，错误汇总落日志
                    errors.append(str(e))
            if webhooks:  # 群机器人渠道
                md = render_markdown(result)
                for wh in webhooks:
                    try:
                        _post_webhook(wh, subject, md)
                        sent += 1
                    except Exception as e:  # noqa: BLE001
                        errors.append(str(e))
            run.sent_count = sent
            if errors:
                run.error = "；".join(errors)[:500]
        except Exception as e:  # noqa: BLE001 — 推送失败落日志
            db.rollback()
            run.error = str(e)[:500]
        db.add(run)
        db.commit()
        return {"sent": run.sent_count, "range_label": run.range_label, "error": run.error}
    finally:
        db.close()
