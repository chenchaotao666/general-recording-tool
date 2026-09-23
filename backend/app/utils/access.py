"""表级权限：主人全权 / admin 全权 / 分享者按 table_shares 四开关 / 其余 404。

权限是请求的属性，检查放 router 层（Depends 工厂）；engine 层不感知用户
（调度器以无用户上下文执行，engine 掺用户概念会污染内部函数）。
"""
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import GroupMember, MetaTable, TableShare, User
from .auth import get_current_user

PERM_ATTR = {"view": "can_view", "create": "can_create", "edit": "can_edit", "delete": "can_delete"}


@dataclass
class TableAccess:
    table: MetaTable
    is_owner: bool
    is_admin: bool
    can_view: bool
    can_create: bool
    can_edit: bool
    can_delete: bool

    def my_perms(self) -> dict:
        return {
            "is_owner": self.is_owner, "is_admin": self.is_admin,
            "can_view": self.can_view, "can_create": self.can_create,
            "can_edit": self.can_edit, "can_delete": self.can_delete,
        }


def get_table_access(db: Session, table_id: int, user: User) -> TableAccess:
    """表不存在或无权限一律 404（不泄露表存在性）。直接分享与用户组分享取权限并集（就高）。"""
    mt = db.get(MetaTable, table_id)
    if not mt:
        raise HTTPException(404, "数据表不存在")
    if user.role == "admin":
        return TableAccess(mt, mt.owner_id == user.id, True, True, True, True, True)
    if mt.owner_id == user.id:
        return TableAccess(mt, True, False, True, True, True, True)
    shares = (
        db.query(TableShare)
        .outerjoin(GroupMember, TableShare.group_id == GroupMember.group_id)
        .filter(
            TableShare.table_id == table_id,
            or_(TableShare.user_id == user.id, GroupMember.user_id == user.id),
            TableShare.status == "accepted",   # 待确认/已拒绝的分享不产生权限
        )
        .all()
    )
    shares = [s for s in shares if s.can_view]
    if not shares:
        raise HTTPException(404, "数据表不存在")
    return TableAccess(
        mt, False, False, True,
        any(s.can_create for s in shares),
        any(s.can_edit for s in shares),
        any(s.can_delete for s in shares),
    )


def require_table(perm: str):
    """Depends 工厂：从 path 取 table_id，校验对应权限，返回 TableAccess。"""
    if perm not in PERM_ATTR:
        raise ValueError(f"未知权限：{perm}")

    def _dep(table_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> TableAccess:
        access = get_table_access(db, table_id, user)
        if not getattr(access, PERM_ATTR[perm]):
            raise HTTPException(404, "数据表不存在")
        return access

    return _dep


def check_owner_or_admin(obj_user_id: int | None, user: User) -> None:
    """规则/模板等对象级归属校验（无归属或归属他人且非 admin → 404）。"""
    if user.role == "admin":
        return
    if obj_user_id != user.id:
        raise HTTPException(404, "对象不存在")
