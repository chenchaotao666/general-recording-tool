"""租户上下文：每个请求解析当前工作空间（X-Tenant-Id 头 / ?tenant_id= / 默认个人租户）。

JWT 只含 uid 不动；租户选择走请求头，切换工作空间无需重签 token，
被移出租户立即生效（每请求实时校验 membership）。
"""
from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Subscription, Tenant, TenantMember, User
from ..services import entitlement
from .auth import get_current_user


@dataclass
class Context:
    user: User
    tenant: Tenant
    membership: TenantMember | None       # None=平台超管运维通道（视同租户 admin）
    subscription: Subscription | None
    entitlements: dict
    is_platform_admin: bool
    is_tenant_admin: bool
    writable: bool                        # 订阅未过期（expired=只读）
    grace_remaining_days: int | None      # status=grace 时的剩余宽限天数

    def has_feature(self, key: str) -> bool:
        return bool(self.entitlements.get(key))


def _resolve_membership(db: Session, user: User, tenant_id: int) -> TenantMember | None:
    return db.query(TenantMember).filter_by(
        tenant_id=tenant_id, user_id=user.id, status="active").first()


def get_current_context(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    x_tenant_id: str = Header(default=""),
    tenant_id: int = 0,   # ?tenant_id= 下载场景（与 ?token= 并列）
) -> Context:
    tid = tenant_id or (int(x_tenant_id) if x_tenant_id.isdigit() else 0)
    if tid:
        tenant = db.get(Tenant, tid)
        if not tenant:
            raise HTTPException(404, "工作空间不存在")
        membership = _resolve_membership(db, user, tid)
        if membership is None and not user.is_platform_admin:
            raise HTTPException(403, "不是该工作空间的成员")
    else:
        # 默认个人租户；没有则任取一个 active membership（兼容纯企业成员）
        membership = (
            db.query(TenantMember).join(Tenant, TenantMember.tenant_id == Tenant.id)
            .filter(TenantMember.user_id == user.id, TenantMember.status == "active",
                    Tenant.type == "personal")
            .first()
        ) or db.query(TenantMember).filter_by(user_id=user.id, status="active").first()
        if membership is None:
            raise HTTPException(403, "当前账号不属于任何工作空间")
        tenant = db.get(Tenant, membership.tenant_id)

    sub = entitlement.get_subscription(db, tenant.id)
    if sub:
        entitlement.evaluate_subscription(db, sub)   # 惰性状态迁移，随请求事务落库
        db.commit()
    status = sub.status if sub else "active"
    grace_days = None
    if status == "grace" and sub and sub.grace_until:
        grace_days = max((sub.grace_until - datetime.now()).days + 1, 0)
    is_platform = bool(user.is_platform_admin)
    is_tenant_admin = is_platform or (membership is not None and membership.role == "admin")
    return Context(
        user=user, tenant=tenant, membership=membership, subscription=sub,
        entitlements=entitlement.get_entitlements(db, tenant.id),
        is_platform_admin=is_platform, is_tenant_admin=is_tenant_admin,
        writable=status != "expired", grace_remaining_days=grace_days,
    )


def require_tenant_admin(ctx: Context = Depends(get_current_context)) -> Context:
    if not ctx.is_tenant_admin:
        raise HTTPException(403, "需要工作空间管理员权限")
    return ctx


def require_platform_admin(ctx: Context = Depends(get_current_context)) -> Context:
    if not ctx.is_platform_admin:
        raise HTTPException(403, "需要平台管理员权限")
    return ctx
