"""智能表自动化路由（设计文档 §11、§16.2）：规则 CRUD / 启停 / 运行日志 / 手动运行。

权限：查看规则需表查看权；增删改与运行需表编辑权且内容权限 ≥ 可编辑。
"""
from fastapi import APIRouter, Depends, HTTPException
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
    if "name" in payload:
        a.name = str(payload["name"] or "").strip()[:200] or a.name
    if "enabled" in payload:
        a.enabled = bool(payload["enabled"])
    if "trigger" in payload or "actions" in payload:
        trig, actions = automation_engine.validate_rule(db, access.table, {
            "trigger": payload.get("trigger", a.trigger_config), "actions": payload.get("actions", a.actions)})
        a.trigger_config, a.actions = trig, actions
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
              ctx: Context = Depends(get_current_context)):
    a, _ = _get_rule(db, aid, ctx)
    rows = (db.query(SmartAutomationRun).filter_by(rule_id=a.id)
            .order_by(SmartAutomationRun.id.desc()).limit(min(max(limit, 1), 200)).all())
    return {"runs": [_run_out(r) for r in rows]}


@router.post("/automations/{aid}/run")
def run_rule(aid: int, payload: dict | None = None, db: Session = Depends(get_db),
             ctx: Context = Depends(get_current_context)):
    a, _ = _get_rule(db, aid, ctx, edit=True)
    rid = (payload or {}).get("record_id")
    run = automation_engine.run_manual(db, a, int(rid) if rid else None)
    return {"run": _run_out(run)}
