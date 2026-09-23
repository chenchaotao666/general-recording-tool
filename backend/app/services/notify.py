"""站内通知写入的统一入口（由调用方负责 commit，与 act_notify 的约定一致）。"""
from sqlalchemy.orm import Session

from ..models import Notification


def notify_user(db: Session, user_id: int, title: str, content: str, link: str | None = None) -> None:
    db.add(Notification(user_id=user_id, title=title, content=content, link=link))
