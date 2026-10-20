"""智能表自动化路由（设计文档 §11、§16.2）：规则 CRUD / 启停 / 运行日志 / 手动运行。

权限：查看规则需表查看权；增删改与运行需表编辑权且内容权限 ≥ 可编辑。
"""
from datetime import date, datetime, time, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import SmartAutomation, SmartAutomationRun
from ..services import automation_engine, perm_service, scheduler
from ..utils.access import TableAccess, get_table_access, require_table
from ..utils.context import Context, get_current_context

router = APIRouter(prefix="/api/smart", tags=["smart-automation"])


def _run_out(r: SmartAutomationRun | None) -> dict | None:
    if not r:
        return None
    return {"id": r.id, "status": r.status, "error": r.error,
            "trigger_snapshot": r.trigger_snapshot or {}, "step_results": r.step_results or [],
            "started_at": r.started_at.isoformat(sep=" ") if r.started_at else None,
            "finished_at": r.finished_at.isoformat(sep=" ") if r.finished_at else None}


def _rule_out(db: Session, a: SmartAutomation) -> dict:
    last = (db.query(SmartAutomationRun).filter_by(rule_id=a.id)
            .order_by(SmartAutomationRun.id.desc()).first())
    return {"id": a.id, "table_id": a.table_id, "name": a.name, "enabled": bool(a.enabled),
            "trigger": a.trigger_config or {}, "actions": a.actions or [],
            "created_by": a.created_by,
            "updated_at": a.updated_at.isoformat(sep=" ") if a.updated_at else None,
            "last_run": _run_out(last)}


def _require_editor(db: Session, access: TableAccess) -> None:
    if not access.can_edit:
        raise HTTPException(403, "没有设置自动化的权限")
    eff = perm_service.effective_for_access(db, access)
    perm_service.require_level(eff, "EDIT", "没有设置自动化的权限")


def _get_rule(db: Session, aid: int, ctx: Context, edit: bool = False) -> tuple[SmartAutomation, TableAccess]:
    a = db.get(SmartAutomation, aid)
    if not a:
        raise HTTPException(404, "自动化不存在")
    access = get_table_access(db, a.table_id, ctx.user, ctx)
    if edit:
        _require_editor(db, access)
    return a, access


def _reload() -> None:
    try:
        scheduler.reload_jobs()
    except Exception:  # noqa: BLE001 — 调度器重载失败不影响规则保存
        pass


@router.get("/tables/{table_id}/automations")
def list_rules(table_id: int, db: Session = Depends(get_db),
               access: TableAccess = Depends(require_table("view"))):
    rows = db.query(SmartAutomation).filter_by(table_id=table_id).order_by(SmartAutomation.id).all()
    return {"automations": [_rule_out(db, a) for a in rows]}


@router.post("/tables/{table_id}/automations")
def create_rule(table_id: int, payload: dict, db: Session = Depends(get_db),
                access: TableAccess = Depends(require_table("edit"))):
    _require_editor(db, access)
    trig, actions = automation_engine.validate_rule(db, access.table, payload)
    a = SmartAutomation(table_id=table_id, tenant_id=access.table.tenant_id,
                        name=str(payload.get("name") or "自动化提醒").strip()[:200] or "自动化提醒",
                        enabled=payload.get("enabled", True) is not False,
                        trigger_config=trig, actions=actions, created_by=access.ctx.user.id)
    db.add(a)
    db.commit()
    db.refresh(a)
    if trig["type"] == "schedule":
        _reload()
    return {"automation": _rule_out(db, a)}


@router.get("/automations/{aid}")
def get_rule(aid: int, db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    a, _ = _get_rule(db, aid, ctx)
    return {"automation": _rule_out(db, a)}


@router.patch("/automations/{aid}")
def update_rule(aid: int, payload: dict, db: Session = Depends(get_db),
                ctx: Context = Depends(get_current_context)):
    a, access = _get_rule(db, aid, ctx, edit=True)
    was_schedule = (a.trigger_config or {}).get("type") == "schedule"
    enabled = bool(payload.get("enabled", a.enabled))
    if "trigger" in payload or "actions" in payload or enabled:
        trig, actions = automation_engine.validate_rule(db, access.table, {
            "trigger": payload.get("trigger", a.trigger_config), "actions": payload.get("actions", a.actions),
            "enabled": enabled})
        a.trigger_config, a.actions = trig, actions
    if "name" in payload:
        a.name = str(payload["name"] or "").strip()[:200] or a.name
    a.enabled = enabled
    db.commit()
    if was_schedule or (a.trigger_config or {}).get("type") == "schedule":
        _reload()
    return {"automation": _rule_out(db, a)}


@router.delete("/automations/{aid}")
def delete_rule(aid: int, db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    a, _ = _get_rule(db, aid, ctx, edit=True)
    was_schedule = (a.trigger_config or {}).get("type") == "schedule"
    db.query(SmartAutomationRun).filter_by(rule_id=a.id).delete()
    db.delete(a)
    db.commit()
    if was_schedule:
        _reload()
    return {"ok": True}


@router.get("/automations/{aid}/runs")
def list_runs(aid: int, limit: int = 50, db: Session = Depends(get_db),
              ctx: Context = Depends(get_current_context), page: int = 1,
              start_date: date | None = None, end_date: date | None = None,
              statuses: str | None = None, duration: str | None = None):
    a, _ = _get_rule(db, aid, ctx)
    query = db.query(SmartAutomationRun).filter_by(rule_id=a.id)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    if start_date:
        query = query.filter(SmartAutomationRun.started_at >= datetime.combine(start_date, time.min))
    if end_date:
        query = query.filter(SmartAutomationRun.started_at < datetime.combine(end_date + timedelta(days=1), time.min))
    if statuses:
        selected = statuses.split(",")
        if set(selected) - {"success", "failed", "partial", "skipped", "running"}:
            raise HTTPException(400, "运行状态不支持")
        query = query.filter(SmartAutomationRun.status.in_(selected))
    if duration:
        bounds = {"lt1": (0, 60), "1to3": (60, 180), "3to10": (180, 600),
                  "10to60": (600, 3600), "gte60": (3600, None)}
        if duration not in bounds:
            raise HTTPException(400, "耗时范围不支持")
        if db.bind.dialect.name == "sqlite":
            seconds = func.round((func.julianday(SmartAutomationRun.finished_at)
                                  - func.julianday(SmartAutomationRun.started_at)) * 86400, 3)
        else:
            seconds = func.timestampdiff(text("MICROSECOND"), SmartAutomationRun.started_at,
                                         SmartAutomationRun.finished_at) / 1000000
        low, high = bounds[duration]
        query = query.filter(SmartAutomationRun.finished_at.isnot(None), seconds >= low)
        if high is not None:
            query = query.filter(seconds < high)
    total = query.count()
    size = min(max(limit, 1), 200)
    rows = query.order_by(SmartAutomationRun.id.desc()).offset((max(page, 1) - 1) * size).limit(size).all()
    return {"runs": [_run_out(r) for r in rows], "total": total}


@router.post("/automations/{aid}/run")
def run_rule(aid: int, payload: dict | None = None, db: Session = Depends(get_db),
             ctx: Context = Depends(get_current_context)):
    a, _ = _get_rule(db, aid, ctx, edit=True)
    rid = (payload or {}).get("record_id")
    run = automation_engine.run_manual(db, a, int(rid) if rid else None)
    return {"run": _run_out(run)}
