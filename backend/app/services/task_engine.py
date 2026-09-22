"""任务引擎：规则求值（结构化条件 / LLM 判断）、冷却去重、动作执行。"""
import time
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import MetaTable, TaskRule, TaskRunLog, TaskTriggerLog
from . import dyn_engine
from .actions import ACTION_FUNCS, BATCH_ACTION_FUNCS, ActionError, render_batch_body, render_template
from .llm import judge_records
from .llm.base import LLMError

HARD_CANDIDATE_CAP = 200   # LLM 判断模式的候选记录硬上限，控制成本


def _log_sql(tag: str, stmt, elapsed_ms: float) -> None:
    """打印执行的 SQL 语句和耗时（结构化条件求值调试用）。"""
    try:
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    except Exception:  # 个别类型无法字面量渲染时退化为参数形式
        sql = str(stmt)
    print(f"[task] {tag} 耗时 {elapsed_ms:.0f}ms | {sql}", flush=True)


class TaskError(Exception):
    pass


def evaluate_rule(db: Session, rule: TaskRule) -> list[dict]:
    """求值规则条件，返回命中的记录（不含冷却过滤）。"""
    mt, fields = dyn_engine.load_meta(db, rule.table_id)
    fields_by_name = {f.field_name: f for f in fields}
    cond = rule.condition_json or {}

    if mt.storage_mode == "json":
        return _evaluate_rule_py(db, rule, mt, fields, fields_by_name, cond)

    _, fields, table = dyn_engine.load_business(db, rule.table_id)

    if rule.condition_mode == "llm":
        description = (cond.get("description") or "").strip()
        if not description:
            raise TaskError("未配置 LLM 判断条件描述")
        pre = cond.get("prefilter") or {}
        pre_rules = pre.get("rules") or []
        conds = [dyn_engine.build_condition(table, fields_by_name, f) for f in pre_rules]
        if pre.get("logic") == "OR" and conds:
            conds = [or_(*conds)]
        stmt = select(table).where(*conds).limit(HARD_CANDIDATE_CAP)
        t0 = time.perf_counter()
        rows = db.execute(stmt).mappings().all()
        _log_sql("LLM 预筛", stmt, (time.perf_counter() - t0) * 1000)
        candidates = [dyn_engine.row_to_dict(r) for r in rows]
        if not candidates:
            return []
        field_dicts = [{"field_name": f.field_name, "label": f.label, "data_type": f.data_type} for f in fields]
        matched_ids = judge_records(db, description, field_dicts, candidates)
        return [r for r in candidates if r["id"] in matched_ids]

    # 结构化条件：SQL 层过滤，不设条数上限
    rules = cond.get("rules") or []
    if not rules:
        raise TaskError("未配置条件规则")
    conds = [dyn_engine.build_condition(table, fields_by_name, f) for f in rules]
    if (cond.get("logic") or "AND") == "OR" and len(conds) > 1:
        conds = [or_(*conds)]
    stmt = select(table).where(*conds)
    t0 = time.perf_counter()
    rows = db.execute(stmt).mappings().all()
    _log_sql("结构化条件", stmt, (time.perf_counter() - t0) * 1000)
    return [dyn_engine.row_to_dict(r) for r in rows]


def _evaluate_rule_py(db: Session, rule: TaskRule, mt: MetaTable, fields: list, fields_by_name: dict, cond: dict) -> list[dict]:
    """json 模式：全量记录拉回内存，pyquery 过滤（语义与 build_condition 对齐）。"""
    from . import json_store
    from .pyquery import match_filters

    recs = json_store.all_dicts(db, mt.id, fields, normalized=True)

    if rule.condition_mode == "llm":
        description = (cond.get("description") or "").strip()
        if not description:
            raise TaskError("未配置 LLM 判断条件描述")
        candidates = [r for r in recs if match_filters(r, fields_by_name, cond.get("prefilter") or {})]
        candidates = [{k: dyn_engine.serialize_value(v) for k, v in r.items()} for r in candidates[:HARD_CANDIDATE_CAP]]
        if not candidates:
            return []
        field_dicts = [{"field_name": f.field_name, "label": f.label, "data_type": f.data_type} for f in fields]
        matched_ids = judge_records(db, description, field_dicts, candidates)
        return [r for r in candidates if r["id"] in matched_ids]

    rules = cond.get("rules") or []
    if not rules:
        raise TaskError("未配置条件规则")
    matched = [r for r in recs if match_filters(r, fields_by_name, cond)]
    return [{k: dyn_engine.serialize_value(v) for k, v in r.items()} for r in matched]


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
            cooldown_targets, log_map = filter_cooldown(db, rule, matched)
            # 手动执行跳过冷却过滤，便于立即验证效果；定时调度仍遵守冷却窗口
            targets = matched if trigger == "manual" else cooldown_targets
            targets = targets[: (rule.max_per_run or 100)]

            action = rule.action_json or {}
            action_type = action.get("type")
            func = ACTION_FUNCS.get(action_type)
            batch_func = BATCH_ACTION_FUNCS.get(action_type)
            sent = fail = 0
            details = []

            if batch_func is not None and targets:
                # 邮件/短信：每次执行只发一次，汇总所有命中记录；触发日志仍逐条写（冷却语义不变）
                try:
                    batch_func(db, rule, targets)
                    now = datetime.now()
                    for rec in targets:
                        log = log_map.get(rec["id"])
                        if log:
                            log.fired_at = now
                        else:
                            db.add(TaskTriggerLog(rule_id=rule.id, record_id=rec["id"], fired_at=now))
                    db.commit()
                    sent = len(targets)
                    details.append({"batch": len(targets), "ok": True,
                                    "content": render_batch_body(action, targets)[:200]})
                except Exception as e:
                    db.rollback()
                    fail = len(targets)
                    details.append({"batch": len(targets), "ok": False, "error": str(e)[:200]})
            else:
                for rec in targets:
                    content = render_template(action.get("template", ""), rec)
                    try:
                        if func is None:
                            raise ActionError(f"未知动作类型：{action_type}")
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
