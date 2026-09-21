"""站内通知。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Notification

router = APIRouter(prefix="/api/notify", tags=["notify"])


class ReadIn(BaseModel):
    ids: list[int] | None = None
    all: bool = False


@router.get("")
def list_notifications(db: Session = Depends(get_db)):
    rows = db.query(Notification).order_by(Notification.id.desc()).limit(30).all()
    return [
        {
            "id": n.id, "title": n.title, "content": n.content, "link": n.link,
            "read": n.read, "created_at": n.created_at.isoformat(sep=" ") if n.created_at else None,
        }
        for n in rows
    ]


@router.get("/unread_count")
def unread_count(db: Session = Depends(get_db)):
    return {"count": db.query(Notification).filter_by(read=False).count()}


@router.post("/read")
def mark_read(payload: ReadIn, db: Session = Depends(get_db)):
    q = db.query(Notification).filter_by(read=False)
    if not payload.all and payload.ids:
        q = q.filter(Notification.id.in_(payload.ids))
    q.update({Notification.read: True}, synchronize_session=False)
    db.commit()
    return {"ok": True}
