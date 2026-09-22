"""用户组管理（仅 admin）：组的增删改查、成员管理。组可被分享表（table_shares.group_id）。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Group, GroupMember, TableShare, User
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/groups", tags=["groups"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "仅管理员可操作")
    return user


class GroupIn(BaseModel):
    name: str
    description: str | None = None


class MemberIn(BaseModel):
    username: str


def _group_out(db: Session, g: Group) -> dict:
    members = (
        db.query(User)
        .join(GroupMember, GroupMember.user_id == User.id)
        .filter(GroupMember.group_id == g.id)
        .order_by(User.id)
        .all()
    )
    return {
        "id": g.id, "name": g.name, "description": g.description,
        "members": [{"id": u.id, "username": u.username} for u in members],
        "member_count": len(members),
        "created_at": g.created_at.isoformat(sep=" ") if g.created_at else None,
    }


@router.get("")
def list_groups(db: Session = Depends(get_db), admin: User = Depends(_require_admin)):
    return [_group_out(db, g) for g in db.query(Group).order_by(Group.id).all()]


@router.post("")
def create_group(payload: GroupIn, db: Session = Depends(get_db), admin: User = Depends(_require_admin)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "请填写组名")
    if db.query(Group).filter_by(name=name).first():
        raise HTTPException(400, "组名已存在")
    g = Group(name=name, description=payload.description, created_by=admin.id)
    db.add(g)
    db.commit()
    db.refresh(g)
    return _group_out(db, g)


@router.put("/{group_id}")
def update_group(group_id: int, payload: GroupIn, db: Session = Depends(get_db), admin: User = Depends(_require_admin)):
    g = db.get(Group, group_id)
    if not g:
        raise HTTPException(404, "用户组不存在")
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "请填写组名")
    clash = db.query(Group).filter(Group.name == name, Group.id != group_id).first()
    if clash:
        raise HTTPException(400, "组名已存在")
    g.name = name
    g.description = payload.description
    db.commit()
    return _group_out(db, g)


@router.delete("/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db), admin: User = Depends(_require_admin)):
    g = db.get(Group, group_id)
    if not g:
        raise HTTPException(404, "用户组不存在")
    db.query(GroupMember).filter_by(group_id=g.id).delete()
    db.query(TableShare).filter_by(group_id=g.id).delete()  # 组分享同步失效
    db.delete(g)
    db.commit()
    return {"ok": True}


@router.post("/{group_id}/members")
def add_member(group_id: int, payload: MemberIn, db: Session = Depends(get_db), admin: User = Depends(_require_admin)):
    g = db.get(Group, group_id)
    if not g:
        raise HTTPException(404, "用户组不存在")
    u = db.query(User).filter(User.username == payload.username.strip()).first()
    if not u:
        raise HTTPException(404, "用户不存在")
    if db.query(GroupMember).filter_by(group_id=g.id, user_id=u.id).first():
        raise HTTPException(400, "该用户已在组中")
    db.add(GroupMember(group_id=g.id, user_id=u.id))
    db.commit()
    return _group_out(db, g)


@router.delete("/{group_id}/members/{user_id}")
def remove_member(group_id: int, user_id: int, db: Session = Depends(get_db), admin: User = Depends(_require_admin)):
    m = db.query(GroupMember).filter_by(group_id=group_id, user_id=user_id).first()
    if not m:
        raise HTTPException(404, "成员不存在")
    db.delete(m)
    db.commit()
    return {"ok": True}
