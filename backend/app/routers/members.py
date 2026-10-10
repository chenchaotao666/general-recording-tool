"""租户成员管理：邀请（max_seats 配额校验）/ 接受 / 改角色 / 移除。席位口径 = invited + active。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Department, Role, TenantMember, User
from ..services import entitlement, scope as scope_mod
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
    dept = db.get(Department, u.department_id) if u and u.department_id else None
    mgr = db.get(User, u.manager_id) if u and u.manager_id else None
    return {
        "id": m.id, "user_id": m.user_id, "username": u.username if u else m.user_id,
        "role": m.role, "status": m.status,
        "department_id": dept.id if dept and dept.tenant_id == m.tenant_id and dept.enabled else None,
        "department_name": dept.name if dept and dept.tenant_id == m.tenant_id and dept.enabled else None,
        "manager_id": mgr.id if mgr else None,
        "manager_name": mgr.username if mgr else None,
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


class OrgIn(BaseModel):
    department_id: int | None = None
    manager_id: int | None = None


@router.put("/{member_id}/org")
def set_org(member_id: int, body: OrgIn, db: Session = Depends(get_db),
            ctx: Context = Depends(require_tenant_admin)):
    """挂靠组织：所属部门（本租户 enabled 部门）+ 直属上级（本租户成员，防环限深 10 层）。
    users.department_id/manager_id 是全局单列（一人一部一上级，文档已定的简化）。"""
    m = db.get(TenantMember, member_id)
    if not m or m.tenant_id != ctx.tenant.id:
        raise HTTPException(404, "成员不存在")
    u = db.get(User, m.user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    if body.department_id is not None:
        d = db.get(Department, body.department_id)
        if not d or d.tenant_id != ctx.tenant.id or not d.enabled:
            raise HTTPException(404, "部门不存在或已停用")
        u.department_id = body.department_id
    else:
        u.department_id = None
    if body.manager_id is not None:
        if body.manager_id == u.id:
            raise HTTPException(400, "直属上级不能是自己")
        if not db.query(TenantMember).filter_by(
                tenant_id=ctx.tenant.id, user_id=body.manager_id, status="active").first():
            raise HTTPException(400, "直属上级须为本工作空间成员")
        # 防环：沿目标上级的 manager 链上溯，命中自己即成环
        seen, cur, depth = {u.id}, body.manager_id, 0
        while cur is not None and depth < 10:
            if cur in seen:
                raise HTTPException(400, "直属上级设置会形成循环汇报关系")
            seen.add(cur)
            nxt = db.get(User, cur)
            cur, depth = (nxt.manager_id if nxt else None), depth + 1
        u.manager_id = body.manager_id
    else:
        u.manager_id = None
    db.commit()
    scope_mod.invalidate_scope_cache(ctx.tenant.id)
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
    # 清理组织引用（P1）：退租后部门/上级不留脏引用；名下记录的可见性由「记录转移」兜底
    u = db.get(User, m.user_id)
    if u:
        u.department_id = None
        u.manager_id = None
    db.commit()
    scope_mod.invalidate_scope_cache(ctx.tenant.id)
    return {"ok": True}
