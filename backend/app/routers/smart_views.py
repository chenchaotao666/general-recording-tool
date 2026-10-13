"""智能表视图路由（设计文档 §2.3）：视图 CRUD / 复制 / 设默认 / 个人覆盖（仅你可见）/ 字段删除依赖。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import MetaTable, MetaView, MetaViewPref
from ..services.meta_service import get_meta_fields
from ..services import view_config
from ..utils.access import TableAccess, get_table_access, require_table
from ..utils.context import Context, get_current_context

router = APIRouter(prefix="/api/smart", tags=["smart-views"])


def _view_out(v: MetaView) -> dict:
    return {
        "id": v.id, "table_id": v.table_id, "name": v.name, "type": v.type,
        "config": v.config or {}, "is_default": bool(v.is_default),
        "created_by": v.created_by,
        "created_at": v.created_at.isoformat(sep=" ") if v.created_at else None,
    }


def _get_view(db: Session, view_id: int) -> MetaView:
    v = db.get(MetaView, view_id)
    if not v:
        raise HTTPException(404, "视图不存在")
    return v


def _access_for_view(db: Session, v: MetaView, ctx: Context, perm: str) -> TableAccess:
    access = get_table_access(db, v.table_id, ctx.user, ctx)
    if not getattr(access, {"view": "can_view", "edit": "can_edit", "delete": "can_delete",
                            "create": "can_create"}[perm]):
        raise HTTPException(404, "数据表不存在")
    return access


@router.get("/tables/{table_id}/views")
def list_views(table_id: int, db: Session = Depends(get_db),
               access: TableAccess = Depends(require_table("view"))):
    rows = (db.query(MetaView).filter_by(table_id=table_id)
            .order_by(MetaView.is_default.desc(), MetaView.id).all())
    return {"views": [_view_out(v) for v in rows]}


@router.post("/tables/{table_id}/views")
def create_view(table_id: int, payload: dict, db: Session = Depends(get_db),
                access: TableAccess = Depends(require_table("edit"))):
    fields = get_meta_fields(db, table_id)
    config = view_config.validate_view_config(payload.get("config"), fields)
    v = MetaView(table_id=table_id, name=str(payload.get("name") or "表格视图").strip()[:100] or "表格视图",
                 type="grid", config=config, is_default=False, created_by=access.ctx.user.id)
    db.add(v)
    db.commit()
    db.refresh(v)
    return {"view": _view_out(v)}


@router.patch("/views/{view_id}")
def update_view(view_id: int, payload: dict, db: Session = Depends(get_db),
                ctx: Context = Depends(get_current_context)):
    v = _get_view(db, view_id)
    _access_for_view(db, v, ctx, "edit")
    if "name" in payload:
        nm = str(payload["name"] or "").strip()
        if not nm:
            raise HTTPException(400, "视图名称不能为空")
        v.name = nm[:100]
    if "config" in payload:
        fields = get_meta_fields(db, v.table_id)
        v.config = view_config.validate_view_config(payload["config"], fields)
    db.commit()
    db.refresh(v)
    return {"view": _view_out(v)}


@router.delete("/views/{view_id}")
def delete_view(view_id: int, db: Session = Depends(get_db),
                ctx: Context = Depends(get_current_context)):
    v = _get_view(db, view_id)
    _access_for_view(db, v, ctx, "edit")
    cnt = db.query(MetaView).filter_by(table_id=v.table_id).count()
    if cnt <= 1:
        raise HTTPException(400, "至少保留一个视图")
    was_default = v.is_default
    db.query(MetaViewPref).filter_by(view_id=v.id).delete()
    db.delete(v)
    if was_default:
        nxt = db.query(MetaView).filter_by(table_id=v.table_id).order_by(MetaView.id).first()
        if nxt:
            nxt.is_default = True
    db.commit()
    return {"ok": True}


@router.post("/views/{view_id}/duplicate")
def duplicate_view(view_id: int, db: Session = Depends(get_db),
                   ctx: Context = Depends(get_current_context)):
    v = _get_view(db, view_id)
    _access_for_view(db, v, ctx, "edit")
    nv = MetaView(table_id=v.table_id, name=f"{v.name} 副本"[:100], type=v.type,
                  config=dict(v.config or {}), is_default=False, created_by=ctx.user.id)
    db.add(nv)
    db.commit()
    db.refresh(nv)
    return {"view": _view_out(nv)}


@router.post("/views/{view_id}/set-default")
def set_default_view(view_id: int, db: Session = Depends(get_db),
                     ctx: Context = Depends(get_current_context)):
    v = _get_view(db, view_id)
    _access_for_view(db, v, ctx, "edit")
    db.query(MetaView).filter_by(table_id=v.table_id).update({"is_default": False})
    v.is_default = True
    db.commit()
    return {"ok": True}


# ---------- 个人覆盖（「调整仅你可见」，V1 仅 filters 键） ----------

@router.put("/views/{view_id}/prefs")
def put_pref(view_id: int, payload: dict, db: Session = Depends(get_db),
             ctx: Context = Depends(get_current_context)):
    v = _get_view(db, view_id)
    _access_for_view(db, v, ctx, "view")
    config = payload.get("config") or {}
    if set(config) - {"filters"}:
        raise HTTPException(400, "个人覆盖仅支持 filters")
    fields = get_meta_fields(db, v.table_id)
    cleaned = view_config.validate_view_config(config, fields)
    pref = db.query(MetaViewPref).filter_by(view_id=view_id, user_id=ctx.user.id).first()
    if not pref:
        pref = MetaViewPref(view_id=view_id, user_id=ctx.user.id, config=cleaned)
        db.add(pref)
    else:
        pref.config = cleaned
    db.commit()
    return {"ok": True, "config": cleaned}


@router.delete("/views/{view_id}/prefs")
def delete_pref(view_id: int, db: Session = Depends(get_db),
                ctx: Context = Depends(get_current_context)):
    v = _get_view(db, view_id)
    _access_for_view(db, v, ctx, "view")
    db.query(MetaViewPref).filter_by(view_id=view_id, user_id=ctx.user.id).delete()
    db.commit()
    return {"ok": True}


@router.get("/tables/{table_id}/fields/{field_name}/deps")
def field_deps(table_id: int, field_name: str, db: Session = Depends(get_db),
               access: TableAccess = Depends(require_table("edit"))):
    """字段删除依赖检查：扫描本表所有视图 config 中的引用。"""
    views = db.query(MetaView).filter_by(table_id=table_id).all()
    return {"deps": view_config.scan_field_deps(views, field_name)}
