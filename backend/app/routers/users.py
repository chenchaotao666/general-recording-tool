"""用户管理：全站列表/改角色为平台超管专属；用户搜索（登录即可）。
租户内的成员管理走 /api/members。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Friendship, GroupMember, Role, Tenant, TenantMember, User
from ..utils.auth import get_current_user
from ..utils.context import Context, get_current_context, require_platform_admin

router = APIRouter(prefix="/api/users", tags=["users"])


class RoleIn(BaseModel):
    tenant_id: int
    role: str


def _user_out(db: Session, u: User) -> dict:
    tenants = (
        db.query(TenantMember, Tenant)
        .join(Tenant, TenantMember.tenant_id == Tenant.id)
        .filter(TenantMember.user_id == u.id)
        .all()
    )
    return {
        "id": u.id, "username": u.username,
        "is_platform_admin": bool(u.is_platform_admin),
        "tenants": [{"id": t.id, "name": t.name, "type": t.type, "role": m.role, "status": m.status}
                    for m, t in tenants],
        "created_at": u.created_at.isoformat(sep=" ") if u.created_at else None,
    }


@router.get("")
def list_users(db: Session = Depends(get_db), admin: Context = Depends(require_platform_admin)):
    return [_user_out(db, u) for u in db.query(User).order_by(User.id).all()]


@router.get("/search")
def search_users(
    q: str = Query(default=""),
    scope: str = Query(default="shareable"),   # shareable=好友+同组（选分享对象）；all=全站（加好友）
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """用户搜索：shareable=好友+同组（选分享对象）；all=全站（仅平台超管，加好友下拉用）。"""
    is_platform = bool(user.is_platform_admin)
    if scope == "all" and not is_platform:
        raise HTTPException(403, "仅平台管理员可以搜索全站用户；添加好友请输入完整用户名")
    query = db.query(User).filter(User.id != user.id)
    if scope == "shareable" and not is_platform:
        friend_rows = db.query(Friendship).filter(
            Friendship.status == "accepted",
            or_(Friendship.requester_id == user.id, Friendship.addressee_id == user.id),
        ).all()
        friend_ids = [f.addressee_id if f.requester_id == user.id else f.requester_id for f in friend_rows]
        my_groups = [g.group_id for g in db.query(GroupMember).filter_by(user_id=user.id).all()]
        mate_ids = [
            m.user_id for m in db.query(GroupMember)
            .filter(GroupMember.group_id.in_(my_groups or [-1]), GroupMember.user_id != user.id)
            .all()
        ] if my_groups else []
        query = query.filter(User.id.in_(friend_ids + mate_ids or [-1]))
    elif scope != "all" and scope != "shareable":
        raise HTTPException(400, "scope 必须是 shareable 或 all")
    q = q.strip()
    if q:
        query = query.filter(User.username.like(f"%{q}%"))
    rows = query.order_by(User.id).limit(20).all()
    return [{"id": u.id, "username": u.username} for u in rows]


@router.put("/{user_id}/role")
def set_role(user_id: int, body: RoleIn, db: Session = Depends(get_db),
             admin: Context = Depends(require_platform_admin)):
    """平台超管改某用户在某租户的角色（租户内的日常角色管理走 /api/members/{id}/role）。"""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    if not db.query(Role).filter(Role.code == body.role).first():
        raise HTTPException(400, "角色不存在")
    m = db.query(TenantMember).filter_by(tenant_id=body.tenant_id, user_id=user_id).first()
    if not m:
        raise HTTPException(404, "该用户不是此工作空间的成员")
    tenant = db.get(Tenant, body.tenant_id)
    if tenant and tenant.owner_user_id == user_id and body.role != "admin":
        raise HTTPException(400, "空间所有者必须保持管理员角色")
    m.role = body.role
    db.commit()
    return _user_out(db, u)
