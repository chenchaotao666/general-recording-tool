"""智能表表单（设计文档 §12）：表单 = 一种视图（meta_views.type=form，题目配置存 config.form）。

- 登录提交：POST /api/smart/views/{vid}/submit（走内容权限 firstSubmit ∪ edit 白名单）；
- 公开收集：分享链接（shared_links.resource_type=smart_form）→ /api/smart-public/forms/{token} 免登录填写；
- 提交回流：与表格新增记录同一写入管线（json_store.create_record）→ 触发「添加新记录时」自动化（§12.3）；
- 服务端复核：显示条件（隐藏题不收值、不校验必填）、必填、只读/计算字段拒收。
"""
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import MetaField, MetaTable, MetaView, SharedLink, User
from ..services import json_store, perm_service, smart_events
from ..services.field_registry import READONLY_TYPES
from ..services.meta_service import get_meta_fields
from ..services.pyquery import normalize_record
from ..services.smart_cond import match_conditions
from ..utils.access import get_table_access
from ..utils.auth import hash_password, verify_password
from ..utils.context import Context, get_current_context

router = APIRouter(prefix="/api/smart", tags=["smart-forms"])
public_router = APIRouter(prefix="/api/smart-public", tags=["smart-forms-public"])
RESOURCE = "smart_form"


def _empty(v) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _form_view(db: Session, vid: int) -> MetaView:
    v = db.get(MetaView, vid)
    if not v or v.type != "form":
        raise HTTPException(404, "表单不存在")
    return v


def _resolved_options(db: Session, f: MetaField) -> list:
    """引用选项（optionSource=reference）在公开表单里同样需要解析为真实选项集。"""
    cfg = f.options or {}
    if cfg.get("optionSource") == "reference":
        ref = cfg.get("reference") or {}
        try:
            src = next((x for x in get_meta_fields(db, int(ref.get("tableId")))
                        if x.field_name == ref.get("fieldId")), None)
        except (TypeError, ValueError):
            src = None
        if src is not None:
            return (src.options or {}).get("options") or []
    return cfg.get("options") or []


def form_definition(db: Session, v: MetaView) -> dict:
    fields = {f.field_name: f for f in get_meta_fields(db, v.table_id)}
    form = (v.config or {}).get("form") or {}
    items = []
    for it in form.get("items") or []:
        f = fields.get(it["fieldId"])
        if not f:
            continue
        opts = dict(f.options or {})
        if f.field_type in ("singleSelect", "multiSelect"):
            opts["options"] = _resolved_options(db, f)
        items.append({**it, "field": {"field_name": f.field_name, "label": f.label, "field_type": f.field_type,
                                      "data_type": f.data_type, "options": opts,
                                      "readonly": (f.field_type or "") in READONLY_TYPES}})
    return {"view_id": v.id, "table_id": v.table_id, "title": form.get("title") or v.name,
            "description": form.get("description") or "", "cover": form.get("cover"),
            "items": items, "submit": form.get("submit") or {}}


def submit_form(db: Session, v: MetaView, data: dict, user: User | None, allowed: set[str] | None) -> dict:
    """allowed=None 表示不做内容权限裁剪（匿名/管理者）；否则仅收白名单字段。"""
    mt = db.get(MetaTable, v.table_id)
    fields = get_meta_fields(db, v.table_id)
    by_name = {f.field_name: f for f in fields}
    form = (v.config or {}).get("form") or {}
    data = data if isinstance(data, dict) else {}
    # 显示条件基于其他题目的作答值求值（与前端同语义）
    probe = normalize_record({fn: data.get(fn) for fn in by_name}, by_name)
    errors, payload = {}, {}
    for it in form.get("items") or []:
        f = by_name.get(it["fieldId"])
        if f is None or (f.field_type or "") in READONLY_TYPES:
            continue
        vis = it.get("visibility")
        if vis and not match_conditions(probe, fields, vis.get("conditions"), vis.get("match", "all"), prepared=True):
            continue
        val = data.get(f.field_name)
        if it.get("required") and _empty(val):
            errors[f.field_name] = f"「{it.get('title') or f.label}」为必填项"
            continue
        if _empty(val):
            continue
        if allowed is not None and f.field_name not in allowed:
            continue
        payload[f.field_name] = val
    if errors:
        raise HTTPException(422, detail=errors)
    rec = json_store.create_record(db, mt, fields, payload,
                                   user=user.username if user else "匿名填写者",
                                   owner_id=user.id if user else None, anonymous=user is None)
    smart_events.record_created(db, mt, rec, actor_id=user.id if user else None)
    return rec


# ---------- 登录态 ----------

@router.get("/views/{vid}/form")
def get_form(vid: int, db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    v = _form_view(db, vid)
    get_table_access(db, v.table_id, ctx.user, ctx)
    return form_definition(db, v)


@router.post("/views/{vid}/submit")
def submit_logged_in(vid: int, payload: dict, db: Session = Depends(get_db),
                     ctx: Context = Depends(get_current_context)):
    v = _form_view(db, vid)
    access = get_table_access(db, v.table_id, ctx.user, ctx)
    eff = perm_service.effective_for_access(db, access)
    if not eff.can_add_record:
        raise HTTPException(403, "没有提交记录的权限")
    allowed = None
    if not eff.managed:
        rights = eff.field_rights_map(get_meta_fields(db, v.table_id))
        allowed = {fn for fn, r in rights.items() if r["firstSubmit"] or r["edit"]}
    return {"record": submit_form(db, v, payload.get("data") or {}, ctx.user, allowed)}


def _link_out(link: SharedLink | None) -> dict | None:
    if not link:
        return None
    return {"id": link.id, "token": link.token, "has_password": bool(link.password_hash),
            "expires_at": link.expires_at.isoformat(sep=" ") if link.expires_at else None}


def _require_form_manager(db: Session, v: MetaView, ctx: Context) -> None:
    access = get_table_access(db, v.table_id, ctx.user, ctx)
    if not perm_service.effective_for_access(db, access).view_manage:
        raise HTTPException(403, "没有分享表单的权限")


@router.get("/views/{vid}/share-link")
def get_share_link(vid: int, db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    v = _form_view(db, vid)
    get_table_access(db, v.table_id, ctx.user, ctx)
    link = db.query(SharedLink).filter_by(resource_type=RESOURCE, resource_id=v.id).first()
    return {"link": _link_out(link)}


@router.post("/views/{vid}/share-link")
def create_share_link(vid: int, payload: dict | None = None, db: Session = Depends(get_db),
                      ctx: Context = Depends(get_current_context)):
    """开启公开填写：一个表单一条链接（重复调用=重置密码/有效期，token 不变）。"""
    v = _form_view(db, vid)
    _require_form_manager(db, v, ctx)
    payload = payload or {}
    pw = payload.get("password")
    if pw is not None and pw != "" and len(str(pw)) < 4:
        raise HTTPException(400, "访问密码至少 4 位")
    days = payload.get("expires_in_days")
    link = db.query(SharedLink).filter_by(resource_type=RESOURCE, resource_id=v.id).first()
    if link is None:
        link = SharedLink(token=secrets.token_urlsafe(24), resource_type=RESOURCE, resource_id=v.id,
                          created_by=ctx.user.id)
        db.add(link)
    # Partial updates must not silently remove existing password/expiry protection.
    if "password" in payload:
        link.password_hash = hash_password(str(pw)) if pw else None
    if "expires_in_days" in payload:
        link.expires_at = datetime.now() + timedelta(days=int(days)) if days else None
    db.commit()
    db.refresh(link)
    return {"link": _link_out(link)}


@router.delete("/views/{vid}/share-link")
def delete_share_link(vid: int, db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    v = _form_view(db, vid)
    _require_form_manager(db, v, ctx)
    db.query(SharedLink).filter_by(resource_type=RESOURCE, resource_id=v.id).delete()
    db.commit()
    return {"ok": True}


# ---------- 公开（免登录） ----------

def _public_view(db: Session, token: str, password: str | None) -> MetaView:
    link = db.query(SharedLink).filter_by(token=token, resource_type=RESOURCE).first()
    if not link:
        raise HTTPException(404, "表单不存在或已关闭")
    if link.expires_at and link.expires_at < datetime.now():
        raise HTTPException(410, "表单链接已过期")
    if link.password_hash and not (password and verify_password(password, link.password_hash)):
        # 用 403 而非 401：前端 401 会被全局拦截跳登录页，公开页需留在原地输密码
        raise HTTPException(403, detail={"code": "password_required", "message": "请输入访问密码"})
    v = db.get(MetaView, link.resource_id)
    if not v or v.type != "form":
        raise HTTPException(404, "表单不存在或已关闭")
    return v


@public_router.get("/forms/{token}")
def public_form(token: str, password: str | None = None, db: Session = Depends(get_db)):
    v = _public_view(db, token, password)
    d = form_definition(db, v)
    d.pop("table_id", None)
    return d


@public_router.post("/forms/{token}/submit")
def public_submit(token: str, payload: dict, db: Session = Depends(get_db)):
    v = _public_view(db, token, payload.get("password"))
    form = (v.config or {}).get("form") or {}
    if (form.get("submit") or {}).get("allowAnonymous") is False:
        raise HTTPException(403, "该表单仅限登录成员填写")
    rec = submit_form(db, v, payload.get("data") or {}, None, None)
    return {"ok": True, "id": rec["id"], "successText": (form.get("submit") or {}).get("successText")}


@public_router.post("/forms/{token}/upload")
async def public_upload(token: str, file: UploadFile, kind: str = "image", password: str | None = None,
                        db: Session = Depends(get_db)):
    """公开表单的图片/文件题上传：归属表主人（存储配额计入表所在租户）。"""
    v = _public_view(db, token, password)
    mt = db.get(MetaTable, v.table_id)
    if kind == "file":
        from ..services import smart_files
        try:
            return smart_files.save(await file.read(), file.filename or "file", mt.id, None)
        except smart_files.SmartFileError as e:
            raise HTTPException(400, str(e))
    from ..services import images
    try:
        row = await images.save_image(db, file, mt.owner_id, tenant_id=mt.tenant_id)
    except images.ImageError as e:
        raise HTTPException(400, str(e))
    return {"id": row.id, "name": row.filename}


@public_router.get("/forms/{token}/cover")
def public_cover(token: str, password: str | None = None, db: Session = Depends(get_db)):
    """公开表单封面图（普通图片接口需登录，封面经表单令牌放行）。"""
    from fastapi.responses import FileResponse

    from ..services import images
    v = _public_view(db, token, password)
    cover = ((v.config or {}).get("form") or {}).get("cover")
    if not cover:
        raise HTTPException(404, "无封面")
    try:
        row, path = images.get_image(db, cover)
    except images.ImageError as e:
        raise HTTPException(404, str(e))
    return FileResponse(path, media_type=row.mime or "image/jpeg")
