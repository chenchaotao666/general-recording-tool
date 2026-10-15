"""智能表列编组（多级表头，设计文档 §6.3）+ 仪表盘 widget 与图表聚合（§2.5.1）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DashboardWidget, MetaColumnGroup, MetaTable, SmartDoc, SmartDocEntry
from ..services import json_store, view_config
from ..services.meta_service import get_meta_fields
from ..utils.access import TableAccess, get_table_access, require_table
from ..utils.context import Context, get_current_context

router = APIRouter(prefix="/api/smart", tags=["smart-groups"])


# ---------- 列编组 ----------

def _group_out(g: MetaColumnGroup) -> dict:
    return {"id": g.id, "table_id": g.table_id, "name": g.name,
            "field_names": g.field_names or [], "order_no": g.order_no}


@router.get("/tables/{table_id}/column-groups")
def list_column_groups(table_id: int, db: Session = Depends(get_db),
                       access: TableAccess = Depends(require_table("view"))):
    rows = (db.query(MetaColumnGroup).filter_by(table_id=table_id)
            .order_by(MetaColumnGroup.order_no, MetaColumnGroup.id).all())
    return {"groups": [_group_out(g) for g in rows]}


@router.post("/tables/{table_id}/column-groups")
def create_column_group(table_id: int, payload: dict, db: Session = Depends(get_db),
                        access: TableAccess = Depends(require_table("edit"))):
    names = {f.field_name for f in get_meta_fields(db, table_id)}
    members = [n for n in (payload.get("field_names") or []) if n in names]
    if not members:
        raise HTTPException(400, "编组至少包含一个字段")
    name = str(payload.get("name") or "").strip() or "编组"
    g = MetaColumnGroup(table_id=table_id, name=name[:100], field_names=members,
                        order_no=db.query(MetaColumnGroup).filter_by(table_id=table_id).count())
    db.add(g)
    db.commit()
    db.refresh(g)
    return {"group": _group_out(g)}


@router.patch("/column-groups/{group_id}")
def update_column_group(group_id: int, payload: dict, db: Session = Depends(get_db),
                        ctx: Context = Depends(get_current_context)):
    g = db.get(MetaColumnGroup, group_id)
    if not g:
        raise HTTPException(404, "编组不存在")
    access = get_table_access(db, g.table_id, ctx.user, ctx)
    if not access.can_edit:
        raise HTTPException(404, "数据表不存在")
    if "name" in payload:
        g.name = str(payload["name"] or "").strip()[:100] or g.name
    if "field_names" in payload:
        names = {f.field_name for f in get_meta_fields(db, g.table_id)}
        g.field_names = [n for n in payload["field_names"] if n in names]
    db.commit()
    return {"group": _group_out(g)}


@router.delete("/column-groups/{group_id}")
def delete_column_group(group_id: int, db: Session = Depends(get_db),
                        ctx: Context = Depends(get_current_context)):
    """解散编组：字段保留，仅删除组头。"""
    g = db.get(MetaColumnGroup, group_id)
    if not g:
        raise HTTPException(404, "编组不存在")
    access = get_table_access(db, g.table_id, ctx.user, ctx)
    if not access.can_edit:
        raise HTTPException(404, "数据表不存在")
    db.delete(g)
    db.commit()
    return {"ok": True}


# ---------- 仪表盘 widget ----------

def _get_entry_checked(db: Session, entry_id: int, ctx: Context) -> SmartDocEntry:
    e = db.get(SmartDocEntry, entry_id)
    if not e or e.type != "dashboard":
        raise HTTPException(404, "仪表盘不存在")
    doc = db.get(SmartDoc, e.doc_id)
    if not doc or doc.tenant_id != ctx.tenant.id:
        raise HTTPException(404, "仪表盘不存在")
    return e


def _widget_out(w: DashboardWidget) -> dict:
    return {"id": w.id, "entry_id": w.entry_id, "title": w.title, "chart_type": w.chart_type,
            "sub_type": w.sub_type, "theme": w.theme, "config": w.config or {},
            "layout": w.layout or {}, "order_no": w.order_no}


@router.get("/dashboards/{entry_id}/widgets")
def list_widgets(entry_id: int, db: Session = Depends(get_db),
                 ctx: Context = Depends(get_current_context)):
    _get_entry_checked(db, entry_id, ctx)
    rows = (db.query(DashboardWidget).filter_by(entry_id=entry_id)
            .order_by(DashboardWidget.order_no, DashboardWidget.id).all())
    return {"widgets": [_widget_out(w) for w in rows]}


def _validate_widget_config(db: Session, cfg: dict) -> dict:
    src = cfg.get("sourceTableId")
    if not src or not db.get(MetaTable, int(src)):
        raise HTTPException(400, "数据源表不存在")
    fields = get_meta_fields(db, int(src))
    names = {f.field_name for f in fields}
    if cfg.get("dimension") not in names:
        raise HTTPException(400, "类别字段无效")
    metric = cfg.get("metric") or {}
    if metric.get("agg", "count") not in ("count", "sum", "avg", "max", "min"):
        raise HTTPException(400, "聚合方式无效")
    if metric["agg"] != "count" and metric.get("field") not in names:
        raise HTTPException(400, "指标字段无效")
    if cfg.get("subDimension") and cfg["subDimension"] not in names:
        raise HTTPException(400, "二级类别字段无效")
    return cfg


@router.post("/dashboards/{entry_id}/widgets")
def create_widget(entry_id: int, payload: dict, db: Session = Depends(get_db),
                  ctx: Context = Depends(get_current_context)):
    _get_entry_checked(db, entry_id, ctx)
    cfg = _validate_widget_config(db, payload.get("config") or {})
    w = DashboardWidget(entry_id=entry_id, title=str(payload.get("title") or "图表")[:200],
                        chart_type=payload.get("chart_type") or "bar",
                        sub_type=payload.get("sub_type"), theme=payload.get("theme"),
                        config=cfg, layout=payload.get("layout") or {},
                        order_no=db.query(DashboardWidget).filter_by(entry_id=entry_id).count())
    db.add(w)
    db.commit()
    db.refresh(w)
    return {"widget": _widget_out(w)}


@router.patch("/widgets/{widget_id}")
def update_widget(widget_id: int, payload: dict, db: Session = Depends(get_db),
                  ctx: Context = Depends(get_current_context)):
    w = db.get(DashboardWidget, widget_id)
    if not w:
        raise HTTPException(404, "图表不存在")
    _get_entry_checked(db, w.entry_id, ctx)
    for attr in ("title", "chart_type", "sub_type", "theme", "layout"):
        if payload.get(attr) is not None:
            setattr(w, attr, payload[attr])
    if payload.get("config") is not None:
        w.config = _validate_widget_config(db, payload["config"])
    db.commit()
    return {"widget": _widget_out(w)}


@router.delete("/widgets/{widget_id}")
def delete_widget(widget_id: int, db: Session = Depends(get_db),
                  ctx: Context = Depends(get_current_context)):
    w = db.get(DashboardWidget, widget_id)
    if not w:
        raise HTTPException(404, "图表不存在")
    _get_entry_checked(db, w.entry_id, ctx)
    db.delete(w)
    db.commit()
    return {"ok": True}


# ---------- 图表聚合（仪表盘预览与渲染共用） ----------

@router.post("/charts/preview")
def chart_preview(payload: dict, db: Session = Depends(get_db),
                  ctx: Context = Depends(get_current_context)):
    """通用聚合查询：{tableId, dimension, subDimension?, metric:{field?,agg}, filter?, splitMulti?}。
    返回 {categories: [{key, value, children?}], total}。"""
    table_id = int(payload.get("tableId") or 0)
    access = get_table_access(db, table_id, ctx.user, ctx)
    if not access.can_view:
        raise HTTPException(404, "数据表不存在")
    fields = get_meta_fields(db, table_id)
    names = {f.field_name: f for f in fields}
    dim = payload.get("dimension")
    if dim not in names:
        raise HTTPException(400, "类别字段无效")
    sub = payload.get("subDimension")
    metric = payload.get("metric") or {}
    agg = metric.get("agg", "count")
    mfield = metric.get("field")
    split_multi = bool(payload.get("splitMulti"))

    recs = json_store.all_dicts(db, table_id, fields, normalized=True)
    rules = view_config.conditions_to_rules(payload.get("filter"))
    if rules:
        from ..services.pyquery import match_filters
        logic = "OR" if (payload.get("filter") or {}).get("conjunction") == "or" else "AND"
        recs = [r for r in recs if match_filters(r, names, {"logic": logic, "rules": rules})]

    def dim_keys(v):
        if v is None or v == "" or v == []:
            return ["（空）"]
        if isinstance(v, list):
            return [str(x) for x in v] if split_multi else ["、".join(map(str, v))]
        return [str(v)]

    def agg_val(vals):
        if agg == "count":
            return len(vals)
        nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if not nums:
            return 0
        return {"sum": sum(nums), "avg": sum(nums) / len(nums), "max": max(nums), "min": min(nums)}[agg]

    buckets: dict[str, dict[str, list]] = {}
    for r in recs:
        for k in dim_keys(r.get(dim)):
            bk = buckets.setdefault(k, {})
            sk = str(r.get(sub)) if sub and r.get(sub) not in (None, "") else None
            bk.setdefault(sk, []).append(r.get(mfield) if mfield else 1)

    categories = []
    for k, subs in buckets.items():
        if sub:
            categories.append({"key": k, "value": sum(len(v) for v in subs.values()),
                               "children": [{"key": sk or "（空）", "value": agg_val(v)}
                                            for sk, v in subs.items()]})
        else:
            categories.append({"key": k, "value": agg_val(subs.get(None) or [])})
    sort_cfg = payload.get("sort") or {}
    categories.sort(key=lambda c: c["value"] if sort_cfg.get("by") == "value" else c["key"],
                    reverse=sort_cfg.get("direction") == "desc")
    return {"categories": categories, "total": len(recs)}
