"""RBAC 权限判定：角色-权限关联查询。

角色取自租户成员关系（tenant_members.role）而非 users.role（P0 起 users.role 废弃）；
配额类数值权限（max_tables）已上移 plan_entitlements（见 services/entitlement.py）。
"""
from sqlalchemy.orm import Session

from ..models import Permission, Role, RolePermission, TenantMember, User


def tenant_role(db: Session, user: User, tenant_id: int | None) -> str | None:
    """用户在指定租户内的角色 code（active membership）；平台超管视同 admin；非成员 → None。"""
    if tenant_id is None:
        return None
    if user.is_platform_admin:
        return "admin"
    m = db.query(TenantMember).filter_by(
        tenant_id=tenant_id, user_id=user.id, status="active").first()
    return m.role if m else None


def _role_perm_row(db: Session, role_code: str, code: str) -> RolePermission | None:
    return (
        db.query(RolePermission)
        .join(Role, RolePermission.role_id == Role.id)
        .join(Permission, RolePermission.permission_id == Permission.id)
        .filter(Role.code == role_code, Permission.code == code)
        .first()
    )


def has_perm(db: Session, role_code: str | None, code: str) -> bool:
    """角色是否拥有某权限（admin 恒真）"""
    if role_code == "admin":
        return True
    if not role_code:
        return False
    return _role_perm_row(db, role_code, code) is not None


def role_perms(db: Session, role_code: str | None) -> list[str]:
    """角色拥有的权限 code 列表（admin 为全部权限），随登录信息下发给前端做按钮级控制"""
    q = (
        db.query(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, RolePermission.role_id == Role.id)
    )
    if role_code != "admin":
        q = q.filter(Role.code == role_code)
    return [code for (code,) in q.all()]
