"""RBAC 权限判定：角色-权限关联查询。admin 为代码级超级角色，直接放行。"""
from sqlalchemy.orm import Session

from ..models import Permission, Role, RolePermission, User


def _role_perm_row(db: Session, user: User, code: str) -> RolePermission | None:
    return (
        db.query(RolePermission)
        .join(Role, RolePermission.role_id == Role.id)
        .join(Permission, RolePermission.permission_id == Permission.id)
        .filter(Role.code == user.role, Permission.code == code)
        .first()
    )


def has_perm(db: Session, user: User, code: str) -> bool:
    """用户是否拥有某权限（admin 恒真）"""
    if user.role == "admin":
        return True
    return _role_perm_row(db, user, code) is not None


def user_perms(db: Session, user: User) -> list[str]:
    """用户角色拥有的权限 code 列表（admin 为全部权限），随登录信息下发给前端做按钮级控制"""
    q = (
        db.query(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, RolePermission.role_id == Role.id)
    )
    if user.role != "admin":
        q = q.filter(Role.code == user.role)
    return [code for (code,) in q.all()]


def perm_value(db: Session, user: User, code: str) -> int | None:
    """数值型权限的值（如 max_tables）；未配置或 admin → None（不限）"""
    if user.role == "admin":
        return None
    row = _role_perm_row(db, user, code)
    return row.value if row else None
