"""租户开通/升级的公共逻辑（注册、平台后台、个人升企业共用）。"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Plan, Subscription, Tenant, TenantMember, UsageCounter, User


def create_tenant(db: Session, owner: User, name: str, type: str = "personal",
                  plan_code: str = "free") -> Tenant:
    """单事务开租户：Tenant +  owner admin membership + 订阅 + 用量行。"""
    plan = db.query(Plan).filter_by(code=plan_code).first()
    if not plan:
        raise HTTPException(500, f"套餐不存在：{plan_code}")
    tenant = Tenant(name=name, type=type, owner_user_id=owner.id, created_at=datetime.now())
    db.add(tenant)
    db.flush()
    db.add(TenantMember(tenant_id=tenant.id, user_id=owner.id, role="admin",
                        status="active", created_at=datetime.now()))
    db.add(Subscription(tenant_id=tenant.id, plan_id=plan.id, seats=1,
                        status="active", started_at=datetime.now()))
    db.add(UsageCounter(tenant_id=tenant.id, seat_count=1))
    return tenant


def my_tenants(db: Session, user: User) -> list[dict]:
    """用户的全部工作空间（active membership），供顶栏切换器。"""
    rows = (
        db.query(TenantMember, Tenant)
        .join(Tenant, TenantMember.tenant_id == Tenant.id)
        .filter(TenantMember.user_id == user.id, TenantMember.status == "active")
        .order_by(TenantMember.id)
        .all()
    )
    return [{"id": t.id, "name": t.name, "type": t.type, "role": m.role} for m, t in rows]


def default_tenant_id(db: Session, user: User) -> int | None:
    """默认工作空间：个人租户优先，其次任一 active membership。"""
    rows = (
        db.query(TenantMember, Tenant)
        .join(Tenant, TenantMember.tenant_id == Tenant.id)
        .filter(TenantMember.user_id == user.id, TenantMember.status == "active")
        .order_by(TenantMember.id)
        .all()
    )
    for m, t in rows:
        if t.type == "personal":
            return t.id
    return rows[0][1].id if rows else None
