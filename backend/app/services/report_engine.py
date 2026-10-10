"""报表引擎：时间口径解析、模板校验、区块求值（统计卡片/图表/明细表/文本）、定时推送。"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
from fastapi import HTTPException
from sqlalchemy import func, not_, or_, select
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import MetaField, ReportRunLog, ReportTemplate
from . import dyn_engine
from . import report_dataset as ds
from .actions import get_setting, send_smtp_html

BLOCK_TYPES = {"stat", "chart", "table", "text", "pivot", "filter"}
AGG_TYPES = {"count", "count_distinct", "sum", "avg", "max", "min", "ratio"}
CHART_AGG_TYPES = AGG_TYPES - {"ratio"}   # ratio（占比）仅统计卡：满足区块筛选数 / 口径内总数
NUMERIC_TYPES = {"int", "decimal"}
CHART_TYPES = {"bar", "line", "pie", "area", "gauge", "mixed", "funnel"}
GROUP_KINDS = {"field", "day", "week", "month"}
RANGE_MODES = {"today", "yesterday", "past_7d", "past_30d", "this_week", "last_week",
               "this_month", "last_month", "this_quarter", "this_year", "custom"}
COMPARE_MODES = {"mom", "yoy"}   # mom 环比（等长上一期）/ yoy 同比（去年同期）
QUICK_CALCS = {"pct"}            # 快速计算：pct 占总计百分比
SYSTEM_FIELDS = {"id", "created_at", "updated_at"}
TABLE_LIMIT_MAX = 500
CHART_TOP_N_DEFAULT = {"pie": 8, "funnel": 8, "bar": 30, "line": 30, "area": 30, "mixed": 30}
SERIES_MAX = 5          # 多指标图表的指标上限
GROUP2_TOP_N = 8        # 二级分组系列上限，其余合并为"其他"系列
METRIC_AGG_LABELS = {"count": "记录数", "count_distinct": "去重计数", "sum": "求和",
                     "avg": "平均值", "max": "最大值", "min": "最小值"}
WEBHOOK_TYPES = {"wecom": "企业微信", "dingtalk": "钉钉", "custom": "自定义"}
PIVOT_ROW_TOP_N = (1, 100, 30)   # 透视表行维度 top_n（min, max, 默认）
PIVOT_COL_TOP_N = (1, 20, 8)     # 透视表列维度 top_n（min, max, 默认）

# ---------- 栅格布局 ----------
GRID_COLS = 24                   # 栅格列数（x + w ≤ 24）
GRID_PAGES_MAX = 10
# 各区块类型的最小/默认尺寸（w×h，行高 40px）
BLOCK_SIZE = {
    "stat":  {"min": (4, 3), "default": (6, 4)},
    "chart": {"min": (6, 6), "default": (12, 10)},
    "pivot": {"min": (8, 8), "default": (24, 12)},
    "table": {"min": (8, 6), "default": (24, 12)},
    "text":  {"min": (4, 2), "default": (12, 4)},
    "filter": {"min": (4, 2), "default": (6, 2)},
}


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


def _end_date_exclusive(end: datetime):
    """date 类型字段的排他右边界：end 是午夜（期界，如「上周」的右端本周一 00:00、自定义口径的 +1 天）
    时当天排除；end 是日间时刻（进行中的口径 end=now，如「本月」「近7天」）时当天应包含。"""
    midnight = end == end.replace(hour=0, minute=0, second=0, microsecond=0)
    return end.date() if midnight else end.date() + timedelta(days=1)


def _time_conds(table, fields_by_name: dict, date_field: str, start: datetime, end: datetime):
    """时间区间条件；date 类型字段与 date 比较。"""
    col = table.c[date_field]
    f = fields_by_name.get(date_field)
    if f is not None and f.data_type == "date":
        return [col >= start.date(), col < _end_date_exclusive(end)]
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


def _check_group_dim(fields_by_name: dict, group: dict, axis: str = "") -> None:
    """分组维度校验（chart group / pivot row/col 共用）：kind 合法、字段存在、时间型需日期字段。"""
    gkind, gfield = (group or {}).get("kind") or "field", (group or {}).get("field")
    prefix = f"{axis}维度" if axis else ""
    if gkind not in GROUP_KINDS:
        raise HTTPException(400, f"{prefix}不支持的分组方式：{gkind}")
    if not gfield:
        raise HTTPException(400, f"{prefix}需要选择分组字段")
    gf = fields_by_name.get(gfield)
    if gfield not in ("created_at", "updated_at") and gf is None:
        raise HTTPException(400, f"{prefix}分组字段不存在：{gfield}")
    if gkind in ("day", "week", "month"):
        is_date_type = (gf is not None and gf.data_type in ("date", "datetime")) or gfield in ("created_at", "updated_at")
        if not is_date_type:
            raise HTTPException(400, f"{prefix}按日/周/月分组需要选择日期类型字段")


def _check_top_n(block: dict, key: str, lo: int, hi: int) -> None:
    v = block.get(key)
    if v is None:
        return
    try:
        iv = int(v)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{key} 必须是整数")
    if not (lo <= iv <= hi):
        raise HTTPException(400, f"{key} 需在 {lo}~{hi} 之间")


def _validate_layout(layout: dict, block_types: dict[str, str]) -> None:
    """栅格布局校验：页数/页 id/标题，items 引用存在且不重复，坐标边界与最小尺寸。
    block_types: block_id -> type。允许区块不出现在任何页（未放置）。"""
    if not isinstance(layout, dict):
        raise HTTPException(400, "layout 必须是对象")
    pages = layout.get("pages")
    if not isinstance(pages, list) or not (1 <= len(pages) <= GRID_PAGES_MAX):
        raise HTTPException(400, f"布局页签数量须为 1~{GRID_PAGES_MAX}")
    page_ids = set()
    seen_items = set()
    for p in pages:
        if not isinstance(p, dict):
            raise HTTPException(400, "布局页签必须是对象")
        pid = p.get("id")
        if not pid or pid in page_ids:
            raise HTTPException(400, "布局页签 id 缺失或重复")
        page_ids.add(pid)
        if len(str(p.get("title") or "")) > 20:
            raise HTTPException(400, "页签标题不能超过 20 字")
        items = p.get("items")
        if not isinstance(items, list):
            raise HTTPException(400, f"页签「{p.get('title') or pid}」的 items 必须是数组")
        for it in items:
            if not isinstance(it, dict):
                raise HTTPException(400, "布局项必须是对象")
            bid = it.get("block_id")
            btype = block_types.get(bid)
            if btype is None:
                raise HTTPException(400, f"布局引用了不存在的区块：{bid}")
            if bid in seen_items:
                raise HTTPException(400, f"区块在布局中重复放置：{bid}")
            seen_items.add(bid)
            try:
                x, y, w, h = (int(it.get(k)) for k in ("x", "y", "w", "h"))
            except (TypeError, ValueError):
                raise HTTPException(400, f"区块 {bid} 的布局坐标必须是整数")
            min_w, min_h = BLOCK_SIZE[btype]["min"]
            if x < 0 or y < 0 or x + w > GRID_COLS:
                raise HTTPException(400, f"区块 {bid} 的布局越界（0 ≤ x 且 x+w ≤ {GRID_COLS}）")
            if w < min_w or h < min_h:
                raise HTTPException(400, f"区块 {bid} 尺寸小于最小值（{btype} 至少 {min_w}×{min_h}）")


def sectioned_blocks(result: dict) -> list[tuple[str | None, list[dict]]]:
    """按布局把结果区块分节：[(页标题, 该页区块按 y,x 排序), ...]。
    无布局时返回单节 (None, 原顺序)，导出/推送/邮件共用；未放置区块归入末节"其他"。"""
    blocks = result.get("blocks") or []
    layout = result.get("layout") or {}
    pages = layout.get("pages") or []
    if not pages:
        return [(None, blocks)]
    by_id = {b["id"]: b for b in blocks}
    sections: list[tuple[str | None, list[dict]]] = []
    placed: set[str] = set()
    for p in pages:
        items = sorted(p.get("items") or [], key=lambda it: (it.get("y", 0), it.get("x", 0)))
        sec = [by_id[it["block_id"]] for it in items if it.get("block_id") in by_id]
        placed.update(it["block_id"] for it in items if it.get("block_id") in by_id)
        sections.append((p.get("title") or "未命名", sec))
    rest = [b for b in blocks if b["id"] not in placed]
    if rest:
        sections.append(("其他", rest))
    return sections


def validate_template(db: Session, payload) -> None:
    from .meta_service import get_meta_fields, get_meta_table

    rng = payload.range or {}
    mode = rng.get("mode") or "this_week"
    if mode not in RANGE_MODES:
        raise HTTPException(400, f"不支持的时间口径：{mode}")
    if mode == "custom" and (rng.get("start") or rng.get("end")):
        resolve_time_range(rng)  # 校验日期格式（完整校验允许留空，运行时再要求）

    # ---------- 数据集（v3 命名数据集；旧格式 table_id+source 合成 _default） ----------
    datasets_in = ds.normalize_datasets(getattr(payload, "datasets", None) or None,
                                        payload.table_id, getattr(payload, "source", None))
    if payload.table_id and not get_meta_table(db, payload.table_id):
        raise HTTPException(400, "目标数据表不存在")
    ds_fields: dict[str, list] = {}
    ds_base_fields: dict[str, dict] = {}
    for d in datasets_in:
        did = d["id"]
        mt = get_meta_table(db, d["base_table_id"])
        if not mt:
            raise HTTPException(400, f"数据集「{d.get('name') or did}」的基表不存在：{d['base_table_id']}")
        base_fields = get_meta_fields(db, mt.id)
        src = ds.dataset_source(d)
        ds.validate_source(db, src, mt.id, mt, base_fields)
        ds_fields[did] = ds.dataset_fields(db, base_fields, src)
        ds_base_fields[did] = {f.field_name: f for f in base_fields}
    default_did = datasets_in[0]["id"] if datasets_in else None

    # 旧格式：全局 date_field 必须落在默认数据集的基表日期字段上
    if default_did and rng.get("date_field"):
        date_field = rng["date_field"]
        df = ds_base_fields[default_did].get(date_field)
        if date_field not in ("created_at", "updated_at") and (df is None or df.data_type not in ("date", "datetime")):
            raise HTTPException(400, "统计日期字段必须是日期/日期时间类型")

    ids = set()
    block_types = {}
    filter_targets: list[tuple[str, list]] = []   # (filter块id, 目标block_ids)
    for b in payload.blocks:
        t = b.get("type")
        if t not in BLOCK_TYPES:
            raise HTTPException(400, f"未知区块类型：{t}")
        bid = b.get("id")
        if not bid or bid in ids:
            raise HTTPException(400, "区块 id 缺失或重复")
        ids.add(bid)
        block_types[bid] = t
        # 逐块校验：任何错误统一带上区块 id 与标题，前端据此在画布上标红定位
        try:
            # 块所属数据集（text 块可无）
            did = b.get("dataset_id") or default_did
            if t != "text" and (not did or did not in ds_fields):
                raise HTTPException(400, f"引用的数据集不存在：{b.get('dataset_id')}")
            fields_by_name = {f.field_name: f for f in ds_fields.get(did, [])}
            _validate_filters(fields_by_name, b.get("filters"))
            # 块级口径：v3 range_mode 或旧 range_override；date_field 必须是该数据集的日期字段
            bdf = b.get("date_field")
            if bdf is not None and t != "text":
                bf = fields_by_name.get(bdf)
                if bdf not in ("created_at", "updated_at") and (bf is None or bf.data_type not in ("date", "datetime")):
                    raise HTTPException(400, f"日期字段无效：{bdf}")
            if b.get("range_mode") and b["range_mode"] not in RANGE_MODES:
                raise HTTPException(400, f"口径无效：{b.get('range_mode')}")
            ov = b.get("range_override") or {}
            if ov.get("mode"):
                if ov["mode"] not in RANGE_MODES:
                    raise HTTPException(400, f"口径覆盖无效：{ov['mode']}")
                if ov.get("date_field"):
                    raise HTTPException(400, "块级口径覆盖不支持更换日期字段")
            if t == "filter":
                ffield = b.get("field")
                if not ffield or ffield not in fields_by_name:
                    raise HTTPException(400, f"筛选组件必须选择数据集内字段：{ffield}")
                tgt = b.get("target") or {}
                tmode = tgt.get("mode") or "same_dataset"
                if tmode not in ("same_dataset", "blocks"):
                    raise HTTPException(400, f"筛选组件的作用域无效：{tmode}")
                if tmode == "blocks":
                    filter_targets.append((bid, list(tgt.get("block_ids") or [])))
            elif t == "stat":
                if b.get("agg") not in AGG_TYPES:
                    raise HTTPException(400, f"不支持的聚合方式：{b.get('agg')}")
                _check_numeric_field(fields_by_name, b["agg"], b.get("field"))
                ct = b.get("compare_type")
                if ct and ct not in COMPARE_MODES:
                    raise HTTPException(400, f"统计卡对比方式无效：{ct}")
            elif t == "chart":
                ctype = b.get("chart_type")
                if ctype not in CHART_TYPES:
                    raise HTTPException(400, f"不支持的图表类型：{ctype}")
                if ctype == "gauge":
                    # 仪表盘：单聚合值 + max，无分组/系列
                    gagg = b.get("agg") or "count"
                    if gagg not in CHART_AGG_TYPES:
                        raise HTTPException(400, f"仪表盘不支持的聚合方式：{gagg}")
                    _check_numeric_field(fields_by_name, gagg, b.get("field"))
                    gmax = b.get("max")
                    if gmax is not None and (not isinstance(gmax, (int, float)) or gmax <= 0):
                        raise HTTPException(400, "仪表盘 max 必须是正数")
                else:
                    metrics = [m for m in (b.get("metrics") or []) if m.get("agg")]
                    g2field = (b.get("group2") or {}).get("field")
                    if metrics and g2field:
                        raise HTTPException(400, "多指标与二级分组不能同时使用")
                    if len(metrics) > SERIES_MAX:
                        raise HTTPException(400, f"多指标最多 {SERIES_MAX} 个")
                    if ctype in ("pie", "funnel") and (metrics or g2field):
                        raise HTTPException(400, "饼图/漏斗图不支持多系列（多指标/二级分组）")
                    if ctype == "mixed":
                        # 组合图（柱线双轴）：多指标，每个指标选柱状/折线；不支持二级分组/堆叠
                        if g2field:
                            raise HTTPException(400, "组合图不支持二级分组（用多指标并分别选柱状/折线）")
                        if b.get("stack"):
                            raise HTTPException(400, "组合图不支持堆叠")
                        if len(metrics) < 2:
                            raise HTTPException(400, "组合图需要至少 2 个指标")
                        for m in metrics:
                            if (m.get("chart") or "") not in ("", "bar", "line"):
                                raise HTTPException(400, f"指标「{m.get('title') or m.get('agg')}」的图形只能是柱状/折线")
                    if b.get("stack") and ctype not in ("bar", "line", "area"):
                        raise HTTPException(400, "堆叠仅支持柱状/折线/面积图")
                    qc = b.get("quick_calc")
                    if qc and qc not in QUICK_CALCS:
                        raise HTTPException(400, f"不支持的数值显示方式：{qc}")
                    if qc == "pct" and ctype in ("pie", "funnel"):
                        raise HTTPException(400, "饼图/漏斗图本身就是占比，无需占比显示")
                    cmp_ = b.get("compare")
                    if cmp_ and cmp_ not in COMPARE_MODES:
                        raise HTTPException(400, f"图表对比方式无效：{cmp_}")
                    if cmp_ and qc == "pct":
                        raise HTTPException(400, "占比显示与对比不能同时使用")
                    for m in metrics or [{"agg": b.get("agg") or "count", "field": b.get("field")}]:
                        if (m.get("agg") or "count") not in CHART_AGG_TYPES:
                            raise HTTPException(400, f"图表不支持的聚合方式：{m.get('agg')}")
                        _check_numeric_field(fields_by_name, m.get("agg") or "count", m.get("field"))
                    group = b.get("group") or {}
                    _check_group_dim(fields_by_name, group)
                    if cmp_ and (group.get("kind") or "field") not in ("day", "week", "month"):
                        raise HTTPException(400, "对比（环比/同比）仅支持按日/周/月分组的图表")
                    if g2field:
                        g2f = fields_by_name.get(g2field)
                        if g2f is None:
                            raise HTTPException(400, f"二级分组字段不存在：{g2field}")
                        if g2f.data_type in ("date", "datetime"):
                            raise HTTPException(400, "二级分组不支持日期类型字段")
                    if b.get("on_click") not in (None, "drill", "link", "jump"):
                        raise HTTPException(400, f"图表点击行为无效：{b.get('on_click')}")
                    # 层级钻取：按字段分组时再下钻到下一层字段（如 区域 → 城市）
                    dd = b.get("drill_down") or {}
                    if dd.get("field"):
                        if (group.get("kind") or "field") != "field":
                            raise HTTPException(400, "层级钻取仅支持按字段分组的图表")
                        if ctype in ("gauge", "funnel"):
                            raise HTTPException(400, "仪表盘/漏斗图不支持层级钻取")
                        ddf = dd["field"]
                        if ddf not in fields_by_name and ddf not in SYSTEM_FIELDS:
                            raise HTTPException(400, f"层级钻取字段不存在：{ddf}")
                        if ddf == group.get("field"):
                            raise HTTPException(400, "层级钻取字段不能与分组字段相同")
                        if b.get("on_click") in ("link", "jump"):
                            raise HTTPException(400, "层级钻取与联动/跳转不能同时使用")
                    # 跳转其他报表：带着点击的分组值作为目标报表的联动过滤
                    if b.get("on_click") == "jump":
                        if (group.get("kind") or "field") != "field":
                            raise HTTPException(400, "跳转其他报表需要按字段分组（点击的值作为联动条件）")
                        rid = b.get("jump_report_id")
                        if not isinstance(rid, int) or db.get(ReportTemplate, rid) is None:
                            raise HTTPException(400, "跳转的目标报表不存在")
            elif t == "pivot":
                row, col = b.get("row") or {}, b.get("col") or {}
                _check_group_dim(fields_by_name, row, "行")
                _check_group_dim(fields_by_name, col, "列")
                if (row.get("kind") or "field") == (col.get("kind") or "field") and row.get("field") == col.get("field"):
                    raise HTTPException(400, "行维度与列维度不能使用同一分组")
                agg = b.get("agg")
                if agg not in CHART_AGG_TYPES:
                    raise HTTPException(400, f"透视表不支持的聚合方式：{agg}")
                _check_numeric_field(fields_by_name, agg, b.get("field"))
                _check_top_n(b, "row_top_n", *PIVOT_ROW_TOP_N[:2])
                _check_top_n(b, "col_top_n", *PIVOT_COL_TOP_N[:2])
            elif t == "table":
                # 空列 = 默认全部字段（运行期展开），合法；配置了列则必须都存在
                for c in b.get("columns") or []:
                    if c not in fields_by_name and c not in SYSTEM_FIELDS:
                        raise HTTPException(400, f"明细列不存在：{c}")
        except HTTPException as e:
            raise HTTPException(e.status_code, f"区块 {bid}（{b.get('title') or b.get('type')}）：{e.detail}")

    # 筛选组件的目标区块必须存在
    for fb_id, targets in filter_targets:
        for tid in targets:
            if tid not in ids:
                raise HTTPException(400, f"筛选组件 {fb_id} 的目标区块不存在：{tid}")

    # 查看端可筛选字段（旧格式）必须是默认数据集字段
    default_fields_by_name = {f.field_name: f for f in ds_fields.get(default_did, [])}
    for fn in getattr(payload, "filter_fields", None) or []:
        if fn not in default_fields_by_name:
            raise HTTPException(400, f"查看端筛选字段不存在：{fn}")

    # 栅格布局（可选）
    if getattr(payload, "layout", None) is not None:
        _validate_layout(payload.layout, block_types)

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


def _group_expr(table, gkind: str, gfield: str):
    """分组表达式：field 取原列；day/week/month 用 SQLite strftime（%W 周一为周首）。"""
    col = table.c[gfield]
    if gkind == "field":
        return col
    fmt = {"day": "%Y-%m-%d", "week": "%Y-%W", "month": "%Y-%m"}[gkind]
    return func.strftime(fmt, col)


def _rest_cond(expr, master_keys):
    """"其他"桶条件：不在 master keys 内（含 NULL 处理）。master 为空时返回 None（不约束）。"""
    in_master = []
    nn = [k for k in master_keys if k is not None]
    if nn:
        in_master.append(expr.in_(nn))
    if any(k is None for k in master_keys):
        in_master.append(expr.is_(None))
    return not_(or_(*in_master)) if in_master else None


def _base_conds(table, fields_by_name: dict, block_filters: dict, date_field: str | None,
                start: datetime | None, end: datetime | None, viewer_rules: list | None = None):
    conds = [dyn_engine.build_condition(table, fields_by_name, f) for f in (block_filters or {}).get("rules") or []]
    conds = dyn_engine.combine_conditions(conds, (block_filters or {}).get("logic"))
    # 查看端筛选恒为 AND，叠加在区块筛选之上
    conds += [dyn_engine.build_condition(table, fields_by_name, f) for f in viewer_rules or []]
    if date_field is not None and start is not None:   # date_field=None 的块不做时间过滤
        conds += _time_conds(table, fields_by_name, date_field, start, end)
    return conds


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


def _shift_range(start: datetime, end: datetime, mode: str) -> tuple[datetime, datetime]:
    """对比期位移：mom 环比 = 等长上一期；yoy 同比 = 去年同期（2/29 回落 2/28）。"""
    if mode == "yoy":
        def back1y(d: datetime) -> datetime:
            try:
                return d.replace(year=d.year - 1)
            except ValueError:
                return d.replace(year=d.year - 1, day=28)
        return back1y(start), back1y(end)
    span = end - start
    return start - span, start


COMPARE_SUFFIX = {"mom": "上期", "yoy": "去年同期"}


def _compare_payload(cur, prev, cmp_type: str = "mom") -> dict:
    """环比/同比：当前值 vs 对比期。prev 为 0 时无法计算百分比，返回 None。"""
    delta = _round_num(cur - prev)
    return {"prev": prev, "delta": delta, "delta_pct": round(delta / prev * 100, 1) if prev else None, "type": cmp_type}


def _eval_stat(db, table, fields_by_name, block, date_field, start, end, viewer_rules=None) -> dict:
    v = _stat_value_sql(db, table, fields_by_name, block, date_field, start, end, viewer_rules)
    out = {"id": block["id"], "type": "stat", "title": block.get("title") or "", "value": v, "agg": block["agg"]}
    if block.get("compare") and start is not None:
        ctype = block.get("compare_type") or "mom"
        ps, pe = _shift_range(start, end, ctype)
        prev = _stat_value_sql(db, table, fields_by_name, block, date_field, ps, pe, viewer_rules)
        out["compare"] = _compare_payload(v, prev, ctype)
    return out


def _chart_metrics(block: dict, fields_by_name: dict) -> list[dict]:
    """图表指标列表：metrics 非空时优先（多指标），否则退化为单指标 {agg, field}。每项补上显示名。"""
    ms = [m for m in (block.get("metrics") or []) if m.get("agg")]
    if not ms:
        ms = [{"agg": block.get("agg") or "count", "field": block.get("field")}]
    out = []
    for m in ms:
        agg = m.get("agg") or "count"
        name = m.get("title")
        if not name:
            if agg == "count":
                name = "记录数"
            else:
                f = fields_by_name.get(m.get("field") or "")
                name = f"{f.label if f else m.get('field')}{METRIC_AGG_LABELS.get(agg, agg)}"
        out.append({"agg": agg, "field": m.get("field"), "name": name,
                    "chart": m.get("chart") if m.get("chart") in ("bar", "line") else None})
    return out


def _chart_layout_sql(db, table, fields_by_name, block, conds, query_map) -> dict:
    """图表分组布局：主分组 master/rest keys + 二级分组 top 取值。eval 与下钻共用，保证口径一致。"""
    group = block.get("group") or {}
    gkind = group.get("kind") or "field"
    metrics = _chart_metrics(block, fields_by_name)
    g2field = (block.get("group2") or {}).get("field")

    # 主分组 labels：多系列共用同一 x 轴
    if gkind == "field":
        # 字段分组：按值降序取 top_n，其余合并为"其他"；二级分组时按各组记录数排序
        top_n = int(block.get("top_n") or CHART_TOP_N_DEFAULT.get(block.get("chart_type"), 30))
        order_map = query_map("count", None) if g2field else query_map(metrics[0]["agg"], metrics[0]["field"])
        ordered_keys = sorted(order_map, key=lambda k: order_map[k], reverse=True)
        master_keys, rest_keys = ordered_keys[:top_n], ordered_keys[top_n:]
    else:
        # 日期分组：按时间升序，空值排最后
        order_map = query_map("count", None)
        master_keys = sorted(order_map, key=lambda k: (k is None, str(k or "")))
        rest_keys = []

    g2_top, g2_has_rest = [], False
    if g2field:
        g2col = table.c[g2field]
        g2_rows = db.execute(
            select(g2col.label("g2"), func.count().label("c")).select_from(table).where(*conds)
            .group_by(g2col).order_by(func.count().desc())
        ).all()
        g2_top = [r.g2 for r in g2_rows[:GROUP2_TOP_N]]
        g2_has_rest = len(g2_rows) > GROUP2_TOP_N
    return {"gkind": gkind, "metrics": metrics, "g2field": g2field,
            "master_keys": master_keys, "rest_keys": rest_keys,
            "g2_top": g2_top, "g2_has_rest": g2_has_rest}


def _eval_chart(db, table, fields_by_name, block, date_field, start, end, viewer_rules=None) -> dict:
    conds = _base_conds(table, fields_by_name, block.get("filters"), date_field, start, end, viewer_rules)
    if block.get("chart_type") == "gauge":
        # 仪表盘：单聚合值，无分组/系列/下钻
        agg, field = block.get("agg") or "count", block.get("field")
        v = db.execute(select(_agg_expr(table, agg, field)).select_from(table).where(*conds)).scalar()
        return {
            "id": block["id"], "type": "chart", "title": block.get("title") or "",
            "chart_type": "gauge", "value": _round_num(v if v is not None else 0),
            "max": float(block.get("max") or 100), "labels": [], "series": [], "values": [], "agg": agg,
        }
    group = block.get("group") or {}
    gkind, gfield = group.get("kind") or "field", group.get("field")
    gcol = table.c[gfield]
    # SQLite strftime：%W 周一为周首（跨年边界第 0 周有坑，业务周报够用）
    gexpr = _group_expr(table, gkind, gfield)
    gf = fields_by_name.get(gfield)

    def label_of(k):
        return _option_label(gf, k) if gkind == "field" else (str(k) if k is not None else "（空）")

    def query_map(agg, field, extra=None):
        """按主分组聚合 → {分组key: 值}。保留原始 key，便于多系列对齐。"""
        q = select(gexpr.label("g"), _agg_expr(table, agg, field).label("v")).select_from(table).where(*conds)
        if extra is not None:
            q = q.where(extra)
        return {r.g: (r.v or 0) for r in db.execute(q.group_by(gexpr)).all()}

    L = _chart_layout_sql(db, table, fields_by_name, block, conds, query_map)
    metrics, g2field = L["metrics"], L["g2field"]
    master_keys, rest_keys = L["master_keys"], L["rest_keys"]
    labels = [label_of(k) for k in master_keys] + (["其他"] if rest_keys else [])

    def align(mp) -> list:
        vals = [_round_num(mp.get(k, 0)) for k in master_keys]
        if rest_keys:
            vals.append(_round_num(sum(mp.get(k, 0) for k in rest_keys)))
        return vals

    if g2field:
        # 二级分组：每个取值一个系列（按记录数 top N，其余合并"其他"系列）
        g2col = table.c[g2field]
        g2f = fields_by_name.get(g2field)
        m0 = metrics[0]
        series = []
        for v in L["g2_top"]:
            cond = g2col.is_(None) if v is None else (g2col == v)
            series.append({"name": _option_label(g2f, v), "values": align(query_map(m0["agg"], m0["field"], cond))})
        if L["g2_has_rest"]:
            series.append({"name": "其他", "values": align(query_map(m0["agg"], m0["field"], _rest_cond(g2col, L["g2_top"])))})
    else:
        series = [{"name": m["name"], "values": align(query_map(m["agg"], m["field"]))} for m in metrics]

    # 组合图（柱线双轴）：系列带图形标记（bar/line），前端据此分配左右轴
    if block.get("chart_type") == "mixed":
        for s, m in zip(series, metrics):
            s["chart"] = m.get("chart") or "bar"

    # 时间分组的对比系列：环比（上期）/ 同比（去年同期）。按桶位对齐（本周一 vs 上周一…），
    # 前端渲染为虚线折线覆盖。占比显示与对比互斥（校验期已拦）
    cmp_mode = block.get("compare")
    if cmp_mode in COMPARE_MODES and gkind in ("day", "week", "month") and not g2field and start is not None:
        ps, pe = _shift_range(start, end, cmp_mode)
        cmp_conds = _base_conds(table, fields_by_name, block.get("filters"), date_field, ps, pe, viewer_rules)

        def cmp_query_map(agg, field):
            q = select(gexpr.label("g"), _agg_expr(table, agg, field).label("v")).select_from(table).where(*cmp_conds)
            return {r.g: (r.v or 0) for r in db.execute(q.group_by(gexpr)).all()}

        cmp_keys = sorted(cmp_query_map("count", None), key=lambda k: (k is None, str(k or "")))
        suffix = COMPARE_SUFFIX[cmp_mode]
        for m in metrics:
            mp = cmp_query_map(m["agg"], m["field"])
            vals = [_round_num(mp.get(k, 0)) for k in cmp_keys]
            # 与本期桶按位置对齐：对比期桶多/少时截断或补 None
            vals = vals[:len(master_keys)] + [None] * max(0, len(master_keys) - len(vals))
            series.append({"name": f"{m['name']}·{suffix}", "values": vals, "chart": "line", "compare": True})

    # 快速计算：占比（每系列 ÷ 自身合计 × 100）
    unit = None
    if block.get("quick_calc") == "pct":
        for s in series:
            if s.get("compare"):
                continue
            total = sum(v for v in s["values"] if v) or 0
            s["values"] = [round(v / total * 100, 1) if total else 0 for v in s["values"]]
        unit = "%"

    return {
        "id": block["id"], "type": "chart", "title": block.get("title") or "",
        "chart_type": block.get("chart_type"), "labels": labels,
        "series": series, "values": series[0]["values"] if series else [],
        "agg": metrics[0]["agg"], "stack": bool(block.get("stack")),
        "group2": bool(g2field), "unit": unit,
        # 图表联动用：原始分组 key（与 labels 对齐，"其他"桶为 None）+ 字段名 + 点击行为
        "keys": [dyn_engine.serialize_value(k) for k in master_keys] + ([None] if rest_keys else []),
        "group_field": gfield if gkind == "field" else None,
        "on_click": block.get("on_click") or "drill",
        # 层级钻取/报表跳转配置透传（前端渲染的是求值后的块，配置不随块返回会丢）
        "drill_down": (block.get("drill_down") or {}).get("field") or None,
        "jump_report_id": block.get("jump_report_id"),
    }


# ---------- 透视表（行维度 × 列维度交叉聚合） ----------

def _dim_keys_sql(db, table, conds, gexpr, gkind: str, top_n: int):
    """透视表单维度 key 布局：field 型按记录数降序取 top_n、其余为 rest；时间型升序、空值最后、无 rest。"""
    rows = db.execute(
        select(gexpr.label("g"), func.count().label("c")).select_from(table)
        .where(*conds).group_by(gexpr)
    ).all()
    counts = {r.g: r.c for r in rows}
    if gkind == "field":
        # 先按 key 升序打底再做计数降序稳定排序：计数并列时两引擎次序一致
        ordered = sorted(counts, key=lambda k: (k is None, str(k or "")))
        ordered = sorted(ordered, key=lambda k: counts[k], reverse=True)
        return ordered[:top_n], ordered[top_n:]
    return sorted(counts, key=lambda k: (k is None, str(k or ""))), []


def _dim_label(f: MetaField | None, gkind: str, key) -> str:
    """维度 key 的显示标签：field 型回显枚举 label，时间型原样，空值统一"（空）"。"""
    if gkind == "field":
        return _option_label(f, key)
    return str(key) if key is not None else "（空）"


def _eval_pivot(db, table, fields_by_name, block, date_field, start, end, viewer_rules=None) -> dict:
    """透视表 SQL 求值。单元格按行/列布局对齐（含"其他"桶折叠）；合计独立聚合，不受折叠影响。"""
    conds = _base_conds(table, fields_by_name, block.get("filters"), date_field, start, end, viewer_rules)
    row, col = block.get("row") or {}, block.get("col") or {}
    rkind, rfield = row.get("kind") or "field", row.get("field")
    ckind, cfield = col.get("kind") or "field", col.get("field")
    rexpr, cexpr = _group_expr(table, rkind, rfield), _group_expr(table, ckind, cfield)
    agg, field = block["agg"], block.get("field")
    agg_col = _agg_expr(table, agg, field)

    r_master, r_rest = _dim_keys_sql(db, table, conds, rexpr, rkind,
                                     int(block.get("row_top_n") or PIVOT_ROW_TOP_N[2]))
    c_master, c_rest = _dim_keys_sql(db, table, conds, cexpr, ckind,
                                     int(block.get("col_top_n") or PIVOT_COL_TOP_N[2]))
    rf, cf = fields_by_name.get(rfield), fields_by_name.get(cfield)
    row_labels = [_dim_label(rf, rkind, k) for k in r_master] + (["其他"] if r_rest else [])
    col_labels = [_dim_label(cf, ckind, k) for k in c_master] + (["其他"] if c_rest else [])

    # 单元格：一次二维聚合，"其他"桶按 key 折叠求和（count/sum 精确；avg/min/max 为近似，与图表一致）
    cell_map = {}
    q = (select(rexpr.label("r"), cexpr.label("c"), agg_col.label("v"))
         .select_from(table).where(*conds).group_by(rexpr, cexpr))
    for rr in db.execute(q).all():
        cell_map[(rr.r, rr.c)] = rr.v or 0

    def cell(rk, ck):
        return cell_map.get((rk, ck), 0)

    cells = []
    for rk in r_master:
        vals = [cell(rk, ck) for ck in c_master]
        if c_rest:
            vals.append(sum(cell(rk, ck) for ck in c_rest))
        cells.append([_round_num(v) for v in vals])
    if r_rest:
        vals = [sum(cell(rk, ck) for rk in r_rest) for ck in c_master]
        if c_rest:
            vals.append(sum(cell(rk, ck) for rk in r_rest for ck in c_rest))
        cells.append([_round_num(v) for v in vals])

    out = {
        "id": block["id"], "type": "pivot", "title": block.get("title") or "", "agg": agg,
        "row_labels": row_labels, "col_labels": col_labels, "cells": cells,
        "totals": bool(block.get("totals", True)),
    }
    if out["totals"]:
        # 合计独立聚合：行合计含并入"其他"列的记录，列合计含"其他"行，总计为基准集全量
        rmap = {r.g: (r.v or 0) for r in db.execute(
            select(rexpr.label("g"), agg_col.label("v")).select_from(table).where(*conds).group_by(rexpr)).all()}
        cmap = {r.g: (r.v or 0) for r in db.execute(
            select(cexpr.label("g"), agg_col.label("v")).select_from(table).where(*conds).group_by(cexpr)).all()}

        def rest_total(expr, master):
            v = db.execute(select(agg_col).select_from(table).where(*conds, _rest_cond(expr, master))).scalar()
            return _round_num(v if v is not None else 0)

        out["row_totals"] = [_round_num(rmap.get(k, 0)) for k in r_master] + ([rest_total(rexpr, r_master)] if r_rest else [])
        out["col_totals"] = [_round_num(cmap.get(k, 0)) for k in c_master] + ([rest_total(cexpr, c_master)] if c_rest else [])
        grand = db.execute(select(agg_col).select_from(table).where(*conds)).scalar()
        out["grand_total"] = _round_num(grand if grand is not None else 0)
    return out


def _eval_table(db, table, fields_by_name, block, date_field, start, end, viewer_rules=None,
                page: tuple | None = None) -> dict:
    conds = _base_conds(table, fields_by_name, block.get("filters"), date_field, start, end, viewer_rules)
    cols = block.get("columns") or []
    if not cols:
        # 默认全选：未配置展示列时输出全部业务字段 + 创建/更新时间（空列只显示 ID 没有使用价值）
        cols = [f.field_name for f in fields_by_name.values()] + ["created_at", "updated_at"]
    total = db.execute(select(func.count()).select_from(table).where(*conds)).scalar() or 0

    sort_by = block.get("sort_by")
    if sort_by in fields_by_name or sort_by in SYSTEM_FIELDS:
        order_col = table.c[sort_by]
        order = order_col.asc() if block.get("sort_order") == "asc" else order_col.desc()
    else:
        order = table.c.id.desc()
    sel_cols = [table.c[c] for c in cols] + [table.c.id]
    q = select(*sel_cols).select_from(table).where(*conds).order_by(order)
    # 服务端分页：前端翻页时带 (page, page_size)；不带则全量返回（兼容导出/推送/旧前端）
    if page:
        q = q.limit(page[1]).offset((page[0] - 1) * page[1])
    rows = db.execute(q).mappings().all()

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
    out = {
        "id": block["id"], "type": "table", "title": block.get("title") or "",
        "columns": [{"prop": c, "label": col_label(c)} for c in cols],
        "rows": out_rows, "total": total, "truncated": False,
    }
    if page:
        out["page"], out["page_size"] = page
    return out


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


def _run_py(db, mt, fields, tpl, date_field, start, end, label, viewer_rules=None, rules_of=None,
            cascade_rules: dict | None = None, block_pages: dict | None = None) -> dict:
    """json 引擎求值。viewer_rules 平铺作用于全部块；rules_of(block) 按块给规则（v3 数据集作用域）；
    cascade_rules(filter块id) 级联选项用的其它查看端规则；block_pages 明细表服务端分页。"""
    from . import json_store
    from .pyquery import match_filters, sort_records

    source = getattr(tpl, "source_json", None) or None
    if ds.has_source(source):
        fields, recs = ds.load_json_dataset(db, mt, fields, source)
    else:
        recs = json_store.all_dicts(db, mt.id, fields, normalized=True)
    fields_by_name = {f.field_name: f for f in fields}

    def block_rules(block) -> list:
        return rules_of(block) if rules_of else (viewer_rules or [])

    def block_time(block) -> tuple:
        """块级口径：(date_field, start, end)；df/s 为 None 表示不做时间过滤。"""
        return _block_time(block, date_field, start, end)

    def scope_recs(block, df, s, e) -> list[dict]:
        """查看端筛选 + 时间口径（不含区块自身筛选，供 ratio 分母/环比复用）。"""
        vf = {"logic": "AND", "rules": block_rules(block)}
        if df is None or s is None:
            return [r for r in recs if match_filters(r, fields_by_name, vf)]
        dfx = fields_by_name.get(df)

        def in_range(r):
            v = r.get(df)
            if v is None:
                return False  # SQL 三值逻辑：NULL 比较即排除
            try:
                if dfx is not None and dfx.data_type == "date":
                    return s.date() <= v < _end_date_exclusive(e)
                return s <= v < e
            except TypeError:
                return False

        return [r for r in recs if match_filters(r, fields_by_name, vf) and in_range(r)]

    def base_recs(block, df, s, e) -> list[dict]:
        return [r for r in scope_recs(block, df, s, e) if match_filters(r, fields_by_name, block.get("filters") or {})]

    def stat_value(block, df, s, e):
        if block["agg"] == "ratio":
            rows_all = scope_recs(block, df, s, e)
            num = len([r for r in rows_all if match_filters(r, fields_by_name, block.get("filters") or {})])
            return round(num / len(rows_all) * 100, 2) if rows_all else 0
        return _py_agg(base_recs(block, df, s, e), block["agg"], block.get("field"))

    def eval_stat(block):
        df, bs, be = block_time(block)
        v = _round_num(stat_value(block, df, bs, be))
        out = {"id": block["id"], "type": "stat", "title": block.get("title") or "", "value": v, "agg": block["agg"]}
        if block.get("compare") and bs is not None:
            ctype = block.get("compare_type") or "mom"
            ps, pe = _shift_range(bs, be, ctype)
            prev = _round_num(stat_value(block, df, ps, pe))
            out["compare"] = _compare_payload(v, prev, ctype)
        return out

    def eval_chart(block):
        rows = base_recs(block, *block_time(block))
        if block.get("chart_type") == "gauge":
            agg, field = block.get("agg") or "count", block.get("field")
            return {
                "id": block["id"], "type": "chart", "title": block.get("title") or "",
                "chart_type": "gauge", "value": _round_num(_py_agg(rows, agg, field) or 0),
                "max": float(block.get("max") or 100), "labels": [], "series": [], "values": [], "agg": agg,
            }
        group = block.get("group") or {}
        gkind, gfield = group.get("kind") or "field", group.get("field")
        gf = fields_by_name.get(gfield)
        metrics = _chart_metrics(block, fields_by_name)
        g2field = (block.get("group2") or {}).get("field")

        def bucket_key(r):
            if gkind == "field":
                return r.get(gfield)
            v = r.get(gfield)
            # Python strftime('%Y-%W') 与 SQLite strftime('%Y-%W') 同为 C 库 %W 语义（周一为周首），结果等价
            fmt = {"day": "%Y-%m-%d", "week": "%Y-%W", "month": "%Y-%m"}[gkind]
            return v.strftime(fmt) if isinstance(v, (date, datetime)) else None

        buckets: dict = {}
        for r in rows:
            buckets.setdefault(bucket_key(r), []).append(r)

        def agg_rows(rs, m):
            return _py_agg(rs, m["agg"], m["field"]) or 0

        m0 = metrics[0]
        if gkind == "field":
            top_n = int(block.get("top_n") or CHART_TOP_N_DEFAULT.get(block.get("chart_type"), 30))
            ordered = sorted(buckets, key=lambda k: len(buckets[k]) if g2field else agg_rows(buckets[k], m0),
                             reverse=True)
            master_keys, rest_keys = ordered[:top_n], ordered[top_n:]
        else:
            master_keys = sorted(buckets, key=lambda k: (k is None, str(k or "")))
            rest_keys = []
        rest_rows = [r for k in rest_keys for r in buckets[k]]

        def label_of(k):
            return _option_label(gf, k) if gkind == "field" else (str(k) if k is not None else "（空）")

        labels = [label_of(k) for k in master_keys] + (["其他"] if rest_keys else [])

        if g2field:
            g2f = fields_by_name.get(g2field)
            g2_counts: dict = {}
            for r in rows:
                k = r.get(g2field)
                g2_counts[k] = g2_counts.get(k, 0) + 1
            top_g2 = sorted(g2_counts, key=lambda k: g2_counts[k], reverse=True)[:GROUP2_TOP_N]

            def g2_filter(rs, v):
                return [r for r in rs if r.get(g2field) == v]

            series = []
            for v in top_g2:
                vals = [_round_num(agg_rows(g2_filter(buckets[k], v), m0)) for k in master_keys]
                if rest_keys:
                    vals.append(_round_num(agg_rows(g2_filter(rest_rows, v), m0)))
                series.append({"name": _option_label(g2f, v), "values": vals})
            if len(g2_counts) > GROUP2_TOP_N:
                vals = [_round_num(agg_rows([r for r in buckets[k] if r.get(g2field) not in top_g2], m0))
                        for k in master_keys]
                if rest_keys:
                    vals.append(_round_num(agg_rows([r for r in rest_rows if r.get(g2field) not in top_g2], m0)))
                series.append({"name": "其他", "values": vals})
        else:
            series = []
            for m in metrics:
                vals = [_round_num(agg_rows(buckets[k], m)) for k in master_keys]
                if rest_keys:
                    vals.append(_round_num(agg_rows(rest_rows, m)))
                series.append({"name": m["name"], "values": vals})

        # 组合图：系列带图形标记（与 SQL 路径一致）
        if block.get("chart_type") == "mixed":
            for s, m in zip(series, metrics):
                s["chart"] = m.get("chart") or "bar"

        # 时间分组对比系列（环比/同比，按桶位对齐；与 SQL 路径一致）
        cmp_mode = block.get("compare")
        df0, bs0, be0 = block_time(block)
        if cmp_mode in COMPARE_MODES and gkind in ("day", "week", "month") and not g2field and bs0 is not None:
            ps, pe = _shift_range(bs0, be0, cmp_mode)
            cmp_rows = base_recs(block, df0, ps, pe)
            cmp_buckets: dict = {}
            for r in cmp_rows:
                cmp_buckets.setdefault(bucket_key(r), []).append(r)
            cmp_keys = sorted(cmp_buckets, key=lambda k: (k is None, str(k or "")))
            suffix = COMPARE_SUFFIX[cmp_mode]
            for m in metrics:
                vals = [_round_num(agg_rows(cmp_buckets[k], m)) for k in cmp_keys]
                vals = vals[:len(master_keys)] + [None] * max(0, len(master_keys) - len(vals))
                series.append({"name": f"{m['name']}·{suffix}", "values": vals, "chart": "line", "compare": True})

        # 快速计算：占比（与 SQL 路径一致）
        unit = None
        if block.get("quick_calc") == "pct":
            for s in series:
                if s.get("compare"):
                    continue
                total = sum(v for v in s["values"] if v) or 0
                s["values"] = [round(v / total * 100, 1) if total else 0 for v in s["values"]]
            unit = "%"
        return {
            "id": block["id"], "type": "chart", "title": block.get("title") or "",
            "chart_type": block.get("chart_type"), "labels": labels,
            "series": series, "values": series[0]["values"] if series else [],
            "agg": m0["agg"], "stack": bool(block.get("stack")),
            "group2": bool(g2field), "unit": unit,
            # 图表联动用：原始分组 key（与 labels 对齐，"其他"桶为 None）+ 字段名 + 点击行为
            "keys": [dyn_engine.serialize_value(k) for k in master_keys] + ([None] if rest_keys else []),
            "group_field": gfield if gkind == "field" else None,
            "on_click": block.get("on_click") or "drill",
            # 层级钻取/报表跳转配置透传
            "drill_down": (block.get("drill_down") or {}).get("field") or None,
            "jump_report_id": block.get("jump_report_id"),
        }

    def eval_pivot(block):
        """透视表 py 求值：与 _eval_pivot 逐项对齐（"其他"桶折叠求和 + 合计独立聚合）。"""
        rows = base_recs(block, *block_time(block))
        row, col = block.get("row") or {}, block.get("col") or {}
        rkind, rfield = row.get("kind") or "field", row.get("field")
        ckind, cfield = col.get("kind") or "field", col.get("field")
        rf, cf = fields_by_name.get(rfield), fields_by_name.get(cfield)
        agg, field = block["agg"], block.get("field")

        def dim_key(r, kind, f):
            if kind == "field":
                return r.get(f)
            v = r.get(f)
            fmt = {"day": "%Y-%m-%d", "week": "%Y-%W", "month": "%Y-%m"}[kind]
            return v.strftime(fmt) if isinstance(v, (date, datetime)) else None

        buckets: dict = {}
        r_counts: dict = {}
        c_counts: dict = {}
        for r in rows:
            rk, ck = dim_key(r, rkind, rfield), dim_key(r, ckind, cfield)
            buckets.setdefault((rk, ck), []).append(r)
            r_counts[rk] = r_counts.get(rk, 0) + 1
            c_counts[ck] = c_counts.get(ck, 0) + 1

        def dim_keys(counts, kind, top_n):
            if kind == "field":
                # 与 _dim_keys_sql 一致：key 升序打底 + 计数降序稳定排序，并列时两引擎次序一致
                ordered = sorted(counts, key=lambda k: (k is None, str(k or "")))
                ordered = sorted(ordered, key=lambda k: counts[k], reverse=True)
                return ordered[:top_n], ordered[top_n:]
            return sorted(counts, key=lambda k: (k is None, str(k or ""))), []

        r_master, r_rest = dim_keys(r_counts, rkind, int(block.get("row_top_n") or PIVOT_ROW_TOP_N[2]))
        c_master, c_rest = dim_keys(c_counts, ckind, int(block.get("col_top_n") or PIVOT_COL_TOP_N[2]))
        row_labels = [_dim_label(rf, rkind, k) for k in r_master] + (["其他"] if r_rest else [])
        col_labels = [_dim_label(cf, ckind, k) for k in c_master] + (["其他"] if c_rest else [])

        def cell_val(rk, ck):
            return _py_agg(buckets.get((rk, ck), []), agg, field) or 0

        cells = []
        for rk in r_master:
            vals = [cell_val(rk, ck) for ck in c_master]
            if c_rest:
                vals.append(sum(cell_val(rk, ck) for ck in c_rest))
            cells.append([_round_num(v) for v in vals])
        if r_rest:
            vals = [sum(cell_val(rk, ck) for rk in r_rest) for ck in c_master]
            if c_rest:
                vals.append(sum(cell_val(rk, ck) for rk in r_rest for ck in c_rest))
            cells.append([_round_num(v) for v in vals])

        out = {
            "id": block["id"], "type": "pivot", "title": block.get("title") or "", "agg": agg,
            "row_labels": row_labels, "col_labels": col_labels, "cells": cells,
            "totals": bool(block.get("totals", True)),
        }
        if out["totals"]:
            r_master_set, c_master_set = set(r_master), set(c_master)

            def pick(rpred, cpred):
                return [r for (rk, ck), rs in buckets.items() if rpred(rk) and cpred(ck) for r in rs]

            def agg_of(rs):
                return _round_num(_py_agg(rs, agg, field) or 0)

            out["row_totals"] = [agg_of(pick(lambda rk, k=k: rk == k, lambda c: True)) for k in r_master]
            if r_rest:
                out["row_totals"].append(agg_of(pick(lambda rk: rk not in r_master_set, lambda c: True)))
            out["col_totals"] = [agg_of(pick(lambda r: True, lambda ck, k=k: ck == k)) for k in c_master]
            if c_rest:
                out["col_totals"].append(agg_of(pick(lambda r: True, lambda ck: ck not in c_master_set)))
            out["grand_total"] = agg_of(rows)
        return out

    def eval_table(block):
        rows = base_recs(block, *block_time(block))
        cols = block.get("columns") or []
        if not cols:
            # 默认全选：未配置展示列时输出全部业务字段 + 创建/更新时间
            cols = [f.field_name for f in fields_by_name.values()] + ["created_at", "updated_at"]
        total = len(rows)
        sort_by = block.get("sort_by")
        rows = sort_records(rows, sort_by if sort_by in (set(fields_by_name) | SYSTEM_FIELDS) else None,
                            block.get("sort_order"), fields_by_name)
        # 服务端分页（与 SQL 路径一致：不带 page 时全量返回）
        pg = (block_pages or {}).get(block["id"])

        def col_label(c):
            f = fields_by_name.get(c)
            return f.label if f else {"id": "ID", "created_at": "创建时间", "updated_at": "更新时间"}[c]

        select_fields = {c: fields_by_name[c] for c in cols
                         if c in fields_by_name and fields_by_name[c].widget == "select"}
        out_rows = []
        for r in (rows[(pg[0] - 1) * pg[1]:pg[0] * pg[1]] if pg else rows):
            d = {c: dyn_engine.serialize_value(r.get(c)) for c in cols}
            d["id"] = r["id"]
            for c, f in select_fields.items():
                if d.get(c) is not None:
                    d[c] = _option_label(f, d.get(c))
            out_rows.append(d)
        out = {
            "id": block["id"], "type": "table", "title": block.get("title") or "",
            "columns": [{"prop": c, "label": col_label(c)} for c in cols],
            "rows": out_rows, "total": total, "truncated": False,
        }
        if pg:
            out["page"], out["page_size"] = pg
        return out

    def eval_filter(block):
        """筛选组件块 + 级联可选项：select 型按「其它查看端规则 + 时间口径」过滤可选值。"""
        out = _filter_block_out(block, fields_by_name)
        rules = (cascade_rules or {}).get(block["id"])
        f = fields_by_name.get(block.get("field") or "")
        if rules is not None and f is not None and f.widget == "select":
            df, s, e = block_time(block)
            vf = {"logic": "AND", "rules": rules}
            if df is None or s is None:
                rows = [r for r in recs if match_filters(r, fields_by_name, vf)]
            else:
                dfx = fields_by_name.get(df)
                end_ex = _end_date_exclusive(e)

                def in_range(r):
                    v = r.get(df)
                    if v is None:
                        return False
                    try:
                        if dfx is not None and dfx.data_type == "date":
                            return s.date() <= v < end_ex
                        return s <= v < e
                    except TypeError:
                        return False

                rows = [r for r in recs if match_filters(r, fields_by_name, vf) and in_range(r)]
            present = {r.get(block["field"]) for r in rows}
            out["available"] = _filter_available(f, present)
        return out

    blocks = tpl.blocks_json or []
    results_by_id, stat_values = {}, {}
    for b in blocks:
        t = b.get("type")
        if t == "filter":
            results_by_id[b["id"]] = eval_filter(b)
        elif t == "stat":
            r = eval_stat(b)
            stat_values[b["id"]] = r["value"]
            results_by_id[b["id"]] = r
        elif t == "chart":
            results_by_id[b["id"]] = eval_chart(b)
        elif t == "pivot":
            results_by_id[b["id"]] = eval_pivot(b)
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
        "layout": getattr(tpl, "layout_json", None),   # getattr 兜底：数据问答用 SimpleNamespace 伪模板
    }


def _filter_block_out(block: dict, fields_by_name: dict) -> dict:
    """筛选组件块：不参与聚合，原样透传字段元数据给前端渲染控件。"""
    f = fields_by_name.get(block.get("field") or "")
    return {
        "id": block["id"], "type": "filter",
        "title": block.get("title") or (f.label if f else "") or "筛选",
        "field": block.get("field"),
        "data_type": getattr(f, "data_type", None), "widget": getattr(f, "widget", None),
        "options": getattr(f, "options", None) or {},
    }


def _filter_available(f, present: set) -> list | None:
    """级联后的可选项：select 型筛选按元数据顺序过滤出当前可选值（保持 {value,label} 形态）。"""
    opts = (getattr(f, "options", None) or {}).get("options") or []
    if not opts:
        return None
    return [o for o in opts if (o.get("value") if isinstance(o, dict) else o) in present]


def _block_range_spec(block: dict) -> dict | None:
    """块级独立口径：v3 range_mode/range_start/range_end，或旧 range_override。"""
    ov = block.get("range_override") or {}
    if ov.get("mode"):
        return {k: v for k, v in ov.items() if v is not None}
    if block.get("range_mode"):
        spec = {"mode": block["range_mode"]}
        if block.get("range_start"):
            spec["start"] = block["range_start"]
        if block.get("range_end"):
            spec["end"] = block["range_end"]
        return spec
    return None


def _block_time(block: dict, default_df: str | None, g_start, g_end) -> tuple:
    """块的 (date_field, start, end)。df 或 start 为 None 表示该块不做时间过滤。"""
    df = block.get("date_field", default_df)
    spec = _block_range_spec(block)
    if spec:
        try:
            s, e, _ = resolve_time_range({"date_field": df or "created_at", **spec})
        except ReportError as e:
            raise HTTPException(400, str(e))
        return df, s, e
    if df is None:
        return None, None, None
    return df, g_start, g_end


def _range_badge(block: dict, df: str | None) -> str | None:
    """块口径徽标（查看端展示）：不随时间筛选 / 独立口径标签；跟随全局返回 None。"""
    if df is None:
        return "不随时间筛选"
    spec = _block_range_spec(block)
    if not spec:
        return None
    try:
        _, _, blabel = resolve_time_range({"date_field": df, **spec})
    except ReportError:
        return None
    return blabel


def _tagged_viewer_rules(db: Session, tpl, datasets: list, viewer_filters: dict | None, links: list | None) -> list:
    """查看端规则打数据集标签：filter 块声明（含作用域 target）+ 旧 filters_json（归 _default）+ 图表联动。
    返回 [{field, op, value, _dataset, _targets}]，_targets=None 表示作用于同数据集全部区块。"""
    default_did = datasets[0]["id"] if datasets else "_default"
    declared: dict[tuple, list | None] = {}
    for b in (tpl.blocks_json or []):
        if b.get("type") == "filter" and b.get("field"):
            did = b.get("dataset_id") or default_did
            tgt = b.get("target") or {}
            declared[(did, b["field"])] = list(tgt.get("block_ids") or []) if tgt.get("mode") == "blocks" else None
    legacy = not getattr(tpl, "datasets_json", None)
    if legacy:
        for fn in (tpl.filters_json or []):
            declared[(default_did, fn)] = None

    fields_cache: dict[str, dict] = {}

    def fbn_of(did: str) -> dict:
        if did not in fields_cache:
            d = next((x for x in datasets if x["id"] == did), None)
            if d is None:
                fields_cache[did] = {}
            else:
                _, base_fields = dyn_engine.load_meta(db, d["base_table_id"])
                fl = ds.dataset_fields(db, base_fields, ds.dataset_source(d))
                fields_cache[did] = {f.field_name: f for f in fl}
        return fields_cache[did]

    tagged: list = []
    for r in (viewer_filters or {}).get("rules") or []:
        name = r.get("field")
        did = r.get("dataset")
        if did is None:
            matches = [k for k in declared if k[1] == name]
            if len(matches) != 1:
                raise HTTPException(400, f"该字段未开放查看端筛选：{name}")
            did = matches[0][0]
        if (did, name) not in declared:
            raise HTTPException(400, f"该字段未开放查看端筛选：{name}")
        if r.get("op") not in dyn_engine.FILTER_OPS:
            raise HTTPException(400, f"不支持的筛选操作符：{r.get('op')}")
        if not dyn_engine.rule_value_ok(fbn_of(did).get(name), r.get("op"), r.get("value")):
            raise HTTPException(400, f"筛选值无效（{name}）")
        tagged.append({**r, "_dataset": did, "_targets": declared[(did, name)]})

    # 图表联动/报表间跳转：field 优先是某图表的字段型主分组（图表点击联动）；
    # 否则只要是某数据集的字段也接受（报表间跳转带值过滤，目标报表可能没有对应分组图），
    # 数据集取首个包含该字段的数据集（联动恒作用于同数据集区块）
    group_map: dict[str, str] = {}
    for b in (tpl.blocks_json or []):
        if b.get("type") == "chart" and ((b.get("group") or {}).get("kind") or "field") == "field":
            gf = (b.get("group") or {}).get("field")
            if gf:
                group_map.setdefault(gf, b.get("dataset_id") or default_did)
    for l in (links or [])[:10]:
        name = l.get("field")
        did = group_map.get(name)
        if did is None:
            did = next((d["id"] for d in datasets if name in fbn_of(d["id"])), None)
        if did is None:
            raise HTTPException(400, f"联动/跳转的字段在报表数据集中不存在：{name}")
        value = l.get("value")
        if value is None:
            continue  # 空值桶不联动
        if not dyn_engine.rule_value_ok(fbn_of(did).get(name), "eq", value):
            raise HTTPException(400, f"联动值无效（{name}）")
        tagged.append({"field": name, "op": "eq", "value": value, "_dataset": did, "_targets": None})
    return tagged


def run_template(db: Session, tpl: ReportTemplate, range_override: dict | None = None,
                 viewer_filters: dict | None = None, links: list | None = None,
                 block_pages: dict | None = None, block_overrides: dict | None = None,
                 viewer=None) -> dict:
    """执行报表模板，返回结构化结果（前端渲染 / 导出共用）。
    v3：区块经 dataset_id 各自绑定数据集（旧模板运行期合成 _default），全局口径逐块套用各自的 date_field。
    block_pages：{块id: [page, page_size]}，明细表服务端分页；
    block_overrides：{块id: {group/row/col/filters}}，层级钻取/透视表行列互换的临时覆盖（不落库）。"""
    datasets = ds.template_datasets(tpl)
    ds_by_id = {d["id"]: d for d in datasets}
    default_did = datasets[0]["id"] if datasets else "_default"
    rng = dict(tpl.range_json or {})
    if range_override:
        rng.update({k: v for k, v in range_override.items() if v is not None})
    try:
        g_start, g_end, label = resolve_time_range(rng)
    except ReportError as e:
        raise HTTPException(400, str(e))
    legacy_df = rng.get("date_field") or "created_at"

    def did_of(block) -> str:
        return block.get("dataset_id") or default_did

    # 查看端规则：带数据集标签 + 作用域，逐块匹配
    tagged = _tagged_viewer_rules(db, tpl, datasets, viewer_filters, links)
    # P1 数据范围：viewer 的角色 scope 物化为 owner_id 规则，逐数据集追加
    # （必须在 _tagged_viewer_rules 之后 append——那里的"未开放筛选"校验不认 owner_id）
    if viewer is not None:
        from . import scope as scope_mod
        for d in datasets:
            mt, _ = dyn_engine.load_meta(db, d["base_table_id"])
            rule = scope_mod.scope_rule(db, mt, viewer)
            if rule:
                tagged.append({**rule, "_dataset": d["id"], "_targets": None})
    rules_by_block: dict[str, list] = {}
    for b in (tpl.blocks_json or []):
        if b.get("type") in ("text", "filter"):
            continue
        bid, bd = b.get("id"), did_of(b)
        for r in tagged:
            if r["_dataset"] != bd:
                continue
            targets = r.get("_targets")
            if targets and bid not in targets:
                continue
            rules_by_block.setdefault(bid, []).append({k: v for k, v in r.items() if not k.startswith("_")})

    def rules_of(block) -> list:
        return rules_by_block.get(block.get("id"), [])

    # 筛选块级联：除本字段外的其它查看端规则，用于收缩该筛选块的可选项
    cascade_rules: dict[str, list] = {}
    for b in (tpl.blocks_json or []):
        if b.get("type") == "filter" and b.get("field"):
            bd = did_of(b)
            cascade_rules[b["id"]] = [
                {k: v for k, v in r.items() if not k.startswith("_")}
                for r in tagged if r["_dataset"] == bd and r["field"] != b["field"]
            ]

    # 明细表服务端分页参数（钳制范围，防滥用）
    def page_of(bid: str) -> tuple | None:
        pg = (block_pages or {}).get(bid)
        if not pg:
            return None
        try:
            p, s = int(pg.get("page") or 1), int(pg.get("page_size") or 50)
        except (TypeError, ValueError, AttributeError):
            return None
        return (max(p, 1), min(max(s, 1), 200))

    # 区块临时覆盖（层级钻取/透视表互换/明细表点列头排序）：仅放行白名单键，逐块校验分组/筛选字段存在
    OVERRIDE_KEYS = {"group", "row", "col", "filters", "sort_by", "sort_order"}
    overridden: set[str] = set()

    # 数据集解析缓存：同 dataset 的区块共享子查询/记录集
    meta_cache: dict = {}

    def meta_of(did: str):
        if did not in meta_cache:
            d = ds_by_id.get(did)
            if d is None:
                raise HTTPException(400, f"区块引用的数据集不存在：{did}")
            mt, base_fields = dyn_engine.load_meta(db, d["base_table_id"])
            meta_cache[did] = (d, mt, base_fields)
        return meta_cache[did]

    sql_cache: dict = {}

    def resolve_sql(did: str):
        if did not in sql_cache:
            d, mt, _ = meta_of(did)
            sql_cache[did] = ds.build_sql_dataset(db, mt, ds.dataset_source(d))
        return sql_cache[did]

    blocks = tpl.blocks_json or []
    if block_overrides:
        applied = []
        for b in blocks:
            ov = block_overrides.get(b.get("id"))
            if isinstance(ov, dict):
                ov = {k: v for k, v in ov.items() if k in OVERRIDE_KEYS}
                if ov:
                    b = {**b, **ov}
                    overridden.add(b["id"])
            applied.append(b)
        blocks = applied
    results_by_id, stat_values = {}, {}
    json_groups: dict[str, list] = {}   # did -> blocks（json 引擎按数据集分组批处理）

    for b in blocks:
        t = b.get("type")
        if t == "text":
            continue
        did = did_of(b)
        d, mt, _ = meta_of(did)
        if mt.storage_mode == "json":
            json_groups.setdefault(did, []).append(b)
            continue
        table, fields = resolve_sql(did)
        fields_by_name = {f.field_name: f for f in fields}
        if b["id"] in overridden:
            # 临时覆盖的块：校验分组维度/筛选字段合法（覆盖来自前端交互，不落库不信任）
            if b.get("type") == "chart":
                _check_group_dim(fields_by_name, b.get("group"))
            elif b.get("type") == "pivot":
                _check_group_dim(fields_by_name, b.get("row"), "行")
                _check_group_dim(fields_by_name, b.get("col"), "列")
            elif b.get("type") == "table":
                sb = b.get("sort_by")
                if sb and sb not in fields_by_name and sb not in SYSTEM_FIELDS:
                    raise HTTPException(400, f"明细表排序字段不存在：{sb}")
                if b.get("sort_order") not in (None, "asc", "desc"):
                    raise HTTPException(400, "排序方向只能是 asc/desc")
            _validate_filters(fields_by_name, b.get("filters"))
        df, bs, be = _block_time(b, legacy_df, g_start, g_end)
        vrules = rules_of(b)
        if t == "filter":
            out = _filter_block_out(b, fields_by_name)
            out["dataset_id"], out["target"] = did, b.get("target")
            # 级联可选项：select 型筛选按「其它查看端规则 + 时间口径」收缩可选值
            f = fields_by_name.get(b.get("field") or "")
            if f is not None and f.widget == "select" and b["id"] in cascade_rules:
                conds = _base_conds(table, fields_by_name, None, df, bs, be, cascade_rules[b["id"]] or None)
                present = {r[0] for r in db.execute(
                    select(table.c[b["field"]]).select_from(table).where(*conds).distinct().limit(500)
                ).all()}
                out["available"] = _filter_available(f, present)
            results_by_id[b["id"]] = out
        elif t == "stat":
            r = _eval_stat(db, table, fields_by_name, b, df, bs, be, vrules)
            stat_values[b["id"]] = r["value"]
            results_by_id[b["id"]] = r
        elif t == "chart":
            results_by_id[b["id"]] = _eval_chart(db, table, fields_by_name, b, df, bs, be, vrules)
        elif t == "pivot":
            results_by_id[b["id"]] = _eval_pivot(db, table, fields_by_name, b, df, bs, be, vrules)
        elif t == "table":
            results_by_id[b["id"]] = _eval_table(db, table, fields_by_name, b, df, bs, be, vrules,
                                                 page=page_of(b["id"]))
        badge = _range_badge(b, df)
        if badge and b["id"] in results_by_id:
            results_by_id[b["id"]]["range_badge"] = badge

    # json 引擎：按数据集分组走 _run_py 批处理（同一数据集只加载一次记录）
    for did, group in json_groups.items():
        d, mt, base_fields = meta_of(did)
        # 临时覆盖的块（json 路径）：同样先校验分组/筛选字段
        if overridden:
            fields_by_name_j = {f.field_name: f for f in ds.dataset_fields(db, base_fields, ds.dataset_source(d))}
            for b in group:
                if b["id"] in overridden:
                    if b.get("type") == "chart":
                        _check_group_dim(fields_by_name_j, b.get("group"))
                    elif b.get("type") == "pivot":
                        _check_group_dim(fields_by_name_j, b.get("row"), "行")
                        _check_group_dim(fields_by_name_j, b.get("col"), "列")
                    elif b.get("type") == "table":
                        sb = b.get("sort_by")
                        if sb and sb not in fields_by_name_j and sb not in SYSTEM_FIELDS:
                            raise HTTPException(400, f"明细表排序字段不存在：{sb}")
                        if b.get("sort_order") not in (None, "asc", "desc"):
                            raise HTTPException(400, "排序方向只能是 asc/desc")
                    _validate_filters(fields_by_name_j, b.get("filters"))
        proxy = SimpleNamespace(
            id=tpl.id, name=tpl.name, blocks_json=group,
            source_json=ds.dataset_source(d), layout_json=None, filters_json=[],
        )
        sub = _run_py(db, mt, base_fields, proxy, legacy_df, g_start, g_end, label, rules_of=rules_of,
                      cascade_rules=cascade_rules,
                      block_pages={b["id"]: page_of(b["id"]) for b in group if page_of(b["id"])})
        by_id = {x.get("id"): x for x in group}
        for sb in sub["blocks"]:
            if sb.get("type") == "stat":
                stat_values[sb["id"]] = sb["value"]
            if sb.get("type") == "filter":
                sb["dataset_id"] = did
                sb["target"] = by_id.get(sb["id"], {}).get("target")
            else:
                orig = by_id.get(sb["id"], {})
                badge = _range_badge(orig, orig.get("date_field", legacy_df))
                if badge:
                    sb["range_badge"] = badge
            results_by_id[sb["id"]] = sb

    context = {"range_label": label, "start": f"{g_start:%Y-%m-%d}", "end": f"{g_end:%Y-%m-%d}", **stat_values}
    for b in blocks:
        if b.get("type") == "text":
            results_by_id[b["id"]] = _eval_text(b, context)
    blocks_out = [results_by_id[b["id"]] for b in blocks if b.get("id") in results_by_id]

    return {
        "template_id": tpl.id, "name": tpl.name, "table_label": meta_of(default_did)[1].label if datasets else "",
        "range": {"start": f"{g_start:%Y-%m-%d}", "end": f"{g_end:%Y-%m-%d}", "label": label},
        "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "blocks": blocks_out,
        "layout": getattr(tpl, "layout_json", None),   # getattr 兜底：数据问答用 SimpleNamespace 伪模板
    }


# ---------- 图表下钻 ----------

DRILL_LIMIT = 200


def _drill_columns(fields: list) -> tuple[list, dict]:
    """下钻明细列：全部业务字段 + 创建时间。返回 (columns, select字段映射)。"""
    fields_by_name = {f.field_name: f for f in fields}
    cols = [f.field_name for f in fields]
    columns = [{"prop": c, "label": fields_by_name[c].label} for c in cols]
    columns.append({"prop": "created_at", "label": "创建时间"})
    select_fields = {c: fields_by_name[c] for c in cols if fields_by_name[c].widget == "select"}
    return columns, select_fields


def _apply_dim_index(conds: list, expr, master_keys: list, rest_keys: list, index: int | None, axis: str) -> None:
    """按维度下标追加筛选条件（下标与 labels 对齐，含末尾"其他"桶）；index 为 None 时不约束（透视表合计行/列）。"""
    if index is None:
        return
    if index < 0 or index >= len(master_keys) + (1 if rest_keys else 0):
        raise HTTPException(400, f"{axis}序号无效")
    if index < len(master_keys):
        k = master_keys[index]
        conds.append(expr.is_(None) if k is None else expr == k)
    else:
        conds.append(_rest_cond(expr, master_keys))


def _drill_rows_sql(db, table, fields, conds) -> dict:
    """下钻明细查询尾部：计数 + id 倒序取行（上限 DRILL_LIMIT）+ 枚举值回显 label。"""
    columns, select_fields = _drill_columns(fields)
    cols = [f.field_name for f in fields]
    total = db.execute(select(func.count()).select_from(table).where(*conds)).scalar() or 0
    sel_cols = [table.c[c] for c in cols] + [table.c.id, table.c.created_at]
    rows = db.execute(
        select(*sel_cols).select_from(table).where(*conds).order_by(table.c.id.desc()).limit(DRILL_LIMIT)
    ).mappings().all()
    out_rows = []
    for r in rows:
        d = dyn_engine.row_to_dict(r)
        for c, f in select_fields.items():
            d[c] = _option_label(f, d.get(c)) if d.get(c) is not None else d.get(c)
        out_rows.append(d)
    return {"columns": columns, "rows": out_rows, "total": total, "truncated": total > DRILL_LIMIT}


def _drill_sql(db, table, fields, block, date_field, start, end, viewer_rules, group_index, series_index) -> dict:
    fields_by_name = {f.field_name: f for f in fields}
    conds = _base_conds(table, fields_by_name, block.get("filters"), date_field, start, end, viewer_rules)
    group = block.get("group") or {}
    gkind, gfield = group.get("kind") or "field", group.get("field")
    gexpr = _group_expr(table, gkind, gfield)

    def query_map(agg, field, extra=None):
        q = select(gexpr.label("g"), _agg_expr(table, agg, field).label("v")).select_from(table).where(*conds)
        if extra is not None:
            q = q.where(extra)
        return {r.g: (r.v or 0) for r in db.execute(q.group_by(gexpr)).all()}

    L = _chart_layout_sql(db, table, fields_by_name, block, conds, query_map)

    # 主分组条件：序号 = labels 下标（含末尾"其他"桶）
    _apply_dim_index(conds, gexpr, L["master_keys"], L["rest_keys"], group_index, "分组")

    # 二级分组条件：系列序号 = series 下标（含末尾"其他"系列）；多指标系列的指标不影响记录集
    if L["g2field"] and series_index is not None:
        g2col = table.c[L["g2field"]]
        _apply_dim_index(conds, g2col, L["g2_top"], ["其他"] if L["g2_has_rest"] else [], series_index, "系列")

    return _drill_rows_sql(db, table, fields, conds)


def _drill_pivot_sql(db, table, fields, block, date_field, start, end, viewer_rules, group_index, series_index) -> dict:
    """透视表下钻：group_index=行下标、series_index=列下标（与 row_labels/col_labels 对齐），None 表示该维度不约束。"""
    fields_by_name = {f.field_name: f for f in fields}
    conds = _base_conds(table, fields_by_name, block.get("filters"), date_field, start, end, viewer_rules)
    row, col = block.get("row") or {}, block.get("col") or {}
    rkind, rfield = row.get("kind") or "field", row.get("field")
    ckind, cfield = col.get("kind") or "field", col.get("field")
    rexpr, cexpr = _group_expr(table, rkind, rfield), _group_expr(table, ckind, cfield)
    r_master, r_rest = _dim_keys_sql(db, table, conds, rexpr, rkind,
                                     int(block.get("row_top_n") or PIVOT_ROW_TOP_N[2]))
    c_master, c_rest = _dim_keys_sql(db, table, conds, cexpr, ckind,
                                     int(block.get("col_top_n") or PIVOT_COL_TOP_N[2]))
    _apply_dim_index(conds, rexpr, r_master, r_rest, group_index, "行")
    _apply_dim_index(conds, cexpr, c_master, c_rest, series_index, "列")
    return _drill_rows_sql(db, table, fields, conds)


def _drill_rows_py(fields, rows: list) -> dict:
    """下钻明细尾部（py 路径）：id 倒序、上限 DRILL_LIMIT、枚举值回显 label。"""
    columns, select_fields = _drill_columns(fields)
    cols = [f.field_name for f in fields]
    total = len(rows)
    rows = sorted(rows, key=lambda r: r.get("id") or 0, reverse=True)[:DRILL_LIMIT]
    out_rows = []
    for r in rows:
        d = {c: dyn_engine.serialize_value(r.get(c)) for c in cols}
        d["id"] = r["id"]
        d["created_at"] = dyn_engine.serialize_value(r.get("created_at"))
        for c, f in select_fields.items():
            if d.get(c) is not None:
                d[c] = _option_label(f, d.get(c))
        out_rows.append(d)
    return {"columns": columns, "rows": out_rows, "total": total, "truncated": total > DRILL_LIMIT}


def _drill_base_py(db, mt, fields, block, date_field, start, end, viewer_rules, source=None) -> tuple[list, dict, list]:
    """py 路径下钻公共前置：口径 + 查看端筛选（恒 AND）+ 区块筛选后的记录集。
    返回 (数据集字段, fields_by_name, 记录集)。"""
    from . import json_store
    from .pyquery import match_filters

    if ds.has_source(source):
        fields, recs = ds.load_json_dataset(db, mt, fields, source)
    else:
        recs = json_store.all_dicts(db, mt.id, fields, normalized=True)
    fields_by_name = {f.field_name: f for f in fields}
    viewer_filters = {"logic": "AND", "rules": viewer_rules or []}
    date_f = fields_by_name.get(date_field)

    def in_range(r):
        if date_field is None or start is None:
            return True   # date_field=None 的块不做时间过滤
        v = r.get(date_field)
        if v is None:
            return False  # SQL 三值逻辑：NULL 比较即排除
        try:
            if date_f is not None and date_f.data_type == "date":
                return start.date() <= v < end.date()
            return start <= v < end
        except TypeError:
            return False

    rows = [r for r in recs if match_filters(r, fields_by_name, viewer_filters) and in_range(r)]
    rows = [r for r in rows if match_filters(r, fields_by_name, block.get("filters") or {})]
    return fields, fields_by_name, rows


def _drill_py(db, mt, fields, block, date_field, start, end, viewer_rules, group_index, series_index, source=None) -> dict:
    fields, fields_by_name, rows = _drill_base_py(db, mt, fields, block, date_field, start, end, viewer_rules, source)

    group = block.get("group") or {}
    gkind, gfield = group.get("kind") or "field", group.get("field")
    metrics = _chart_metrics(block, fields_by_name)
    g2field = (block.get("group2") or {}).get("field")

    def bucket_key(r):
        if gkind == "field":
            return r.get(gfield)
        v = r.get(gfield)
        fmt = {"day": "%Y-%m-%d", "week": "%Y-%W", "month": "%Y-%m"}[gkind]
        return v.strftime(fmt) if isinstance(v, (date, datetime)) else None

    buckets: dict = {}
    for r in rows:
        buckets.setdefault(bucket_key(r), []).append(r)

    if gkind == "field":
        top_n = int(block.get("top_n") or CHART_TOP_N_DEFAULT.get(block.get("chart_type"), 30))
        ordered = sorted(buckets, key=lambda k: len(buckets[k]) if g2field
                         else (_py_agg(buckets[k], metrics[0]["agg"], metrics[0]["field"]) or 0), reverse=True)
        master_keys, rest_keys = ordered[:top_n], ordered[top_n:]
    else:
        master_keys = sorted(buckets, key=lambda k: (k is None, str(k or "")))
        rest_keys = []

    # 二级分组布局要在主分组过滤之前算（与 SQL 路径一致）：系列序号对应全量口径下的 top 取值
    g2_counts: dict = {}
    if g2field:
        for r in rows:
            k = r.get(g2field)
            g2_counts[k] = g2_counts.get(k, 0) + 1

    if group_index < 0 or group_index >= len(master_keys) + (1 if rest_keys else 0):
        raise HTTPException(400, "分组序号无效")
    if group_index < len(master_keys):
        k = master_keys[group_index]
        rows = [r for r in rows if bucket_key(r) == k]
    else:
        rows = [r for r in rows if bucket_key(r) not in set(master_keys)]

    if g2field and series_index is not None:
        top_g2 = sorted(g2_counts, key=lambda k: g2_counts[k], reverse=True)[:GROUP2_TOP_N]
        if series_index < 0 or series_index >= len(top_g2) + (1 if len(g2_counts) > GROUP2_TOP_N else 0):
            raise HTTPException(400, "系列序号无效")
        if series_index < len(top_g2):
            v = top_g2[series_index]
            rows = [r for r in rows if r.get(g2field) == v]
        else:
            rows = [r for r in rows if r.get(g2field) not in set(top_g2)]

    return _drill_rows_py(fields, rows)


def _drill_pivot_py(db, mt, fields, block, date_field, start, end, viewer_rules, group_index, series_index, source=None) -> dict:
    """透视表下钻（py 路径）：布局与 _drill_pivot_sql 一致；行/列下标为 None 表示该维度不约束。"""
    fields, _fields_by_name, rows = _drill_base_py(db, mt, fields, block, date_field, start, end, viewer_rules, source)

    row, col = block.get("row") or {}, block.get("col") or {}
    rkind, rfield = row.get("kind") or "field", row.get("field")
    ckind, cfield = col.get("kind") or "field", col.get("field")

    def dim_key(r, kind, f):
        if kind == "field":
            return r.get(f)
        v = r.get(f)
        fmt = {"day": "%Y-%m-%d", "week": "%Y-%W", "month": "%Y-%m"}[kind]
        return v.strftime(fmt) if isinstance(v, (date, datetime)) else None

    r_counts: dict = {}
    c_counts: dict = {}
    for r in rows:
        rk, ck = dim_key(r, rkind, rfield), dim_key(r, ckind, cfield)
        r_counts[rk] = r_counts.get(rk, 0) + 1
        c_counts[ck] = c_counts.get(ck, 0) + 1

    def dim_keys(counts, kind, top_n):
        if kind == "field":
            # 与 _dim_keys_sql 一致：key 升序打底 + 计数降序稳定排序，并列时两引擎次序一致
            ordered = sorted(counts, key=lambda k: (k is None, str(k or "")))
            ordered = sorted(ordered, key=lambda k: counts[k], reverse=True)
            return ordered[:top_n], ordered[top_n:]
        return sorted(counts, key=lambda k: (k is None, str(k or ""))), []

    r_master, r_rest = dim_keys(r_counts, rkind, int(block.get("row_top_n") or PIVOT_ROW_TOP_N[2]))
    c_master, c_rest = dim_keys(c_counts, ckind, int(block.get("col_top_n") or PIVOT_COL_TOP_N[2]))

    def apply_py(cur_rows, master, rest, index, kind, field, axis):
        if index is None:
            return cur_rows
        if index < 0 or index >= len(master) + (1 if rest else 0):
            raise HTTPException(400, f"{axis}序号无效")
        if index < len(master):
            k = master[index]
            return [r for r in cur_rows if dim_key(r, kind, field) == k]
        mset = set(master)
        return [r for r in cur_rows if dim_key(r, kind, field) not in mset]

    rows = apply_py(rows, r_master, r_rest, group_index, rkind, rfield, "行")
    rows = apply_py(rows, c_master, c_rest, series_index, ckind, cfield, "列")
    return _drill_rows_py(fields, rows)


def drill_chart(db: Session, tpl: ReportTemplate, block_id: str, group_index: int | None, series_index: int | None = None,
                range_override: dict | None = None, viewer_filters: dict | None = None, links: list | None = None,
                viewer=None) -> dict:
    """图表/透视表下钻：chart 按分组/系列序号（group_index 必填），pivot 按行/列序号（可为 None 表示合计行/列）。
    沿用图表的完整口径（块自身数据集、块级口径、查看端筛选与联动的作用域匹配）。"""
    datasets = ds.template_datasets(tpl)
    ds_by_id = {d["id"]: d for d in datasets}
    default_did = datasets[0]["id"] if datasets else "_default"
    block = next((b for b in (tpl.blocks_json or []) if b.get("id") == block_id), None)
    if not block or block.get("type") not in ("chart", "pivot"):
        raise HTTPException(400, "图表/透视表区块不存在")
    if block["type"] == "chart" and group_index is None:
        raise HTTPException(400, "缺少有效的 group_index")
    rng = dict(tpl.range_json or {})
    if range_override:
        rng.update({k: v for k, v in range_override.items() if v is not None})
    try:
        g_start, g_end, _label = resolve_time_range(rng)
    except ReportError as e:
        raise HTTPException(400, str(e))
    legacy_df = rng.get("date_field") or "created_at"
    df, start, end = _block_time(block, legacy_df, g_start, g_end)

    did = block.get("dataset_id") or default_did
    tagged = _tagged_viewer_rules(db, tpl, datasets, viewer_filters, links)
    if viewer is not None:   # P1 数据范围（同 run_template）
        from . import scope as scope_mod
        for d in datasets:
            mt, _ = dyn_engine.load_meta(db, d["base_table_id"])
            rule = scope_mod.scope_rule(db, mt, viewer)
            if rule:
                tagged.append({**rule, "_dataset": d["id"], "_targets": None})
    vrules = [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in tagged
        if r["_dataset"] == did and (not r.get("_targets") or block_id in r["_targets"])
    ]
    d = ds_by_id.get(did)
    if d is None:
        raise HTTPException(400, f"区块引用的数据集不存在：{did}")
    src = ds.dataset_source(d)
    mt, base_fields = dyn_engine.load_meta(db, d["base_table_id"])

    is_pivot = block["type"] == "pivot"
    if mt.storage_mode == "json":
        fn = _drill_pivot_py if is_pivot else _drill_py
        return fn(db, mt, base_fields, block, df, start, end, vrules, group_index, series_index, source=src)
    table, fields = ds.build_sql_dataset(db, mt, src)
    fn = _drill_pivot_sql if is_pivot else _drill_sql
    return fn(db, table, fields, block, df, start, end, vrules, group_index, series_index)


# ---------- 定时推送 ----------

def render_email_html(result: dict) -> str:
    """邮件正文：纯 HTML（邮件客户端禁 JS），stat 大数字 + 数据表，不出图。
    有布局时按页签分节（统计卡就地成组），无布局保持统计卡置顶的旧版式。"""
    import html as html_mod

    def esc(v):
        return html_mod.escape("" if v is None else str(v))

    def stat_table(stats) -> str:
        cells = "".join(
            f'<td style="padding:12px 20px;background:#f5f7fa;border-radius:8px;text-align:center">'
            f'<div style="font-size:12px;color:#888">{esc(b["title"])}</div>'
            f'<div style="font-size:24px;font-weight:600;color:#303133">{esc(b["value"])}</div></td>'
            f'<td style="width:12px"></td>'
            for b in stats
        )
        return f'<table cellpadding="0" cellspacing="0"><tr>{cells}</tr></table>'

    def block_html(b) -> str:
        if b["type"] == "filter":
            return ""
        if b["type"] == "chart" and b.get("chart_type") == "gauge":
            return (f'<h3 style="margin:20px 0 8px">{esc(b["title"])}</h3>'
                    f'<p style="font-size:24px;font-weight:600;color:#303133;margin:0">{esc(b.get("value"))}</p>')
        if b["type"] == "chart":
            series = b.get("series") or [{"name": "值", "values": b.get("values") or []}]
            if len(series) > 1:
                # 多系列：分组 + 每系列一列
                head = f'<tr><th style="padding:4px 12px;border:1px solid #e4e7ed;background:#f5f7fa">分组</th>' + "".join(
                    f'<th style="padding:4px 12px;border:1px solid #e4e7ed;background:#f5f7fa;text-align:right">{esc(s["name"])}</th>'
                    for s in series) + "</tr>"
                rows = "".join(
                    f'<tr><td style="padding:4px 12px;border:1px solid #e4e7ed">{esc(l)}</td>' + "".join(
                        f'<td style="padding:4px 12px;border:1px solid #e4e7ed;text-align:right">{esc(s["values"][i])}</td>'
                        for s in series) + "</tr>"
                    for i, l in enumerate(b["labels"])
                )
                rows = head + rows
            else:
                rows = "".join(
                    f'<tr><td style="padding:4px 12px;border:1px solid #e4e7ed">{esc(l)}</td>'
                    f'<td style="padding:4px 12px;border:1px solid #e4e7ed;text-align:right">{esc(v)}</td></tr>'
                    for l, v in zip(b["labels"], series[0]["values"])
                )
            return (f'<h3 style="margin:20px 0 8px">{esc(b["title"])}</h3>'
                    f'<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13px">{rows}</table>')
        if b["type"] == "pivot":
            th = 'padding:4px 12px;border:1px solid #e4e7ed;background:#f5f7fa'
            td = 'padding:4px 12px;border:1px solid #e4e7ed'
            tdn = td + ';text-align:right'
            totals = b.get("totals")
            head = f'<th style="{th}">行＼列</th>' + "".join(f'<th style="{th};text-align:right">{esc(c)}</th>' for c in b["col_labels"])
            if totals:
                head += f'<th style="{th};text-align:right">合计</th>'
            rows_html = ""
            for i, rl in enumerate(b["row_labels"]):
                row_cells = "".join(f'<td style="{tdn}">{esc(v)}</td>' for v in b["cells"][i])
                if totals:
                    row_cells += f'<td style="{tdn};font-weight:600">{esc(b["row_totals"][i])}</td>'
                rows_html += f'<tr><td style="{td}">{esc(rl)}</td>{row_cells}</tr>'
            if totals:
                total_cells = "".join(f'<td style="{tdn};font-weight:600">{esc(v)}</td>' for v in b["col_totals"])
                total_cells += f'<td style="{tdn};font-weight:600">{esc(b["grand_total"])}</td>'
                rows_html += f'<tr><td style="{td};font-weight:600">合计</td>{total_cells}</tr>'
            return (f'<h3 style="margin:20px 0 8px">{esc(b["title"])}</h3>'
                    f'<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13px"><tr>{head}</tr>{rows_html}</table>')
        if b["type"] == "table":
            head = "".join(f'<th style="padding:4px 12px;border:1px solid #e4e7ed;background:#f5f7fa">{esc(c["label"])}</th>' for c in b["columns"])
            rows = "".join(
                "<tr>" + "".join(f'<td style="padding:4px 12px;border:1px solid #e4e7ed">{esc(r.get(c["prop"]))}</td>' for c in b["columns"]) + "</tr>"
                for r in b["rows"][:50]
            )
            note = f'<p style="color:#888;font-size:12px">共 {b["total"]} 条，仅显示前 50 条</p>' if b["total"] > 50 else ""
            return (f'<h3 style="margin:20px 0 8px">{esc(b["title"])}</h3>'
                    f'<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13px"><tr>{head}</tr>{rows}</table>{note}')
        if b["type"] == "text":
            return f'<p style="margin:16px 0;color:#606266">{esc(b["content"])}</p>'
        return ""

    parts = [
        f'<h2 style="margin:0 0 4px">{esc(result["name"])}</h2>',
        f'<p style="color:#888;margin:0 0 16px">{esc(result["range"]["label"])} · 生成于 {esc(result["generated_at"])}</p>',
    ]
    sections = sectioned_blocks(result)
    multi = result.get("layout") and len(sections) > 1
    if not multi:
        stats = [b for b in result["blocks"] if b["type"] == "stat"]
        if stats:
            parts.append(stat_table(stats))
        for b in result["blocks"]:
            parts.append(block_html(b))
    else:
        for sec_title, blocks in sections:
            parts.append(f'<h3 style="margin:24px 0 10px;padding-left:8px;border-left:4px solid #409eff">{esc(sec_title)}</h3>')
            stat_run: list = []
            for b in blocks:
                if b["type"] == "stat":
                    stat_run.append(b)
                    continue
                if stat_run:
                    parts.append(stat_table(stat_run))
                    stat_run = []
                parts.append(block_html(b))
            if stat_run:
                parts.append(stat_table(stat_run))
    return '<div style="font-family:Helvetica,Arial,sans-serif;max-width:720px">' + "".join(parts) + "</div>"


# ---------- Webhook 推送（企业微信/钉钉群机器人） ----------

def render_markdown(result: dict, max_rows: int = 10) -> str:
    """报表结果的 Markdown 摘要，供群机器人推送。企微 markdown 不支持表格/图片，统一用列表行。
    有布局时按页签分节，无布局保持原版式。"""
    lines = [f"### 【{result['name']}】{result['range']['label']}"]
    stats = [b for b in result["blocks"] if b["type"] == "stat"]
    if stats:
        for b in stats:
            cell = f"**{b['title']}**：{b['value']}{'%' if b.get('agg') == 'ratio' else ''}"
            cmp_ = b.get("compare")
            if cmp_:
                cmp_label = "较去年同期" if cmp_.get("type") == "yoy" else "较上期"
                cell += f"（{cmp_label} {'↑' if cmp_['delta'] >= 0 else '↓'}{abs(cmp_['delta_pct'])}%）" if cmp_["delta_pct"] is not None else "（对比期无基数）"
            lines.append(f"- {cell}")

    def block_md(b) -> None:
        if b["type"] == "filter":
            return
        if b["type"] == "chart" and b.get("chart_type") == "gauge":
            lines.append(f"- **{b['title']}**：{b.get('value')}")
            return
        if b["type"] == "chart":
            lines.append(f"\n**{b['title']}**")
            series = b.get("series") or [{"name": "值", "values": b.get("values") or []}]
            if len(series) > 1:
                for i, l in enumerate(b["labels"]):
                    parts = "，".join(f"{s['name']} {s['values'][i]}" for s in series)
                    lines.append(f"- {l}：{parts}")
            else:
                lines.extend(f"- {l}：{v}" for l, v in zip(b["labels"], series[0]["values"]))
        elif b["type"] == "pivot":
            lines.append(f"\n**{b['title']}**")
            for i, rl in enumerate(b["row_labels"][:max_rows]):
                line = f"- {rl}：" + "，".join(f"{cl} {v}" for cl, v in zip(b["col_labels"], b["cells"][i]))
                if b.get("totals"):
                    line += f"｜合计 {b['row_totals'][i]}"
                lines.append(line)
            if len(b["row_labels"]) > max_rows:
                lines.append(f"- …（共 {len(b['row_labels'])} 行，仅显示前 {max_rows} 行）")
            if b.get("totals"):
                lines.append("- **合计**：" + "，".join(f"{cl} {v}" for cl, v in zip(b["col_labels"], b["col_totals"]))
                             + f"｜总计 {b['grand_total']}")
        elif b["type"] == "table":
            note = f"（共 {b['total']} 条，仅显示前 {min(len(b['rows']), max_rows)} 条）" if b["total"] > max_rows else ""
            lines.append(f"\n**{b['title']}**{note}")
            head = " | ".join(str(c["label"]) for c in b["columns"])
            lines.append(f"`{head}`")
            for r in b["rows"][:max_rows]:
                lines.append("- " + " | ".join(str(r.get(c["prop"]) or "—") for c in b["columns"]))
        elif b["type"] == "text":
            lines.append(f"\n{b['content']}")

    sections = sectioned_blocks(result)
    if result.get("layout") and len(sections) > 1:
        for sec_title, blocks in sections:
            lines.append(f"\n**── {sec_title} ──**")
            for b in blocks:
                if b["type"] != "stat":   # 统计卡已在顶部汇总
                    block_md(b)
    else:
        for b in result["blocks"]:
            block_md(b)
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


def _guard_rule_met(result: dict, rule: dict) -> bool:
    """单条阈值条件：rule={block_id, op, value}，引用统计卡的数值。
    找不到块/值非数值时不误拦（宁可发）——配置变更不该静默吞掉推送。"""
    blk = next((b for b in (result.get("blocks") or [])
                if b.get("id") == rule.get("block_id") and b.get("type") == "stat"), None)
    if blk is None or blk.get("value") is None:
        return True
    try:
        v, target = float(blk["value"]), float(rule.get("value"))
    except (TypeError, ValueError):
        return True
    return {
        "gt": v > target, "gte": v >= target, "lt": v < target, "lte": v <= target,
        "eq": v == target, "ne": v != target,
    }.get(rule.get("op") or "gt", True)


def _guard_met(result: dict, guard: dict) -> bool:
    """阈值告警开关：guard={logic: AND|OR, rules: [{block_id, op, value}]}；
    兼容单条件旧格式 {block_id, op, value}。无条件 = 不拦截。"""
    if not guard:
        return True
    rules = [r for r in (guard.get("rules") or []) if r.get("block_id")]
    if not rules and guard.get("block_id"):
        rules = [guard]
    if not rules:
        return True
    results = [_guard_rule_met(result, r) for r in rules]
    return any(results) if guard.get("logic") == "OR" else all(results)


def push_template(template_id: int, trigger: str = "schedule", range_override: dict | None = None,
                  viewer_id: int | None = None) -> dict | None:
    """生成报表并推送（邮件 + 群机器人 Webhook），写 ReportRunLog。供调度器和手动调用。
    range_override：工作流「推送报表」节点的口径覆盖（不落库，仅本次生成生效）。
    viewer_id（P1 数据范围）：报表内容按该用户的 scope 过滤；默认模板主人，工作流节点传流程 owner。"""
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
            from ..models import User
            viewer = db.get(User, viewer_id or tpl.user_id)   # P1：推送内容按执行人范围过滤
            result = run_template(db, tpl, range_override=range_override, viewer=viewer)
            run.range_label = result["range"]["label"]
            push = tpl.push_json or {}
            # 阈值告警：仅当统计卡数值满足条件时才发送（条件不满足 = 本次静默跳过，日志标记 skipped）
            guard = push.get("guard") or {}
            if not _guard_met(result, guard):
                run.sent_count = 0
                run.skipped = True
                db.add(run)
                db.commit()
                return {"sent": 0, "skipped": True, "range_label": run.range_label, "error": None}
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
