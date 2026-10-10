"""套餐权益与配额校验：单点收口（设计文档 §4.7 / 定价文档 §8）。

所有配额/功能/订阅状态判定都走这里，router 与 engine 层只调用本模块：
- engine 层（dyn_engine / json_store / images）用 tenant_id 级函数（不感知用户）
- router 层可用 Context 上的 entitlements / writable（context.py 装配）
"""
import time
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    ImageFile, MetaTable, PlanEntitlement, Record, Subscription,
    Tenant, TenantMember, UsageCounter,
)

# 进程内 entitlement 缓存：{tenant_id: (过期时间戳, dict)}，平台后台改套餐后主动失效
_cache: dict[int, tuple[float, dict]] = {}
_CACHE_TTL = 60

# 配额键 → (usage_counters 字段, 单位倍率)。max_storage_mb 权益单位是 MB，usage 单位是字节
QUOTA_TO_USAGE = {
    "max_tables": ("table_count", 1),
    "max_rows": ("row_count", 1),
    "max_storage_mb": ("storage_bytes", 1024 * 1024),
    "max_seats": ("seat_count", 1),
}
QUOTA_LABELS = {
    "max_tables": "数据表数量",
    "max_rows": "记录总条数",
    "max_storage_mb": "存储空间",
    "max_seats": "成员席位",
}


def invalidate_cache(tenant_id: int | None = None) -> None:
    """平台后台改套餐/订阅后调用（None=全清）。"""
    if tenant_id is None:
        _cache.clear()
    else:
        _cache.pop(tenant_id, None)


# ---------- 订阅状态机（trial/active/grace/expired，定价文档 §6 + 权限文档 §4.7 企业过期态） ----------

def get_subscription(db: Session, tenant_id: int) -> Subscription | None:
    return db.query(Subscription).filter_by(tenant_id=tenant_id).first()


def evaluate_subscription(db: Session, sub: Subscription) -> str:
    """惰性状态迁移：到期 → grace（宽限 sub_grace_days 天）→ expired。
    只改对象不提交，随调用方事务落库；expires_at=NULL（free/legacy）永不到期。"""
    now = datetime.now()
    if sub.status in ("trial", "active") and sub.expires_at and sub.expires_at < now:
        days = get_entitlements(db, sub.tenant_id).get("sub_grace_days") or 7
        sub.status = "grace"
        sub.grace_until = sub.expires_at + timedelta(days=days)
    if sub.status == "grace" and sub.grace_until and sub.grace_until < now:
        sub.status = "expired"
    return sub.status


def tenant_writable(db: Session, tenant_id: int) -> bool:
    sub = get_subscription(db, tenant_id)
    if not sub:
        return True
    return evaluate_subscription(db, sub) != "expired"


def assert_tenant_writable(db: Session, tenant_id: int) -> None:
    """只读闸：expired 租户禁止一切写（读/导出/打印放行；权限配置保留，续费即恢复）。"""
    if tenant_id is None:
        return
    sub = get_subscription(db, tenant_id)
    if sub and evaluate_subscription(db, sub) == "expired":
        db.commit()  # 把 expired 迁移落库（403 会回滚事务，先提交状态）
        raise HTTPException(403, detail={
            "code": "tenant_expired",
            "message": "订阅已到期，当前为只读状态；数据完整保留，续费后自动恢复",
        })


# ---------- 权益读取 ----------

def get_entitlements(db: Session, tenant_id: int) -> dict:
    """当前订阅套餐的权益键值 dict（带 60s 进程内缓存）。无订阅 → 空 dict（全不限）。"""
    hit = _cache.get(tenant_id)
    if hit and hit[0] > time.time():
        return hit[1]
    sub = get_subscription(db, tenant_id)
    ents: dict = {}
    if sub:
        rows = db.query(PlanEntitlement).filter_by(plan_id=sub.plan_id).all()
        ents = {r.key: r.value for r in rows}
    _cache[tenant_id] = (time.time() + _CACHE_TTL, ents)
    return ents


def has_feature(db: Session, tenant_id: int, key: str) -> bool:
    return bool(get_entitlements(db, tenant_id).get(key))


def require_feature(db: Session, tenant_id: int, key: str) -> None:
    if not has_feature(db, tenant_id, key):
        raise HTTPException(403, detail={
            "code": "feature_not_available",
            "message": "当前套餐未包含该功能，升级后可用",
            "feature": key,
        })


# ---------- 配额闸（超限进宽限：登记起点+放行+提醒；宽限期满 403；回落自动清除） ----------

def _usage_row(db: Session, tenant_id: int) -> UsageCounter:
    row = db.query(UsageCounter).filter_by(tenant_id=tenant_id).first()
    if not row:
        try:
            with db.begin_nested():
                row = UsageCounter(tenant_id=tenant_id)
                db.add(row)
                db.flush()
        except IntegrityError:   # 并发撞行：重查
            row = db.query(UsageCounter).filter_by(tenant_id=tenant_id).first()
    return row


def _notify_tenant_admins(db: Session, tenant_id: int, title: str, content: str) -> None:
    try:
        from .notify import notify_user
        admins = db.query(TenantMember).filter_by(tenant_id=tenant_id, role="admin", status="active").all()
        for m in admins:
            notify_user(db, m.user_id, title, content, link="/billing")
    except Exception:  # noqa: BLE001 — 提醒失败不影响主流程
        pass


def check_quota(db: Session, tenant_id: int, key: str, delta: int = 1) -> None:
    """配额校验（宽限期模型，定价文档 §6）：
    - 限值 NULL/缺键 → 不限直接过；
    - 未超限 → 过（并清除该键残留的宽限记录）；
    - 首次超限 → 登记宽限起点、放行、提醒租户管理员；
    - 宽限中 → 放行；
    - 宽限期满 → 403 quota_exceeded（已有数据可读可导出，绝不删除）。
    delta 单位与 usage 字段一致（max_storage_mb 时传字节数）。"""
    if tenant_id is None:
        return
    ent = get_entitlements(db, tenant_id)
    limit = ent.get(key)
    if limit is None:
        return
    usage_field, multiplier = QUOTA_TO_USAGE[key]
    usage = _usage_row(db, tenant_id)
    current = getattr(usage, usage_field) or 0
    if current + delta <= limit * multiplier:
        graces = dict(usage.grace_json or {})
        if key in graces:
            graces.pop(key)
            usage.grace_json = graces
        return
    grace_days = ent.get("quota_grace_days") or 7
    graces = dict(usage.grace_json or {})
    start = graces.get(key)
    now = datetime.now()
    if start is None:
        graces[key] = now.isoformat(sep=" ")
        usage.grace_json = graces
        _notify_tenant_admins(
            db, tenant_id, "配额超限提醒",
            f"「{QUOTA_LABELS.get(key, key)}」已超当前套餐上限，{grace_days} 天宽限期内可正常使用；"
            f"请升级套餐或清理数据，宽限期满后将无法新增。")
        return
    if now < datetime.fromisoformat(start) + timedelta(days=grace_days):
        return  # 宽限中放行
    raise HTTPException(403, detail={
        "code": "quota_exceeded",
        "message": f"「{QUOTA_LABELS.get(key, key)}」已超上限且宽限期已满，请升级套餐或清理数据后再试",
        "quota": {"key": key, "limit": limit, "current": current},
    })


def bump_usage(db: Session, tenant_id: int | None, field: str, delta: int) -> None:
    """usage_counters 行级增减（field: table_count/row_count/storage_bytes/seat_count）。
    SQLite 单进程行级 UPDATE 安全；切 MySQL 多 worker 时改 INSERT ... ON DUPLICATE KEY UPDATE。"""
    if tenant_id is None or delta == 0:
        return
    col = getattr(UsageCounter, field)
    res = db.execute(
        sa_update(UsageCounter).where(UsageCounter.tenant_id == tenant_id).values(**{field: col + delta})
    )
    if res.rowcount:
        return
    try:
        with db.begin_nested():
            db.add(UsageCounter(tenant_id=tenant_id, **{field: max(delta, 0)}))
    except IntegrityError:   # 并发撞行：改为自增
        db.execute(
            sa_update(UsageCounter).where(UsageCounter.tenant_id == tenant_id).values(**{field: col + delta})
        )


# ---------- 全量校准（定时任务 + 迁移后初始化） ----------

def recalibrate_usage(db: Session, tenant_id: int | None = None) -> None:
    """按实数覆写 usage_counters：表数（active）/ 记录数（records + 物理表）/ 存储（图片）/ 席位。"""
    tenants = db.query(Tenant).all() if tenant_id is None else db.query(Tenant).filter_by(id=tenant_id).all()
    for tenant in tenants:
        tid = tenant.id
        table_count = db.query(func.count(MetaTable.id)).filter(
            MetaTable.tenant_id == tid, MetaTable.status == "active").scalar() or 0
        row_count = db.query(func.count(Record.id)).filter(Record.tenant_id == tid).scalar() or 0
        phys = db.query(MetaTable).filter(
            MetaTable.tenant_id == tid, MetaTable.storage_mode == "physical",
            MetaTable.status == "active").all()
        for mt in phys:
            try:
                row_count += db.execute(text(f"SELECT COUNT(*) FROM {mt.name}")).scalar() or 0
            except Exception:  # noqa: BLE001 — 物理表缺失不阻塞校准
                pass
        member_ids = select(TenantMember.user_id).where(
            TenantMember.tenant_id == tid, TenantMember.status.in_(("invited", "active")))
        storage = db.query(func.coalesce(func.sum(ImageFile.size), 0)).filter(
            ImageFile.uploader_id.in_(member_ids)).scalar() or 0
        seat_count = db.query(func.count(TenantMember.id)).filter(
            TenantMember.tenant_id == tid, TenantMember.status.in_(("invited", "active"))).scalar() or 0
        usage = _usage_row(db, tid)
        usage.table_count = table_count
        usage.row_count = row_count
        usage.storage_bytes = storage
        usage.seat_count = seat_count
        usage.calibrated_at = datetime.now()
    db.commit()
