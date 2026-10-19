"""轻企业：创建多个企业、邀请码加入、查看同事；不暴露角色/部门配置。"""
import secrets
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import EnterpriseProfile, Tenant, TenantMember, User
from ..services import entitlement
from ..services.tenancy import create_tenant
from ..utils.auth import get_current_user
from ..utils.context import Context, get_current_context, require_tenant_admin
from .auth import _user_payload

router = APIRouter(prefix="/api/enterprises", tags=["enterprises"])


class EnterpriseIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    category: Literal["企业", "学校/教育局", "政府", "其他"] = "企业"
    industry: str = Field(default="", max_length=64)
    size: str = Field(default="", max_length=32)


class JoinIn(BaseModel):
    code: str = Field(min_length=1, max_length=128)


def _new_code():
    return secrets.token_hex(12).upper()


def _enterprise(ctx):
    if ctx.tenant.type not in ("enterprise", "private"):
        raise HTTPException(400, "请先切换到企业")


@router.post("")
def create(body: EnterpriseIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "请输入企业名称")
    tenant = create_tenant(db, user, name, type="enterprise", plan_code="light_enterprise")
    db.add(EnterpriseProfile(tenant_id=tenant.id, category=body.category,
                             industry=body.industry.strip(), size=body.size.strip(),
                             invite_code=_new_code(), invite_expires_at=datetime.now() + timedelta(days=7)))
    db.commit()
    return _user_payload(db, user, tenant.id)


@router.get("/current")
def current(db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    _enterprise(ctx)
    p = db.get(EnterpriseProfile, ctx.tenant.id)
    members = (db.query(TenantMember, User).join(User, User.id == TenantMember.user_id)
               .filter(TenantMember.tenant_id == ctx.tenant.id, TenantMember.status == "active")
               .order_by(TenantMember.id).all())
    return {"id": ctx.tenant.id, "name": ctx.tenant.name,
            "category": p.category if p else "企业", "industry": p.industry if p else "",
            "size": p.size if p else "", "can_manage": ctx.is_tenant_admin,
            "lightweight": bool(p and p.lightweight),
            "members": [{"id": m.user_id, "name": u.username,
                         "is_owner": u.id == ctx.tenant.owner_user_id} for m, u in members]}


@router.put("/current")
def update(body: EnterpriseIn, db: Session = Depends(get_db), ctx: Context = Depends(require_tenant_admin)):
    _enterprise(ctx)
    if not body.name.strip():
        raise HTTPException(400, "请输入企业名称")
    entitlement.assert_tenant_writable(db, ctx.tenant.id)
    ctx.tenant.name = body.name.strip()
    p = db.get(EnterpriseProfile, ctx.tenant.id)
    if not p:
        p = EnterpriseProfile(tenant_id=ctx.tenant.id, lightweight=False,
                              invite_code=_new_code(), invite_expires_at=datetime.now() + timedelta(days=7))
        db.add(p)
    p.category, p.industry, p.size = body.category, body.industry.strip(), body.size.strip()
    db.commit()
    return current(db, ctx)


@router.post("/invitation")
def invitation(db: Session = Depends(get_db), ctx: Context = Depends(require_tenant_admin)):
    """每次生成都会替换旧码，七天有效；仅管理员能签发企业加入凭证。"""
    _enterprise(ctx)
    entitlement.assert_tenant_writable(db, ctx.tenant.id)
    p = db.get(EnterpriseProfile, ctx.tenant.id)
    if not p:
        p = EnterpriseProfile(tenant_id=ctx.tenant.id, lightweight=False)
        db.add(p)
    p.invite_code = _new_code()
    p.invite_expires_at = datetime.now() + timedelta(days=7)
    db.commit()
    return {"code": p.invite_code, "name": ctx.tenant.name,
            "expires_at": p.invite_expires_at.isoformat()}


@router.post("/preview")
def preview(body: JoinIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _resolve_code(db, body.code)
    t = db.get(Tenant, p.tenant_id)
    return {"id": t.id, "name": t.name, "category": p.category}


def _resolve_code(db, code):
    p = db.query(EnterpriseProfile).filter_by(invite_code=code.strip().upper()).first()
    if not p or p.invite_expires_at <= datetime.now():
        raise HTTPException(400, "邀请码无效或已过期，请联系企业创建者重新邀请")
    t = db.get(Tenant, p.tenant_id)
    if not t or t.type not in ("enterprise", "private"):
        raise HTTPException(400, "企业不存在")
    return p


@router.post("/join")
def join(body: JoinIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _resolve_code(db, body.code)
    tid = p.tenant_id
    m = db.query(TenantMember).filter_by(tenant_id=tid, user_id=user.id).first()
    if m and m.status == "active":
        return _user_payload(db, user, tid)
    if m and m.status == "disabled":
        raise HTTPException(403, "你在该企业的成员身份已停用，请联系企业创建者")
    entitlement.assert_tenant_writable(db, tid)
    try:
        if not m:
            entitlement.check_quota(db, tid, "max_seats")
            m = TenantMember(tenant_id=tid, user_id=user.id, role="user", status="active")
            db.add(m)
            db.flush()
            entitlement.bump_usage(db, tid, "seat_count", 1)
        else:
            # invited 已计入席位；邀请码加入始终是普通成员。
            m.status, m.role = "active", "user"
        db.commit()
    except IntegrityError:
        db.rollback()
        m = db.query(TenantMember).filter_by(tenant_id=tid, user_id=user.id, status="active").first()
        if not m:
            raise HTTPException(409, "加入失败，请重试")
    return _user_payload(db, user, tid)
