"""审计日志查询：租户 admin 查本租户（feature_audit 功能闸），平台超管可跨租户。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, MetaTable
from ..services import entitlement
from ..utils.context import Context, get_current_context

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(db: Session = Depends(get_db), ctx: Context = Depends(get_current_context),
               table_id: int = 0, user: str = "", action: str = "",
               start: str = "", end: str = "", page: int = 1, page_size: int = 50):
    if not ctx.is_tenant_admin:
        raise HTTPException(403, "需要工作空间管理员权限")
    entitlement.require_feature(db, ctx.tenant.id, "feature_audit")
    q = db.query(AuditLog).filter(AuditLog.tenant_id == ctx.tenant.id)
    if table_id:
        q = q.filter(AuditLog.table_id == table_id)
    if user:
        q = q.filter(AuditLog.user.like(f"%{user}%"))
    if action:
        q = q.filter(AuditLog.action == action)
    for param, op in ((start, "ge"), (end, "le")):
        if param:
            try:
                dt = datetime.fromisoformat(param.strip())
            except ValueError:
                raise HTTPException(400, "时间格式应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS")
            q = q.filter(AuditLog.created_at >= dt if op == "ge" else AuditLog.created_at <= dt)
    total = q.count()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    rows = q.order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    table_labels = dict(
        db.query(MetaTable.id, MetaTable.label)
        .filter(MetaTable.id.in_({r.table_id for r in rows if r.table_id} or [-1]))
        .all()
    )
    return {
        "total": total,
        "items": [{
            "id": r.id, "user": r.user, "action": r.action,
            "table_id": r.table_id, "table_label": table_labels.get(r.table_id, ""),
            "record_id": r.record_id, "before": r.before_json, "after": r.after_json,
            "created_at": r.created_at.isoformat(sep=" ") if r.created_at else None,
        } for r in rows],
    }
