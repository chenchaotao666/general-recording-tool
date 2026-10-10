"""租户成员管理：邀请（max_seats 配额校验）/ 接受 / 改角色 / 移除。席位口径 = invited + active。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Role, TenantMember, User
from ..services import entitlement
from ..services.notify import notify_user
from ..utils.context import Context, get_current_context, require_tenant_admin

router = APIRouter(prefix="/api/members", tags=["members"])


class InviteIn(BaseModel):
    username: str
    role: str = "user"


class RoleIn(BaseModel):
    role: str


def _out(db: Session, m: TenantMember) -> dict:
    u = db.get(User, m.user_id)
    return {
        "id": m.id, "user_id": m.user_id, "username": u.username if u else m.user_id,
        "role": m.role, "status": m.status,
        "created_at": m.created_at.isoformat(sep=" ") if m.created_at else None,
    }


def _check_role(db: Session, role: str) -> None:
    if role == "admin" or db.query(Role).filter_by(code=role).first():
        return
    raise HTTPException(400, f"角色不存在：{role}")


@router.get("")
def list_members(db: Session = Depends(get_db), ctx: Context = Depends(require_tenant_admin)):
    rows = db.query(TenantMember).filter_by(tenant_id=ctx.tenant.id).order_by(TenantMember.id).all()
    return [_out(db, m) for m in rows]


@router.get("/invitations")
def my_invitations(db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    """我的待接受邀请（跨全部租户），配合通知中心使用。"""
    from ..models import Tenant
    rows = db.query(TenantMember).filter_by(user_id=ctx.user.id, status="invited").all()
    return [{"id": m.id, "tenant_id": m.tenant_id, "role": m.role,
             "tenant_name": (db.get(Tenant, m.tenant_id) or Tenant(name="?")).name}
            for m in rows]


@router.post("/invite")
def invite(body: InviteIn, db: Session = Depends(get_db), ctx: Context = Depends(require_tenant_admin)):
    target = db.query(User).filter(User.username == body.username.strip()).first()
    if not target:
        raise HTTPException(404, "用户不存在（对方需先注册账号）")
    _check_role(db, body.role)
    existing = db.query(TenantMember).filter_by(tenant_id=ctx.tenant.id, user_id=target.id).first()
    if existing:
        if existing.status == "disabled":
            entitlement.check_quota(db, ctx.tenant.id, "max_seats")
            existing.status = "invited"
            existing.role = body.role
            existing.invited_by = ctx.user.id
            entitlement.bump_usage(db, ctx.tenant.id, "seat_count", 1)
            db.commit()
            return _out(db, existing)
        raise HTTPException(400, "该用户已是本空间成员")
    entitlement.check_quota(db, ctx.tenant.id, "max_seats")
    m = TenantMember(tenant_id=ctx.tenant.id, user_id=target.id, role=body.role,
                     status="invited", invited_by=ctx.user.id, created_at=datetime.now())
    db.add(m)
    entitlement.bump_usage(db, ctx.tenant.id, "seat_count", 1)
    notify_user(db, target.id, "工作空间邀请",
                f"{ctx.user.username} 邀请你加入工作空间「{ctx.tenant.name}」（角色：{body.role}）",
                link="/members")
    db.commit()
    return _out(db, m)


@router.post("/{member_id}/accept")
def accept(member_id: int, db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    """本人接受邀请（invited → active）。席位已含 invited，不再重复计数。"""
    m = db.get(TenantMember, member_id)
    if not m or m.user_id != ctx.user.id or m.status != "invited":
        raise HTTPException(404, "邀请不存在")
    m.status = "active"
    db.commit()
    return _out(db, m)


@router.put("/{member_id}/role")
def set_role(member_id: int, body: RoleIn, db: Session = Depends(get_db),
             ctx: Context = Depends(require_tenant_admin)):
    m = db.get(TenantMember, member_id)
    if not m or m.tenant_id != ctx.tenant.id:
        raise HTTPException(404, "成员不存在")
    _check_role(db, body.role)
    if m.user_id == ctx.tenant.owner_user_id and body.role != "admin":
        raise HTTPException(400, "空间所有者必须保持管理员角色")
    m.role = body.role
    db.commit()
    return _out(db, m)


@router.delete("/{member_id}")
def remove(member_id: int, db: Session = Depends(get_db), ctx: Context = Depends(require_tenant_admin)):
    m = db.get(TenantMember, member_id)
    if not m or m.tenant_id != ctx.tenant.id:
        raise HTTPException(404, "成员不存在")
    if m.user_id == ctx.tenant.owner_user_id:
        raise HTTPException(400, "不能移除空间所有者")
    db.delete(m)
    if m.status in ("invited", "active"):
        entitlement.bump_usage(db, ctx.tenant.id, "seat_count", -1)
    db.commit()
    return {"ok": True}
