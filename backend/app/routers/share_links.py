"""链接分享：表/报表生成免登录只读链接（可设密码和有效期）+ 公开访问接口。"""
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import MetaTable, ReportTemplate, SharedLink, User
from ..services import dyn_engine
from ..services.report_engine import run_template
from ..utils.access import check_owner_or_admin, get_table_access
from ..utils.auth import get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api", tags=["share-links"])


class ShareLinkIn(BaseModel):
    password: str | None = None
    expires_in_days: int | None = None   # 有效期（天），空 = 永久
    allow_interact: bool = False         # 报表：允许查看者筛选/切换时间口径


def _table_access_dep():
    from ..utils.access import require_table
    return require_table("view")


def _check_table_owner(access, user: User) -> None:
    if not access.is_owner and not access.is_admin:
        raise HTTPException(404, "数据表不存在")


def _get_own_template(db: Session, tpl_id: int, user: User) -> ReportTemplate:
    tpl = db.get(ReportTemplate, tpl_id)
    if not tpl:
        raise HTTPException(404, "报表模板不存在")
    check_owner_or_admin(tpl.user_id, user, db, tpl.tenant_id)
    return tpl


def _link_out(db: Session, link: SharedLink) -> dict:
    return {
        "id": link.id, "token": link.token, "resource_type": link.resource_type,
        "has_password": bool(link.password_hash),
        "allow_interact": bool(link.allow_interact),
        "expires_at": link.expires_at.isoformat(sep=" ") if link.expires_at else None,
        "created_at": link.created_at.isoformat(sep=" ") if link.created_at else None,
    }


def _create_link(db: Session, resource_type: str, resource_id: int, payload: ShareLinkIn, user: User) -> SharedLink:
    if payload.password is not None and len(payload.password) < 4:
        raise HTTPException(400, "访问密码至少 4 位")
    if payload.expires_in_days is not None and payload.expires_in_days < 1:
        raise HTTPException(400, "有效期至少 1 天")
    link = SharedLink(
        token=secrets.token_urlsafe(24),
        resource_type=resource_type,
        resource_id=resource_id,
        password_hash=hash_password(payload.password) if payload.password else None,
        expires_at=datetime.now() + timedelta(days=payload.expires_in_days) if payload.expires_in_days else None,
        allow_interact=bool(payload.allow_interact),
        created_by=user.id,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def _delete_link(db: Session, link_id: int, resource_type: str, resource_id: int) -> None:
    link = db.get(SharedLink, link_id)
    if not link or link.resource_type != resource_type or link.resource_id != resource_id:
        raise HTTPException(404, "分享链接不存在")
    db.delete(link)
    db.commit()


# ---------- 表的链接分享 ----------

@router.get("/tables/{table_id}/share-links")
def list_table_links(table_id: int, db: Session = Depends(get_db),
                     access=Depends(_table_access_dep()), user: User = Depends(get_current_user)):
    _check_table_owner(access, user)
    links = db.query(SharedLink).filter_by(resource_type="table", resource_id=table_id).all()
    return [_link_out(db, l) for l in links]


@router.post("/tables/{table_id}/share-links")
def create_table_link(table_id: int, payload: ShareLinkIn, db: Session = Depends(get_db),
                      access=Depends(_table_access_dep()), user: User = Depends(get_current_user)):
    _check_table_owner(access, user)
    return _link_out(db, _create_link(db, "table", table_id, payload, user))


@router.delete("/tables/{table_id}/share-links/{link_id}")
def delete_table_link(table_id: int, link_id: int, db: Session = Depends(get_db),
                      access=Depends(_table_access_dep()), user: User = Depends(get_current_user)):
    _check_table_owner(access, user)
    _delete_link(db, link_id, "table", table_id)
    return {"ok": True}


# ---------- 报表的链接分享 ----------

@router.get("/reports/{tpl_id}/share-links")
def list_report_links(tpl_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = _get_own_template(db, tpl_id, user)
    links = db.query(SharedLink).filter_by(resource_type="report", resource_id=tpl.id).all()
    return [_link_out(db, l) for l in links]


@router.post("/reports/{tpl_id}/share-links")
def create_report_link(tpl_id: int, payload: ShareLinkIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = _get_own_template(db, tpl_id, user)
    return _link_out(db, _create_link(db, "report", tpl.id, payload, user))


@router.delete("/reports/{tpl_id}/share-links/{link_id}")
def delete_report_link(tpl_id: int, link_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = _get_own_template(db, tpl_id, user)
    _delete_link(db, link_id, "report", tpl.id)
    return {"ok": True}


# ---------- 公开访问（免登录） ----------

@router.get("/share/{token}")
def visit_share(
    token: str,
    password: str = Query(default=""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    mode: str | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    filters: str | None = Query(default=None),
    block_pages: str | None = Query(default=None),
    overrides_raw: str | None = Query(default=None, alias="block_overrides"),
    db: Session = Depends(get_db),
):
    """公开只读访问：表 → 元数据+记录；报表 → 运行结果。支持密码和有效期。
    报表链接开启 allow_interact 时，查看者可带 mode/start/end（口径）与 filters（JSON 筛选）；
    block_pages（JSON 明细表分页）是纯展示层参数，恒可用。"""
    link = db.query(SharedLink).filter_by(token=token).first()
    if not link:
        raise HTTPException(404, "分享链接不存在")
    if link.expires_at and link.expires_at < datetime.now():
        raise HTTPException(410, "链接已过期")
    if link.password_hash:
        if not password:
            raise HTTPException(401, "需要访问密码")
        if not verify_password(password, link.password_hash):
            raise HTTPException(401, "访问密码错误")

    if link.resource_type == "table":
        mt = db.get(MetaTable, link.resource_id)
        if not mt:
            raise HTTPException(404, "数据表不存在")
        from ..services.meta_service import field_out, get_meta_fields
        result = dyn_engine.list_records(db, mt.id, page, page_size, None, "id", "desc")
        return {
            "resource_type": "table",
            "label": mt.label,
            "fields": [field_out(f) for f in get_meta_fields(db, mt.id)],
            "records": result["items"],
            "total": result["total"],
            "page": page,
            "page_size": page_size,
        }

    tpl = db.get(ReportTemplate, link.resource_id)
    if not tpl:
        raise HTTPException(404, "报表不存在")
    pages = None
    overrides = None
    if block_pages:
        import json
        try:
            pages = json.loads(block_pages)
        except ValueError:
            raise HTTPException(400, "block_pages 参数不是合法 JSON")
        if not isinstance(pages, dict):
            raise HTTPException(400, "block_pages 必须是对象")
    # 明细表点列头排序：纯展示层参数（只放行排序键，不给外部改分组/筛选语义）
    if overrides_raw:
        import json
        try:
            ov = json.loads(overrides_raw)
        except ValueError:
            raise HTTPException(400, "block_overrides 参数不是合法 JSON")
        if isinstance(ov, dict):
            overrides = {
                bid: {k: v for k, v in o.items() if k in ("sort_by", "sort_order")}
                for bid, o in ov.items() if isinstance(o, dict)
            }
    interact = bool(link.allow_interact)
    range_override, viewer_filters = None, None
    if interact:
        rng = {}
        if mode:
            from ..services.report_engine import RANGE_MODES
            if mode not in RANGE_MODES:
                raise HTTPException(400, "不支持的时间口径")
            rng["mode"] = mode
        if start:
            rng["start"] = start
        if end:
            rng["end"] = end
        range_override = rng or None
        if filters:
            import json
            try:
                viewer_filters = json.loads(filters)
            except ValueError:
                raise HTTPException(400, "filters 参数不是合法 JSON")
    result = run_template(db, tpl, range_override, viewer_filters=viewer_filters,
                          block_pages=pages, block_overrides=overrides)
    return {"resource_type": "report", "label": tpl.name, "report": result, "allow_interact": interact}
