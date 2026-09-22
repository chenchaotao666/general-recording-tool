"""任务规则管理 + 试运行/手动执行 + 运行日志。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import TaskRule, TaskRunLog
from ..schemas import TaskRuleIn
from ..services import scheduler as sched
from ..services.actions import ACTION_FUNCS
from ..services.dyn_engine import FILTER_OPS, rule_value_ok
from ..services.llm import LLMError
from ..services.llm.gateway import assist_task
from ..services.meta_service import get_meta_fields, get_meta_table
from ..services.task_engine import evaluate_rule, execute_rule, filter_cooldown

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _validate(db: Session, payload: TaskRuleIn) -> None:
    if not get_meta_table(db, payload.table_id):
        raise HTTPException(400, "目标数据表不存在")

    cond = payload.condition or {}
    if payload.condition_mode == "llm":
        if not (cond.get("description") or "").strip():
            raise HTTPException(400, "LLM 判断模式需要填写条件描述")
        pre_rules = (cond.get("prefilter") or {}).get("rules") or []
        _check_rules(db, payload.table_id, pre_rules)
    else:
        rules = cond.get("rules") or []
        if not rules:
            raise HTTPException(400, "请至少配置一条条件")
        _check_rules(db, payload.table_id, rules)

    s = payload.schedule or {}
    if s.get("type") == "interval":
        if int(s.get("minutes") or 0) < 1:
            raise HTTPException(400, "间隔分钟数必须 ≥ 1")
    elif s.get("type") == "cron":
        if sched.trigger_of(s) is None:
            raise HTTPException(400, "cron 表达式无效（格式：分 时 日 月 周，如 0 9 * * *）")
    else:
        raise HTTPException(400, "执行周期类型无效")

    a = payload.action or {}
    if a.get("type") not in ACTION_FUNCS:
        raise HTTPException(400, "动作类型无效")
    if not (a.get("template") or "").strip():
        raise HTTPException(400, "请填写通知内容模板")


def _check_rules(db: Session, table_id: int, rules: list[dict]) -> None:
    fields = {f.field_name: f for f in get_meta_fields(db, table_id)}
    system_fields = {"id", "created_at", "updated_at"}
    for r in rules:
        name = r.get("field")
        if name not in fields and name not in system_fields:
            raise HTTPException(400, f"条件字段不存在：{name}")
        if r.get("op") not in FILTER_OPS:
            raise HTTPException(400, f"不支持的条件操作符：{r.get('op')}")
        if not rule_value_ok(fields.get(name), r.get("op"), r.get("value")):
            label = fields[name].label if name in fields else name
            raise HTTPException(400, f"筛选值无效（{label}）：无法按字段类型转换（日期请选具体日期或相对时间操作符）")


def _out(db: Session, rule: TaskRule) -> dict:
    mt = get_meta_table(db, rule.table_id)
    last_run = (
        db.query(TaskRunLog)
        .filter(TaskRunLog.rule_id == rule.id, TaskRunLog.trigger != "test")
        .order_by(TaskRunLog.id.desc())
        .first()
    )
    return {
        "id": rule.id, "name": rule.name, "table_id": rule.table_id,
        "table_label": mt.label if mt else f"表#{rule.table_id}",
        "enabled": rule.enabled, "condition_mode": rule.condition_mode,
        "condition": rule.condition_json or {}, "schedule": rule.schedule_json or {},
        "action": rule.action_json or {},
        "cooldown_hours": rule.cooldown_hours, "max_per_run": rule.max_per_run,
        "created_at": rule.created_at.isoformat(sep=" ") if rule.created_at else None,
        "last_run": {
            "run_at": last_run.run_at.isoformat(sep=" "),
            "matched": last_run.matched_count, "sent": last_run.sent_count,
            "failed": last_run.fail_count, "error": last_run.error,
        } if last_run else None,
    }


@router.get("")
def list_rules(db: Session = Depends(get_db)):
    rows = db.query(TaskRule).order_by(TaskRule.id.desc()).all()
    return [_out(db, r) for r in rows]


class AiAssistIn(BaseModel):
    table_id: int
    description: str


@router.post("/ai-assist")
def ai_assist(payload: AiAssistIn, db: Session = Depends(get_db)):
    """自然语言描述 → LLM 生成任务规则配置（条件/周期/动作），不落库。"""
    if not payload.description.strip():
        raise HTTPException(400, "请填写任务需求描述")
    if not get_meta_table(db, payload.table_id):
        raise HTTPException(400, "目标数据表不存在")
    fields = get_meta_fields(db, payload.table_id)
    try:
        return assist_task(db, fields, payload.description.strip())
    except LLMError as e:
        raise HTTPException(400, str(e))


@router.post("")
def create_rule(payload: TaskRuleIn, db: Session = Depends(get_db)):
    _validate(db, payload)
    rule = TaskRule(
        name=payload.name, table_id=payload.table_id, enabled=payload.enabled,
        condition_mode=payload.condition_mode, condition_json=payload.condition,
        schedule_json=payload.schedule, action_json=payload.action,
        cooldown_hours=payload.cooldown_hours, max_per_run=payload.max_per_run,
    )
    db.add(rule)
    db.commit()
    sched.reload_jobs()
    return _out(db, rule)


@router.put("/{rule_id}")
def update_rule(rule_id: int, payload: TaskRuleIn, db: Session = Depends(get_db)):
    rule = db.get(TaskRule, rule_id)
    if not rule:
        raise HTTPException(404, "任务不存在")
    _validate(db, payload)
    rule.name, rule.table_id, rule.enabled = payload.name, payload.table_id, payload.enabled
    rule.condition_mode, rule.condition_json = payload.condition_mode, payload.condition
    rule.schedule_json, rule.action_json = payload.schedule, payload.action
    rule.cooldown_hours, rule.max_per_run = payload.cooldown_hours, payload.max_per_run
    rule.updated_at = datetime.now()
    db.commit()
    sched.reload_jobs()
    return _out(db, rule)


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(TaskRule, rule_id)
    if not rule:
        raise HTTPException(404, "任务不存在")
    db.delete(rule)
    db.commit()
    sched.reload_jobs()
    return {"ok": True}


@router.post("/{rule_id}/toggle")
def toggle_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(TaskRule, rule_id)
    if not rule:
        raise HTTPException(404, "任务不存在")
    rule.enabled = not rule.enabled
    db.commit()
    sched.reload_jobs()
    return _out(db, rule)


@router.post("/{rule_id}/test")
def test_rule(rule_id: int, db: Session = Depends(get_db)):
    """试运行：只求值和冷却过滤，不执行动作，返回命中样本。"""
    rule = db.get(TaskRule, rule_id)
    if not rule:
        raise HTTPException(404, "任务不存在")
    try:
        matched = evaluate_rule(db, rule)
        targets, _ = filter_cooldown(db, rule, matched)
    except Exception as e:
        raise HTTPException(400, f"条件求值失败：{e}")
    return {
        "matched": len(matched),
        "would_fire": len(targets),
        "samples": targets[:10],
    }


@router.post("/{rule_id}/run")
def run_rule(rule_id: int, db: Session = Depends(get_db)):
    """立即执行一次（执行动作，遵守冷却窗口）。"""
    rule = db.get(TaskRule, rule_id)
    if not rule:
        raise HTTPException(404, "任务不存在")
    result = execute_rule(rule_id, trigger="manual")
    return result or {"error": "执行失败"}


@router.get("/{rule_id}/runs")
def list_runs(rule_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(TaskRunLog)
        .filter_by(rule_id=rule_id)
        .order_by(TaskRunLog.id.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": r.id, "trigger": r.trigger,
            "run_at": r.run_at.isoformat(sep=" ") if r.run_at else None,
            "matched_count": r.matched_count, "sent_count": r.sent_count,
            "fail_count": r.fail_count, "error": r.error, "detail": r.detail_json or [],
        }
        for r in rows
    ]
