"""计费相关定时任务（APScheduler 每日）：订阅状态巡检、配额宽限提醒、用量全量校准。
请求内的惰性判定（context.py / check_quota）是主路径，这里是兜底 + 每日提醒。"""
from datetime import datetime, timedelta

from ..database import SessionLocal
from ..models import Subscription, UsageCounter
from . import entitlement


def sweep_subscriptions() -> None:
    """每日：全量订阅状态机推进（到期→grace→expired）+ grace 期每日提醒。"""
    db = SessionLocal()
    try:
        for sub in db.query(Subscription).all():
            before = sub.status
            entitlement.evaluate_subscription(db, sub)
            if sub.status != before:
                db.commit()
            if sub.status == "grace" and sub.grace_until:
                days = max((sub.grace_until - datetime.now()).days + 1, 0)
                entitlement._notify_tenant_admins(
                    db, sub.tenant_id, "订阅到期宽限中",
                    f"工作空间订阅已到期，宽限期还剩 {days} 天；宽限期满后将进入只读状态，"
                    f"数据完整保留，续费即自动恢复。")
        db.commit()
    finally:
        db.close()


def remind_quota_grace() -> None:
    """每日：配额宽限中的租户每日提醒（禁新增的实时判定在 entitlement.check_quota）。"""
    db = SessionLocal()
    try:
        for usage in db.query(UsageCounter).all():
            graces = usage.grace_json or {}
            if not graces:
                continue
            ent = entitlement.get_entitlements(db, usage.tenant_id)
            now = datetime.now()
            for key, start_iso in graces.items():
                days_total = ent.get("quota_grace_days") or 7
                try:
                    start = datetime.fromisoformat(start_iso)
                except (ValueError, TypeError):
                    continue
                remaining = (start + timedelta(days=days_total) - now).days + 1
                label = entitlement.QUOTA_LABELS.get(key, key)
                if remaining > 0:
                    entitlement._notify_tenant_admins(
                        db, usage.tenant_id, "配额宽限提醒",
                        f"「{label}」已超套餐上限，宽限期还剩 {remaining} 天，请升级套餐或清理数据。")
                else:
                    entitlement._notify_tenant_admins(
                        db, usage.tenant_id, "配额宽限已到期",
                        f"「{label}」宽限期已满，现已无法新增；升级套餐或清理数据后自动恢复。")
        db.commit()
    finally:
        db.close()


def calibrate_usage() -> None:
    """每日：usage_counters 全量校准（写路径增减是缓存，这里按实数覆写纠偏）。"""
    db = SessionLocal()
    try:
        entitlement.recalibrate_usage(db)
    finally:
        db.close()
