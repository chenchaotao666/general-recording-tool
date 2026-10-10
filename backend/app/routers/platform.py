"""平台管理（平台超管专用）：租户列表/代客改订阅（收银台）、套餐配置台、开租户。
支付未接入，套餐与定价变更全部在这里操作（套餐参数库表驱动，可配置）。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Plan, PlanEntitlement, Subscription, Tenant, TenantMember,
    UsageCounter, User,
)
from ..services import entitlement
from ..services.dyn_engine import log_audit
from ..services.tenancy import create_tenant
from ..utils.context import Context, require_platform_admin

router = APIRouter(prefix="/api/platform", tags=["platform"])


# ---------- 租户与订阅（收银台） ----------

class SubscriptionIn(BaseModel):
    plan_code: str | None = None
    seats: int | None = None
    expires_at: str | None = None   # "YYYY-MM-DD" 或 "YYYY-MM-DD HH:MM:SS"；空串=清为永不到期
    status: str | None = None       # trial / active / grace / expired


class TenantCreateIn(BaseModel):
    username: str
    name: str
    type: str = "enterprise"        # enterprise / private
    plan_code: str = "ent_standard"


def _tenant_out(db: Session, t: Tenant) -> dict:
    sub = db.query(Subscription).filter_by(tenant_id=t.id).first()
    plan = db.get(Plan, sub.plan_id) if sub else None
    usage = db.query(UsageCounter).filter_by(tenant_id=t.id).first()
    owner = db.get(User, t.owner_user_id) if t.owner_user_id else None
    member_count = db.query(TenantMember).filter_by(tenant_id=t.id).count()
    return {
        "id": t.id, "name": t.name, "type": t.type,
        "owner": owner.username if owner else None,
        "member_count": member_count,
        "subscription": {
            "plan_code": plan.code if plan else None, "plan_name": plan.name if plan else None,
            "status": sub.status if sub else None, "seats": sub.seats if sub else None,
            "expires_at": sub.expires_at.isoformat(sep=" ") if sub and sub.expires_at else None,
        },
        "usage": {
            "table_count": usage.table_count if usage else 0,
            "row_count": usage.row_count if usage else 0,
            "storage_bytes": usage.storage_bytes if usage else 0,
            "seat_count": usage.seat_count if usage else 0,
        },
        "created_at": t.created_at.isoformat(sep=" ") if t.created_at else None,
    }


@router.get("/tenants")
def list_tenants(db: Session = Depends(get_db), ctx: Context = Depends(require_platform_admin)):
    rows = db.query(Tenant).order_by(Tenant.id).all()
    return [_tenant_out(db, t) for t in rows]


@router.post("/tenants")
def create_tenant_api(body: TenantCreateIn, db: Session = Depends(get_db),
                      ctx: Context = Depends(require_platform_admin)):
    """代开租户（私有化初始化/企业客户开通）。owner 须为已注册用户。"""
    if body.type not in ("enterprise", "private", "personal"):
        raise HTTPException(400, "type 仅支持 personal / enterprise / private")
    owner = db.query(User).filter(User.username == body.username.strip()).first()
    if not owner:
        raise HTTPException(404, "用户不存在（请先注册 owner 账号）")
    tenant = create_tenant(db, owner, name=body.name, type=body.type, plan_code=body.plan_code)
    log_audit(db, "create_tenant", None, after={"tenant_id": tenant.id, "name": body.name,
              "type": body.type, "plan": body.plan_code}, user=ctx.user.username)
    db.commit()
    return _tenant_out(db, tenant)


@router.put("/tenants/{tenant_id}/subscription")
def set_subscription(tenant_id: int, body: SubscriptionIn, db: Session = Depends(get_db),
                     ctx: Context = Depends(require_platform_admin)):
    """代客续费/改档：改套餐、席位、到期日、状态。续费（expires_at 改到未来）自动恢复 active。"""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "租户不存在")
    sub = db.query(Subscription).filter_by(tenant_id=tenant_id).first()
    if not sub:
        raise HTTPException(404, "租户无订阅")
    before = {"plan_id": sub.plan_id, "seats": sub.seats, "status": sub.status,
              "expires_at": sub.expires_at.isoformat(sep=" ") if sub.expires_at else None}
    if body.plan_code is not None:
        plan = db.query(Plan).filter_by(code=body.plan_code).first()
        if not plan:
            raise HTTPException(404, f"套餐不存在：{body.plan_code}")
        sub.plan_id = plan.id
    if body.seats is not None:
        sub.seats = body.seats
    if body.expires_at is not None:
        if body.expires_at.strip() == "":
            sub.expires_at = None
        else:
            try:
                sub.expires_at = datetime.fromisoformat(body.expires_at.strip())
            except ValueError:
                raise HTTPException(400, "expires_at 格式应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS")
    if body.status is not None:
        if body.status not in ("trial", "active", "grace", "expired"):
            raise HTTPException(400, "status 仅支持 trial / active / grace / expired")
        sub.status = body.status
    # 续费恢复：到期日改到未来且当前 grace/expired → 回 active
    if sub.status in ("grace", "expired") and (sub.expires_at is None or sub.expires_at > datetime.now()):
        sub.status = "active"
        sub.grace_until = None
    log_audit(db, "subscription_change", None, tenant_id=tenant_id,
              before=before,
              after={"plan_id": sub.plan_id, "seats": sub.seats, "status": sub.status,
                     "expires_at": sub.expires_at.isoformat(sep=" ") if sub.expires_at else None},
              user=ctx.user.username)
    entitlement.invalidate_cache(tenant_id)
    db.commit()
    return _tenant_out(db, tenant)


# ---------- 套餐配置台（价格/配额/功能/宽限期全部可配置） ----------

class PlanIn(BaseModel):
    code: str
    name: str
    audience: str = "individual"      # individual / enterprise / private
    price_monthly: int = 0            # 分
    price_yearly: int = 0             # 分
    sort: int = 0
    is_public: bool = True


class PlanUpdateIn(BaseModel):
    name: str | None = None
    audience: str | None = None
    price_monthly: int | None = None
    price_yearly: int | None = None
    sort: int | None = None
    is_public: bool | None = None


class EntitlementsIn(BaseModel):
    entitlements: dict[str, int | None]   # 全量替换该套餐的权益键值（value=null 表示不限）


def _plan_out(db: Session, p: Plan) -> dict:
    ents = {e.key: e.value for e in db.query(PlanEntitlement).filter_by(plan_id=p.id).all()}
    return {
        "id": p.id, "code": p.code, "name": p.name, "audience": p.audience,
        "price_monthly": p.price_monthly, "price_yearly": p.price_yearly,
        "sort": p.sort, "is_public": p.is_public, "entitlements": ents,
    }


@router.get("/plans")
def list_plans(db: Session = Depends(get_db), ctx: Context = Depends(require_platform_admin)):
    rows = db.query(Plan).order_by(Plan.sort, Plan.id).all()
    return [_plan_out(db, p) for p in rows]


@router.post("/plans")
def create_plan(body: PlanIn, db: Session = Depends(get_db),
                ctx: Context = Depends(require_platform_admin)):
    if db.query(Plan).filter_by(code=body.code).first():
        raise HTTPException(400, "套餐 code 已存在")
    if body.audience not in ("individual", "enterprise", "private"):
        raise HTTPException(400, "audience 仅支持 individual / enterprise / private")
    p = Plan(code=body.code, name=body.name, audience=body.audience,
             price_monthly=body.price_monthly, price_yearly=body.price_yearly,
             sort=body.sort, is_public=body.is_public, created_at=datetime.now())
    db.add(p)
    db.commit()
    return _plan_out(db, p)


@router.put("/plans/{plan_id}")
def update_plan(plan_id: int, body: PlanUpdateIn, db: Session = Depends(get_db),
                ctx: Context = Depends(require_platform_admin)):
    p = db.get(Plan, plan_id)
    if not p:
        raise HTTPException(404, "套餐不存在")
    for attr in ("name", "audience", "price_monthly", "price_yearly", "sort", "is_public"):
        v = getattr(body, attr)
        if v is not None:
            setattr(p, attr, v)
    entitlement.invalidate_cache()
    db.commit()
    return _plan_out(db, p)


@router.put("/plans/{plan_id}/entitlements")
def set_entitlements(plan_id: int, body: EntitlementsIn, db: Session = Depends(get_db),
                     ctx: Context = Depends(require_platform_admin)):
    """全量替换套餐权益（配额/功能开关/宽限天数）。改完即对全部订阅该套餐的租户生效。"""
    p = db.get(Plan, plan_id)
    if not p:
        raise HTTPException(404, "套餐不存在")
    db.query(PlanEntitlement).filter_by(plan_id=plan_id).delete()
    for key, value in body.entitlements.items():
        db.add(PlanEntitlement(plan_id=plan_id, key=key, value=value))
    log_audit(db, "plan_entitlements_change", None,
              after={"plan": p.code, "entitlements": body.entitlements}, user=ctx.user.username)
    entitlement.invalidate_cache()
    db.commit()
    return _plan_out(db, p)
