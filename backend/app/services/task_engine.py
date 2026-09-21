"""任务引擎：规则求值（结构化条件 / LLM 判断）、冷却去重、动作执行。"""
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import MetaTable, TaskRule, TaskRunLog, TaskTriggerLog
from . import dyn_engine
from .actions import ACTION_FUNCS, ActionError, render_template
from .llm import judge_records
from .llm.base import LLMError

HARD_CANDIDATE_CAP = 200   # LLM 判断模式的候选记录硬上限，控制成本


class TaskError(Exception):
    pass


def evaluate_rule(db: Session, rule: TaskRule) -> list[dict]:
    """求值规则条件，返回命中的记录（不含冷却过滤）。"""
    mt, fields, table = dyn_engine.load_business(db, rule.table_id)
    fields_by_name = {f.field_name: f for f in fields}
    cond = rule.condition_json or {}

    if rule.condition_mode == "llm":
        description = (cond.get("description") or "").strip()
        if not description:
            raise TaskError("未配置 LLM 判断条件描述")
        pre = cond.get("prefilter") or {}
        pre_rules = pre.get("rules") or []
        conds = [dyn_engine.build_condition(table, fields_by_name, f) for f in pre_rules]
        if pre.get("logic") == "OR" and conds:
            conds = [or_(*conds)]
        rows = db.execute(
            select(table).where(*conds).limit(HARD_CANDIDATE_CAP)
        ).mappings().all()
        candidates = [dyn_engine.row_to_dict(r) for r in rows]
        if not candidates:
            return []
        field_dicts = [{"field_name": f.field_name, "label": f.label, "data_type": f.data_type} for f in fields]
        matched_ids = judge_records(db, description, field_dicts, candidates)
        return [r for r in candidates if r["id"] in matched_ids]

    # 结构化条件
    rules = cond.get("rules") or []
    if not rules:
        raise TaskError("未配置条件规则")
    conds = [dyn_engine.build_condition(table, fields_by_name, f) for f in rules]
    if (cond.get("logic") or "AND") == "OR" and len(conds) > 1:
        conds = [or_(*conds)]
    rows = db.execute(select(table).where(*conds).limit(HARD_CANDIDATE_CAP)).mappings().all()
    return [dyn_engine.row_to_dict(r) for r in rows]


def filter_cooldown(db: Session, rule: TaskRule, records: list[dict]) -> tuple[list[dict], dict[int, TaskTriggerLog]]:
    """按冷却窗口过滤。返回 (可触发记录, 已有触发日志 map)。cooldown=0 表示永不重复。"""
    if not records:
        return [], {}
    ids = [r["id"] for r in records]
    logs = db.query(TaskTriggerLog).filter(
        TaskTriggerLog.rule_id == rule.id, TaskTriggerLog.record_id.in_(ids)
    ).all()
    log_map = {l.record_id: l for l in logs}
    cooldown = rule.cooldown_hours if rule.cooldown_hours is not None else 24
    now = datetime.now()
    targets = []
    for r in records:
        log = log_map.get(r["id"])
        if log is None:
            targets.append(r)
        elif cooldown <= 0:
            continue  # 已触发过且永不重复
        elif log.fired_at and (now - log.fired_at) < timedelta(hours=cooldown):
            continue  # 冷却期内
        else:
            targets.append(r)
    return targets, log_map


def execute_rule(rule_id: int, trigger: str = "schedule") -> dict | None:
    """执行一条规则：求值 -> 冷却过滤 -> 逐条执行动作 -> 写日志。供调度器和手动调用。"""
    db = SessionLocal()
    try:
        rule = db.get(TaskRule, rule_id)
        if not rule:
            return None
        if trigger == "schedule" and not rule.enabled:
            return None

        run = TaskRunLog(rule_id=rule.id, trigger=trigger, run_at=datetime.now())
        matched, targets = [], []
        try:
            matched = evaluate_rule(db, rule)
            targets, log_map = filter_cooldown(db, rule, matched)
            targets = targets[: (rule.max_per_run or 100)]

            action = rule.action_json or {}
            func = ACTION_FUNCS.get(action.get("type"))
            sent = fail = 0
            details = []
            for rec in targets:
                content = render_template(action.get("template", ""), rec)
                try:
                    if func is None:
                        raise ActionError(f"未知动作类型：{action.get('type')}")
                    func(db, rule, rec, content)
                    # 更新触发去重记录
                    log = log_map.get(rec["id"])
                    if log:
                        log.fired_at = datetime.now()
                    else:
                        db.add(TaskTriggerLog(rule_id=rule.id, record_id=rec["id"], fired_at=datetime.now()))
                    db.commit()   # 每条成功立即提交，避免后续失败回滚丢掉触发记录
                    sent += 1
                    details.append({"record_id": rec["id"], "ok": True, "content": content[:200]})
                except Exception as e:
                    db.rollback()
                    fail += 1
                    details.append({"record_id": rec["id"], "ok": False, "error": str(e)[:200]})

            run.matched_count = len(matched)
            run.sent_count = sent
            run.fail_count = fail
            run.detail_json = details[:100]
            # 把第一条动作失败原因提到 run.error，列表页能直接看到
            if fail and not run.error:
                first_fail = next((d for d in details if not d["ok"]), None)
                if first_fail:
                    run.error = first_fail["error"]
        except (TaskError, LLMError, Exception) as e:  # noqa: BLE001 — 任何求值错误都落日志
            run.error = str(e)[:500]

        db.add(run)
        db.commit()
        return {
            "matched": run.matched_count, "fired": run.sent_count,
            "failed": run.fail_count, "error": run.error,
        }
    finally:
        db.close()
