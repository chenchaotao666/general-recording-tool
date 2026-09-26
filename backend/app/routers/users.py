"""用户管理（仅 admin）：列表、改角色；用户搜索（登录即可）"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Friendship, GroupMember, Role, User
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/users", tags=["users"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "仅管理员可操作")
    return user


class RoleIn(BaseModel):
    role: str


def _user_out(u: User) -> dict:
    return {
        "id": u.id, "username": u.username, "role": u.role,
        "created_at": u.created_at.isoformat(sep=" ") if u.created_at else None,
    }


@router.get("")
def list_users(db: Session = Depends(get_db), admin: User = Depends(_require_admin)):
    return [_user_out(u) for u in db.query(User).order_by(User.id).all()]


@router.get("/search")
def search_users(
    q: str = Query(default=""),
    scope: str = Query(default="shareable"),   # shareable=好友+同组（选分享对象）；all=全站（加好友）
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """用户搜索：shareable=好友+同组（选分享对象）；all=全站（仅 admin，加好友下拉用）。"""
    if scope == "all" and user.role != "admin":
        raise HTTPException(403, "仅管理员可以搜索全站用户；添加好友请输入完整用户名")
    query = db.query(User).filter(User.id != user.id)
    if scope == "shareable" and user.role != "admin":
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
def set_role(user_id: int, body: RoleIn, db: Session = Depends(get_db), admin: User = Depends(_require_admin)):
    if user_id == admin.id:
        raise HTTPException(400, "不能修改自己的角色")
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    if not db.query(Role).filter(Role.code == body.role).first():
        raise HTTPException(400, "角色不存在")
    u.role = body.role
    db.commit()
    return _user_out(u)
