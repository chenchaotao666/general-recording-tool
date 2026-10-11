"""RBAC 权限判定：角色-权限关联查询。

角色取自租户成员关系（tenant_members.role）而非 users.role（P0 起 users.role 废弃）；
配额类数值权限（max_tables）已上移 plan_entitlements（见 services/entitlement.py）。
"""
from sqlalchemy.orm import Session

from ..models import Permission, Role, RolePermission, TenantMember, TenantRolePerm, User


def tenant_role(db: Session, user: User, tenant_id: int | None) -> str | None:
    """用户在指定租户内的角色 code（active membership）；平台超管视同 admin；非成员 → None。"""
    if tenant_id is None:
        return None
    if user.is_platform_admin:
        return "admin"
    m = db.query(TenantMember).filter_by(
        tenant_id=tenant_id, user_id=user.id, status="active").first()
    return m.role if m else None


def resolve_role(db: Session, role_code: str, tenant_id: int | None) -> Role | None:
    """code → 角色行：本租户自定义角色优先，回落全局内置角色。"""
    q = db.query(Role).filter(Role.code == role_code)
    if tenant_id is not None:
        r = q.filter(Role.tenant_id == tenant_id).first()
        if r:
            return r
    return q.filter(Role.tenant_id.is_(None)).first()


def has_perm(db: Session, role_code: str | None, code: str,
             tenant_id: int | None = None) -> bool:
    """角色在某租户内是否拥有某权限（admin 恒真）。
    判定：tenant_role_perms 覆盖行优先；无覆盖 → 全局 role_permissions。"""
    if role_code == "admin":
        return True
    if not role_code:
        return False
    role = resolve_role(db, role_code, tenant_id)
    perm = db.query(Permission).filter_by(code=code).first()
    if not role or not perm:
        return False
    if tenant_id is not None:
        ov = db.query(TenantRolePerm).filter_by(
            tenant_id=tenant_id, role_id=role.id, permission_id=perm.id).first()
        if ov is not None:
            return bool(ov.granted)
    return db.query(RolePermission).filter_by(
        role_id=role.id, permission_id=perm.id).first() is not None


def role_perms(db: Session, role_code: str | None,
               tenant_id: int | None = None) -> list[str]:
    """角色在某租户内拥有的权限 code 列表（admin 为全部权限），随登录信息下发给前端做按钮级控制。
    全局授权 ∪ 租户覆盖（granted=True 加入、False 移除）。"""
    if role_code == "admin":
        return [c for (c,) in db.query(Permission.code).all()]
    if not role_code:
        return []
    role = resolve_role(db, role_code, tenant_id)
    if not role:
        return []
    codes = {c for (c,) in db.query(Permission.code)
             .join(RolePermission, RolePermission.permission_id == Permission.id)
             .filter(RolePermission.role_id == role.id).all()}
    if tenant_id is not None:
        ovs = (db.query(TenantRolePerm, Permission)
               .join(Permission, TenantRolePerm.permission_id == Permission.id)
               .filter(TenantRolePerm.tenant_id == tenant_id,
                       TenantRolePerm.role_id == role.id).all())
        for ov, p in ovs:
            (codes.add if ov.granted else codes.discard)(p.code)
    return sorted(codes)
