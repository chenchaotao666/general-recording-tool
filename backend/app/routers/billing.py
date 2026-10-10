"""自助计费：套餐选购 / 下单 / 支付（当前为模拟支付，点击即成功）/ 订单列表。
支付渠道接入点：pay_order 内的 TODO（届时替换为真实支付回调）。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Order, Plan, PlanEntitlement, Subscription, Tenant
from ..services import entitlement
from ..services.dyn_engine import log_audit
from ..utils.context import Context, require_tenant_admin

router = APIRouter(prefix="/api/billing", tags=["billing"])

# 企业版人数阶梯折扣（定价文档 §4：20-49 人 9 折、50 人以上 8 折）
SEAT_DISCOUNT_TIERS = [(50, 0.8), (20, 0.9)]


class OrderIn(BaseModel):
    plan_code: str
    seats: int = 1
    years: int = 1


def _audience_for(tenant_type: str) -> str:
    return {"personal": "individual", "enterprise": "enterprise", "private": "private"}[tenant_type]


def _seat_discount(seats: int) -> float:
    for threshold, discount in SEAT_DISCOUNT_TIERS:
        if seats >= threshold:
            return discount
    return 1.0


def _quote(plan: Plan, ents: dict, seats: int, years: int) -> int:
    """应付金额（分）。企业版按人/年 + 阶梯折扣；个人版按年。"""
    yearly = plan.price_yearly or 0
    if plan.audience == "enterprise":
        return int(yearly * seats * years * _seat_discount(seats))
    return yearly * years


def _plan_out(db: Session, p: Plan) -> dict:
    ents = {e.key: e.value for e in db.query(PlanEntitlement).filter_by(plan_id=p.id).all()}
    return {
        "code": p.code, "name": p.name, "audience": p.audience,
        "price_monthly": p.price_monthly, "price_yearly": p.price_yearly,
        "entitlements": ents,
    }


def _order_out(db: Session, o: Order) -> dict:
    plan = db.get(Plan, o.plan_id)
    return {
        "id": o.id, "plan_code": plan.code if plan else None,
        "plan_name": plan.name if plan else None,
        "seats": o.seats, "years": o.years, "amount": o.amount, "status": o.status,
        "created_at": o.created_at.isoformat(sep=" ") if o.created_at else None,
        "paid_at": o.paid_at.isoformat(sep=" ") if o.paid_at else None,
    }


@router.get("/plans")
def available_plans(db: Session = Depends(get_db), ctx: Context = Depends(require_tenant_admin)):
    """当前租户可选购的套餐（仅上架档），含当前订阅标记。
    个人版空间：个人档 + 企业档都展示（购买企业档即自动升级为企业空间，无需单独"升级"动作）。"""
    if ctx.tenant.type == "personal":
        audiences = ("individual", "enterprise")
    else:
        audiences = (_audience_for(ctx.tenant.type),)
    rows = (db.query(Plan).filter(Plan.audience.in_(audiences), Plan.is_public == True)  # noqa: E712
            .order_by(Plan.sort, Plan.id).all())
    sub = ctx.subscription
    current_plan = db.get(Plan, sub.plan_id) if sub else None
    return {
        "plans": [_plan_out(db, p) for p in rows],
        "current_plan_code": current_plan.code if current_plan else None,
        "tenant_type": ctx.tenant.type,
    }


@router.post("/orders")
def create_order(body: OrderIn, db: Session = Depends(get_db), ctx: Context = Depends(require_tenant_admin)):
    plan = db.query(Plan).filter_by(code=body.plan_code, is_public=True).first()
    allowed = ("individual", "enterprise") if ctx.tenant.type == "personal" else (_audience_for(ctx.tenant.type),)
    if not plan or plan.audience not in allowed:
        raise HTTPException(404, "套餐不存在或不适用于当前空间类型")
    seats, years = max(body.seats, 1), min(max(body.years, 1), 5)
    if plan.audience == "individual":
        seats = 1
    else:
        ent = {e.key: e.value for e in db.query(PlanEntitlement).filter_by(plan_id=plan.id).all()}
        min_seats = ent.get("min_seats") or 1
        if seats < min_seats:
            raise HTTPException(400, f"该套餐最低 {min_seats} 席起购")
        max_seats = ent.get("max_seats")
        if max_seats and seats > max_seats:
            raise HTTPException(400, f"该套餐最多 {max_seats} 席")
    amount = _quote(plan, {}, seats, years)
    order = Order(tenant_id=ctx.tenant.id, plan_id=plan.id, seats=seats, years=years,
                  amount=amount, created_by=ctx.user.id)
    db.add(order)
    db.commit()
    return _order_out(db, order)


@router.post("/orders/{order_id}/pay")
def pay_order(order_id: int, db: Session = Depends(get_db), ctx: Context = Depends(require_tenant_admin)):
    """模拟支付：点击即成功。接入真实支付时改为先生成支付单，此处由支付回调驱动。"""
    order = db.get(Order, order_id)
    if not order or order.tenant_id != ctx.tenant.id:
        raise HTTPException(404, "订单不存在")
    if order.status != "pending":
        raise HTTPException(400, "订单已支付或已取消")
    order.status = "paid"
    order.paid_at = datetime.now()

    # 订阅生效：换档 + 续期（未到期部分顺延累加）+ 状态恢复 active
    sub = entitlement.get_subscription(db, ctx.tenant.id)
    if not sub:
        sub = Subscription(tenant_id=ctx.tenant.id, plan_id=order.plan_id, seats=order.seats,
                           status="active", started_at=datetime.now())
        db.add(sub)
        db.flush()
    before = {"plan_id": sub.plan_id, "seats": sub.seats, "status": sub.status,
              "expires_at": sub.expires_at.isoformat(sep=" ") if sub.expires_at else None}
    base = sub.expires_at if sub.expires_at and sub.expires_at > datetime.now() else datetime.now()
    sub.plan_id = order.plan_id
    sub.seats = order.seats
    sub.expires_at = base + timedelta(days=365 * order.years)
    sub.status = "active"
    sub.grace_until = None
    # 购买企业档即升级：个人空间 → 企业空间（数据不动，成员邀请/协作子系统解锁）
    plan = db.get(Plan, order.plan_id)
    if plan and plan.audience == "enterprise" and ctx.tenant.type == "personal":
        ctx.tenant.type = "enterprise"
    log_audit(db, "subscription_change", None, tenant_id=ctx.tenant.id,
              before=before, after={"plan_id": sub.plan_id, "seats": sub.seats,
                                    "expires_at": sub.expires_at.isoformat(sep=" "),
                                    "order_id": order.id, "amount": order.amount},
              user=ctx.user.username)
    entitlement.invalidate_cache(ctx.tenant.id)
    db.commit()
    return _order_out(db, order)


@router.get("/orders")
def list_orders(db: Session = Depends(get_db), ctx: Context = Depends(require_tenant_admin)):
    rows = (db.query(Order).filter_by(tenant_id=ctx.tenant.id)
            .order_by(Order.id.desc()).limit(50).all())
    return [_order_out(db, o) for o in rows]
