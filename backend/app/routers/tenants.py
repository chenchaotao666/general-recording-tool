"""租户/工作空间：我的空间列表、切换、当前空间详情（套餐与用量页数据源）、个人升企业。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import UsageCounter, User
from ..services.tenancy import my_tenants
from ..utils.auth import get_current_user
from ..utils.context import Context, get_current_context
from .auth import _user_payload

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


class SwitchIn(BaseModel):
    tenant_id: int


@router.get("/mine")
def list_mine(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return my_tenants(db, user)


@router.post("/switch")
def switch(body: SwitchIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """切换工作空间：返回新租户下的 user payload，前端重存 grt_user / grt_tenant_id。"""
    payload = _user_payload(db, user, tenant_id=body.tenant_id)
    if not payload["tenant"] or payload["tenant"]["id"] != body.tenant_id:
        raise HTTPException(403, "不是该工作空间的成员")
    return payload


@router.get("/current")
def current(db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    """当前空间详情：套餐 + 权益 + 用量 + 订阅状态（套餐与用量页的数据源）。"""
    from ..models import Plan
    sub = ctx.subscription
    usage = db.query(UsageCounter).filter_by(tenant_id=ctx.tenant.id).first()
    ent = ctx.entitlements
    plan = db.get(Plan, sub.plan_id) if sub else None

    def quota(key: str, usage_val: int, multiplier: int = 1) -> dict:
        limit = ent.get(key)
        return {"limit": limit, "used": usage_val,
                "percent": round(usage_val / (limit * multiplier) * 100, 1) if limit else None}

    return {
        "tenant": {"id": ctx.tenant.id, "name": ctx.tenant.name, "type": ctx.tenant.type},
        "plan": {
            "code": plan.code, "name": plan.name, "audience": plan.audience,
            "price_monthly": plan.price_monthly, "price_yearly": plan.price_yearly,
        } if plan else None,
        "subscription": {
            "status": sub.status if sub else "active",
            "seats": sub.seats if sub else 1,
            "started_at": sub.started_at.isoformat(sep=" ") if sub and sub.started_at else None,
            "expires_at": sub.expires_at.isoformat(sep=" ") if sub and sub.expires_at else None,
            "grace_until": sub.grace_until.isoformat(sep=" ") if sub and sub.grace_until else None,
            "grace_remaining_days": ctx.grace_remaining_days,
        },
        "entitlements": ent,
        "usage": {
            "tables": quota("max_tables", usage.table_count if usage else 0),
            "rows": quota("max_rows", usage.row_count if usage else 0),
            "storage": quota("max_storage_mb", usage.storage_bytes if usage else 0, 1024 * 1024),
            "seats": quota("max_seats", usage.seat_count if usage else 0),
        },
        "writable": ctx.writable,
        "my_role": ctx.membership.role if ctx.membership else ("admin" if ctx.is_platform_admin else None),
    }


@router.post("/upgrade-to-enterprise")
def upgrade_to_enterprise(db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    """个人版一键升级企业版：type 翻转，数据不动（定价文档 §3）；套餐由平台超管另行调整。"""
    if ctx.tenant.type != "personal":
        raise HTTPException(400, "仅个人版空间可升级")
    if not ctx.membership or ctx.membership.role != "admin":
        raise HTTPException(403, "仅空间所有者可升级")
    ctx.tenant.type = "enterprise"
    db.commit()
    return {"ok": True, "tenant": {"id": ctx.tenant.id, "name": ctx.tenant.name, "type": "enterprise"}}
