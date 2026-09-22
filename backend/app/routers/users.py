"""用户管理（仅 admin）：列表、改角色"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Role, User
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
