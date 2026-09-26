"""用户组管理：admin 全权；普通成员可建组并管理自己创建的组（成员只能加好友）。组可被分享表（table_shares.group_id）。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Friendship, Group, GroupMember, TableShare, User
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/groups", tags=["groups"])


class GroupIn(BaseModel):
    name: str
    description: str | None = None


class MemberIn(BaseModel):
    username: str


def _get_manageable(db: Session, group_id: int, user: User) -> Group:
    """admin 或组创建者才能管理（改/删/增减成员）。"""
    g = db.get(Group, group_id)
    if not g:
        raise HTTPException(404, "用户组不存在")
    if user.role != "admin" and g.created_by != user.id:
        raise HTTPException(403, "只有组创建者或管理员可以管理该组")
    return g


def _is_friend(db: Session, a: int, b: int) -> bool:
    return db.query(Friendship).filter(
        Friendship.status == "accepted",
        or_(
            and_(Friendship.requester_id == a, Friendship.addressee_id == b),
            and_(Friendship.requester_id == b, Friendship.addressee_id == a),
        ),
    ).first() is not None


@router.get("/mine")
def list_my_groups(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """分享对话框的组下拉数据源：普通用户只列自己所在的组，admin 可列全部（后端约束对 admin 豁免）。"""
    if user.role == "admin":
        rows = db.query(Group).order_by(Group.id).all()
    else:
        rows = (
            db.query(Group)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .filter(GroupMember.user_id == user.id)
            .order_by(Group.id)
            .all()
        )
    return [
        {
            "id": g.id, "name": g.name, "description": g.description,
            "member_count": db.query(GroupMember).filter_by(group_id=g.id).count(),
        }
        for g in rows
    ]


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
def list_groups(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """admin 看全部；普通成员看自己创建的 + 自己所在的组（后者只读，can_manage=False）。"""
    rows = db.query(Group).order_by(Group.id).all()
    if user.role != "admin":
        my_ids = {m.group_id for m in db.query(GroupMember).filter_by(user_id=user.id).all()}
        rows = [g for g in rows if g.created_by == user.id or g.id in my_ids]
    return [
        {**_group_out(db, g), "can_manage": user.role == "admin" or g.created_by == user.id}
        for g in rows
    ]


@router.post("")
def create_group(payload: GroupIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "请填写组名")
    if db.query(Group).filter_by(name=name).first():
        raise HTTPException(400, "组名已存在")
    g = Group(name=name, description=payload.description, created_by=user.id)
    db.add(g)
    db.commit()
    db.refresh(g)
    # 创建者自动入组：分享的组下拉（/groups/mine 按成员关系取）才能看到自建的组
    db.add(GroupMember(group_id=g.id, user_id=user.id))
    db.commit()
    return _group_out(db, g)


@router.put("/{group_id}")
def update_group(group_id: int, payload: GroupIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    g = _get_manageable(db, group_id, user)
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
def delete_group(group_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    g = _get_manageable(db, group_id, user)
    db.query(GroupMember).filter_by(group_id=g.id).delete()
    db.query(TableShare).filter_by(group_id=g.id).delete()  # 组分享同步失效
    db.delete(g)
    db.commit()
    return {"ok": True}


@router.post("/{group_id}/members")
def add_member(group_id: int, payload: MemberIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    g = _get_manageable(db, group_id, user)
    u = db.query(User).filter(User.username == payload.username.strip()).first()
    if not u:
        raise HTTPException(404, "用户不存在")
    # 普通成员只能把好友加进组（admin 不受限）
    if user.role != "admin" and u.id != user.id and not _is_friend(db, user.id, u.id):
        raise HTTPException(400, "只能把好友加入用户组（先到「好友」页添加对方）")
    if db.query(GroupMember).filter_by(group_id=g.id, user_id=u.id).first():
        raise HTTPException(400, "该用户已在组中")
    db.add(GroupMember(group_id=g.id, user_id=u.id))
    db.commit()
    return _group_out(db, g)


@router.delete("/{group_id}/members/{user_id}")
def remove_member(group_id: int, user_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_manageable(db, group_id, user)
    m = db.query(GroupMember).filter_by(group_id=group_id, user_id=user_id).first()
    if not m:
        raise HTTPException(404, "成员不存在")
    db.delete(m)
    db.commit()
    return {"ok": True}
