"""好友体系（申请-同意制）：申请、接受/拒绝、好友列表、删除。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Friendship, GroupMember, User
from ..schemas import FriendRequestIn
from ..services.notify import notify_user
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/friends", tags=["friends"])


def _pair_filter(a_id: int, b_id: int):
    """两个用户之间的好友记录（任一方向）。"""
    return or_(
        and_(Friendship.requester_id == a_id, Friendship.addressee_id == b_id),
        and_(Friendship.requester_id == b_id, Friendship.addressee_id == a_id),
    )


def is_friend(db: Session, a_id: int, b_id: int) -> bool:
    return (
        db.query(Friendship)
        .filter(Friendship.status == "accepted", _pair_filter(a_id, b_id))
        .first()
        is not None
    )


def same_group(db: Session, a_id: int, b_id: int) -> bool:
    """两人是否同在一个用户组。"""
    my_groups = [g.group_id for g in db.query(GroupMember).filter_by(user_id=a_id).all()]
    if not my_groups:
        return False
    return (
        db.query(GroupMember)
        .filter(GroupMember.user_id == b_id, GroupMember.group_id.in_(my_groups))
        .first()
        is not None
    )


def _friend_out(db: Session, f: Friendship, me_id: int) -> dict:
    other_id = f.addressee_id if f.requester_id == me_id else f.requester_id
    other = db.get(User, other_id)
    return {
        "id": f.id, "user_id": other_id,
        "username": other.username if other else str(other_id),
        "since": f.responded_at.isoformat(sep=" ") if f.responded_at else None,
    }


@router.post("/request")
def request_friend(payload: FriendRequestIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    target = db.query(User).filter(User.username == payload.username.strip()).first()
    if not target:
        raise HTTPException(404, "用户不存在")
    if target.id == user.id:
        raise HTTPException(400, "不能加自己为好友")

    existing = db.query(Friendship).filter(_pair_filter(user.id, target.id)).first()
    if existing:
        if existing.status == "accepted":
            raise HTTPException(400, "对方已是好友")
        if existing.status == "pending":
            if existing.requester_id == target.id:
                # 互相申请：自动接受，直接成为好友
                existing.status = "accepted"
                existing.responded_at = datetime.now()
                notify_user(db, target.id, "好友申请", f"{user.username} 也申请加你为好友，已自动成为好友", link="/friends")
                db.commit()
                return {"id": existing.id, "status": "accepted"}
            raise HTTPException(400, "已申请，等待对方处理")
        db.delete(existing)  # rejected：删旧记录，以当前申请人为 requester 重建

    f = Friendship(requester_id=user.id, addressee_id=target.id)
    db.add(f)
    notify_user(db, target.id, "好友申请", f"{user.username} 申请加你为好友", link="/friends")
    db.commit()
    db.refresh(f)
    return {"id": f.id, "status": f.status}


@router.get("")
def list_friends(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        db.query(Friendship)
        .filter(
            Friendship.status == "accepted",
            or_(Friendship.requester_id == user.id, Friendship.addressee_id == user.id),
        )
        .order_by(Friendship.id.desc())
        .all()
    )
    return [_friend_out(db, f, user.id) for f in rows]


@router.get("/requests")
def list_requests(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        db.query(Friendship)
        .filter(Friendship.addressee_id == user.id, Friendship.status == "pending")
        .order_by(Friendship.id.desc())
        .all()
    )
    out = []
    for f in rows:
        requester = db.get(User, f.requester_id)
        out.append({
            "id": f.id,
            "user_id": f.requester_id,
            "username": requester.username if requester else str(f.requester_id),
            "created_at": f.created_at.isoformat(sep=" ") if f.created_at else None,
        })
    return out


def _respond(db: Session, friendship_id: int, user: User, action: str) -> dict:
    f = db.get(Friendship, friendship_id)
    if not f or f.addressee_id != user.id or f.status != "pending":
        raise HTTPException(404, "好友申请不存在")
    f.status = "accepted" if action == "accept" else "rejected"
    f.responded_at = datetime.now()
    if action == "accept":
        notify_user(db, f.requester_id, "好友申请已通过", f"{user.username} 接受了你的好友申请", link="/friends")
    else:
        notify_user(db, f.requester_id, "好友申请被拒绝", f"{user.username} 拒绝了你的好友申请", link="/friends")
    db.commit()
    return {"ok": True, "status": f.status}


@router.post("/{friendship_id}/accept")
def accept_request(friendship_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    return _respond(db, friendship_id, user, "accept")


@router.post("/{friendship_id}/reject")
def reject_request(friendship_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    return _respond(db, friendship_id, user, "reject")


@router.delete("/{friendship_id}")
def delete_friend(friendship_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    f = db.get(Friendship, friendship_id)
    if not f or f.status != "accepted" or user.id not in (f.requester_id, f.addressee_id):
        raise HTTPException(404, "好友不存在")
    db.delete(f)
    db.commit()
    return {"ok": True}
