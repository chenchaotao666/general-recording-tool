"""站内通知（按接收人隔离，admin 也不例外）。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Notification, User
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/notify", tags=["notify"])


class ReadIn(BaseModel):
    ids: list[int] | None = None
    all: bool = False


def _my_notifications(db: Session, user: User):
    return db.query(Notification).filter(Notification.user_id == user.id)


def _out(db: Session, rows) -> list[dict]:
    """通知输出。tenant_invitation 类附带 inv_status：
    invited（待处理，前端渲染 接受/拒绝）/ active（已接受）/ declined（membership 已删 = 已拒绝）。"""
    from ..models import TenantMember
    ref_ids = [n.ref_id for n in rows if n.ref_type == "tenant_invitation" and n.ref_id]
    status_map = {}
    if ref_ids:
        status_map = dict(db.query(TenantMember.id, TenantMember.status)
                          .filter(TenantMember.id.in_(ref_ids)).all())
    out = []
    for n in rows:
        d = {
            "id": n.id, "title": n.title, "content": n.content, "link": n.link,
            "ref_type": n.ref_type, "ref_id": n.ref_id,
            "read": n.read, "created_at": n.created_at.isoformat(sep=" ") if n.created_at else None,
        }
        if n.ref_type == "tenant_invitation":
            d["inv_status"] = status_map.get(n.ref_id, "declined")
        out.append(d)
    return out


@router.get("")
def list_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = _my_notifications(db, user).order_by(Notification.id.desc()).limit(30).all()
    return _out(db, rows)


@router.get("/unread_count")
def unread_count(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"count": _my_notifications(db, user).filter_by(read=False).count()}


@router.get("/page")
def list_notifications_page(page: int = 1, page_size: int = 20, only_unread: bool = False,
                            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """通知页（Web 端）：分页 + 只看未读。旧的 GET /notify（最近 30 条数组）保留给小程序/铃铛。"""
    q = _my_notifications(db, user)
    if only_unread:
        q = q.filter_by(read=False)
    total = q.count()
    page_size = min(max(page_size, 1), 100)
    rows = (
        q.order_by(Notification.id.desc())
        .offset((max(page, 1) - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"total": total, "items": _out(db, rows)}


@router.post("/read")
def mark_read(payload: ReadIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = _my_notifications(db, user).filter_by(read=False)
    if not payload.all and payload.ids:
        q = q.filter(Notification.id.in_(payload.ids))
    q.update({Notification.read: True}, synchronize_session=False)
    db.commit()
    return {"ok": True}


class DeleteIn(BaseModel):
    ids: list[int] | None = None
    read_only: bool = False   # True = 清空全部已读


@router.post("/delete")
def delete_notifications(payload: DeleteIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """删除通知：按 id 列表或「清空已读」。两个条件都不给时空跑（防止误清空）。"""
    q = _my_notifications(db, user)
    if payload.read_only:
        q = q.filter_by(read=True)
    elif payload.ids:
        q = q.filter(Notification.id.in_(payload.ids))
    else:
        return {"ok": True, "deleted": 0}
    n = q.delete(synchronize_session=False)
    db.commit()
    return {"ok": True, "deleted": n}
