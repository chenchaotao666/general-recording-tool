"""待接受分享（接收者侧）：pending 列表、接受/拒绝。直发分享需对方确认后才生效。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import MetaTable, TableShare, User
from ..services.notify import notify_user
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/shares", tags=["shares"])


@router.get("/pending")
def list_pending(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """我收到的、待确认的直发分享。"""
    rows = (
        db.query(TableShare)
        .filter(TableShare.user_id == user.id, TableShare.status == "pending")
        .order_by(TableShare.id.desc())
        .all()
    )
    out = []
    for s in rows:
        mt = db.get(MetaTable, s.table_id)
        if not mt:
            continue
        owner = db.get(User, mt.owner_id) if mt.owner_id else None
        out.append({
            "id": s.id, "table_id": mt.id, "table_label": mt.label,
            "owner_label": owner.username if owner else "",
            "can_view": s.can_view, "can_create": s.can_create,
            "can_edit": s.can_edit, "can_delete": s.can_delete,
            "created_at": s.created_at.isoformat(sep=" ") if s.created_at else None,
        })
    return out


def _respond(db: Session, share_id: int, user: User, action: str) -> dict:
    s = db.get(TableShare, share_id)
    if not s or s.user_id != user.id or s.status != "pending":
        raise HTTPException(404, "分享不存在")
    mt = db.get(MetaTable, s.table_id)
    label = mt.label if mt else "数据表"
    s.status = "accepted" if action == "accept" else "rejected"
    verb = "接受了" if action == "accept" else "拒绝了"
    notify_user(db, s.shared_by, "分享已被" + ("接受" if action == "accept" else "拒绝"),
                f"{user.username} {verb}你对「{label}」的分享", link="/tables")
    db.commit()
    return {"ok": True, "status": s.status}


@router.post("/{share_id}/accept")
def accept_share(share_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    return _respond(db, share_id, user, "accept")


@router.post("/{share_id}/reject")
def reject_share(share_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    return _respond(db, share_id, user, "reject")
