"""智能表自动化引擎（设计文档 §11）：触发器（定时/新增/变更）+ 条件 + 有序动作链 + 变量系统 + 运行日志。

步骤编号：第 1 步 = 触发器，动作依次为第 2..N 步；变量引用「第 N 步 + 变量名」：
  {"kind": "step", "step": 1, "key": "field", "field": "f_1"}   触发记录的字段值
  {"kind": "step", "step": 2, "key": "operator" | "time" | "count"}
  {"kind": "time", "key": "today" | "now"}                        自然时间
  {"kind": "dashboard", "entryId": 3, "name": "仪表盘"}            仪表盘（消息中以链接呈现）
消息内容 = 段落数组：[{"t": "text", "v": "…"}, {"t": "var", "var": {...}, "label": "…"}]。

语义要点（§11.2）：
- 事件型触发在事件发生时点对整行求值，条件不满足整链不执行（不记日志，避免每次编辑刷屏）；
- 自动化动作造成的变更默认不再触发其他规则（trigger.triggerByAutomation=true 可放开），另有深度上限；
- 单步失败即中止后续步骤，日志状态 failed（首步）/ partial（已执行部分步骤）。
"""
from __future__ import annotations

import logging
from datetime import date, datetime

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import MetaTable, Record, SmartAutomation, SmartAutomationRun, SmartDocEntry, User
from . import json_store, smart_events
from .meta_service import get_meta_fields
from .notify import notify_user
from .smart_cond import match_conditions
from .smart_format import display

log = logging.getLogger(__name__)

TRIGGER_TYPES = {"schedule", "recordCreated", "recordUpdated"}
ACTION_TYPES = {"sendMessage", "findRecords", "createRecord", "updateRecords"}
FREQS = {"daily", "weekly", "monthly"}
MAX_ACTIONS = 10
MAX_BATCH = 1000
WEEKDAY_CRON = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class AbortChain(Exception):
    """查找记录未命中且配置为「终止」：正常结束整链（非错误）。"""


# ---------- 校验 ----------

def _check_table(db: Session, table_id, tenant_id: int) -> MetaTable:
    try:
        mt = db.get(MetaTable, int(table_id))
    except (TypeError, ValueError):
        mt = None
    if not mt or mt.tenant_id != tenant_id:
        raise HTTPException(400, "动作引用的数据表不存在")
    return mt


def _clean_conds(conds) -> list[dict]:
    return [{"fieldId": c["fieldId"], "operator": c.get("operator") or "eq", "value": c.get("value")}
            for c in (conds or []) if isinstance(c, dict) and c.get("fieldId")][:20]


def validate_rule(db: Session, mt: MetaTable, payload: dict) -> tuple[dict, list]:
    trig = payload.get("trigger") or {}
    ttype = trig.get("type")
    if ttype not in TRIGGER_TYPES:
        raise HTTPException(400, "触发条件类型不支持")
    out_t = {"type": ttype, "triggerByAutomation": bool(trig.get("triggerByAutomation"))}
    if ttype == "schedule":
        sch = trig.get("schedule") or {}
        freq = sch.get("freq", "daily")
        if freq not in FREQS:
            raise HTTPException(400, "重复频率不支持")
        tm = str(sch.get("time") or "09:00")
        try:
            hh, mm = (int(x) for x in tm.split(":"))
            assert 0 <= hh < 24 and 0 <= mm < 60
        except (ValueError, AssertionError):
            raise HTTPException(400, "触发时间格式应为 HH:MM")
        out_t["schedule"] = {
            "freq": freq, "time": f"{hh:02d}:{mm:02d}",
            "weekdays": sorted({int(d) for d in sch.get("weekdays") or [1] if 1 <= int(d) <= 7}),
            "monthDays": sorted({int(d) for d in sch.get("monthDays") or [1] if 1 <= int(d) <= 31}),
        }
    else:
        names = {f.field_name for f in get_meta_fields(db, mt.id)}
        out_t["filter"] = {"match": "any" if (trig.get("filter") or {}).get("match") == "any" else "all",
                           "conditions": _clean_conds((trig.get("filter") or {}).get("conditions"))}
        if ttype == "recordCreated":
            out_t["rowConditions"] = _clean_conds(trig.get("rowConditions"))
        if ttype == "recordUpdated":
            out_t["watchFields"] = [x for x in (trig.get("watchFields") or []) if x in names]
    actions = payload.get("actions") or []
    if not isinstance(actions, list) or not actions:
        raise HTTPException(400, "至少需要一个执行操作")
    if len(actions) > MAX_ACTIONS:
        raise HTTPException(400, f"最多 {MAX_ACTIONS} 个执行操作")
    out_a = []
    for i, a in enumerate(actions):
        at = a.get("type")
        if at not in ACTION_TYPES:
            raise HTTPException(400, f"第 {i + 2} 步操作类型不支持：{at}")
        item = {"id": str(a.get("id") or f"a{i + 1}"), "type": at}
        if at == "sendMessage":
            item.update({
                "channel": "groupMessage" if a.get("channel") == "groupMessage" else "docMessage",
                "to": [int(x) for x in (a.get("to") or []) if str(x).isdigit()],
                "toFields": [str(x) for x in (a.get("toFields") or [])],
                "webhookUrl": str(a.get("webhookUrl") or "")[:500],
                "title": str(a.get("title") or "")[:200],
                "content": [seg for seg in (a.get("content") or []) if isinstance(seg, dict)][:200],
                "buttons": [{"label": str(b.get("label") or "查看记录")[:20]} for b in (a.get("buttons") or [])
                            if isinstance(b, dict)][:3],
            })
            if item["channel"] == "docMessage" and not item["to"] and not item["toFields"]:
                raise HTTPException(400, f"第 {i + 2} 步「发送消息」请选择接收人")
            if item["channel"] == "groupMessage" and not item["webhookUrl"].startswith(("http://", "https://")):
                raise HTTPException(400, f"第 {i + 2} 步「群消息」请填写群机器人 Webhook 地址")
        else:
            tmt = _check_table(db, a.get("tableId") or mt.id, mt.tenant_id)
            item["tableId"] = tmt.id
            if at == "findRecords":
                item.update({"match": "any" if a.get("match") == "any" else "all",
                             "conditions": _clean_conds(a.get("conditions")),
                             "onNotFound": "abort" if a.get("onNotFound") == "abort" else "continue"})
            if at in ("createRecord", "updateRecords"):
                item["values"] = [{"fieldId": v["fieldId"], "value": v.get("value")}
                                  for v in (a.get("values") or []) if isinstance(v, dict) and v.get("fieldId")]
            if at == "updateRecords":
                target = a.get("target") or "triggered"
                if target not in ("triggered", "all", "found", "matching"):
                    raise HTTPException(400, f"第 {i + 2} 步修改范围不支持：{target}")
                item.update({"target": target, "foundStep": a.get("foundStep"),
                             "match": "any" if a.get("match") == "any" else "all",
                             "conditions": _clean_conds(a.get("conditions"))})
                if target == "triggered" and ttype == "schedule":
                    raise HTTPException(400, "定时触发没有「触发的记录」，请改选其他修改范围")
        out_a.append(item)
    return out_t, out_a


# ---------- 变量与渲染 ----------

class RunContext:
    def __init__(self, db: Session, rule: SmartAutomation, depth: int):
        self.db = db
        self.rule = rule
        self.depth = depth
        self.steps: dict[int, dict] = {}
        self._fields: dict[int, list] = {}
        self._name_cache: dict = {}

    def fields(self, table_id: int) -> list:
        if table_id not in self._fields:
            self._fields[table_id] = get_meta_fields(self.db, table_id)
        return self._fields[table_id]

    def field(self, table_id: int, fn: str):
        return next((f for f in self.fields(table_id) if f.field_name == fn), None)

    def resolve_raw(self, var: dict):
        kind = var.get("kind")
        if kind == "time":
            return date.today().isoformat() if var.get("key") == "today" else datetime.now().strftime("%Y-%m-%d %H:%M")
        if kind in ("dashboard", "report"):
            return f"「{var.get('name') or '仪表盘'}」"
        if kind == "step":
            out = self.steps.get(int(var.get("step") or 0)) or {}
            key = var.get("key")
            if key == "field":
                rec = out.get("record") or {}
                return rec.get(var.get("field"))
            return out.get(key)
        return None

    def resolve_text(self, var: dict) -> str:
        v = self.resolve_raw(var)
        if var.get("kind") == "step" and var.get("key") == "field":
            out = self.steps.get(int(var.get("step") or 0)) or {}
            f = self.field(out.get("table_id") or self.rule.table_id, var.get("field"))
            return display(self.db, f, v, self._name_cache) if f else ("" if v is None else str(v))
        if v is None:
            return ""
        return str(v)

    def render(self, segments: list) -> str:
        parts = []
        for seg in segments or []:
            if seg.get("t") == "var" and isinstance(seg.get("var"), dict):
                parts.append(self.resolve_text(seg["var"]))
            elif seg.get("t") == "br":
                parts.append("\n")
            else:
                parts.append(str(seg.get("v") or ""))
        return "".join(parts)

    def value_for(self, target_field, spec):
        """赋值来源：静态值 / 变量（同类型取原始值，文本类目标取展示文本）。"""
        if isinstance(spec, dict) and spec.get("type") == "var" and isinstance(spec.get("var"), dict):
            var = spec["var"]
            raw = self.resolve_raw(var)
            src = None
            if var.get("kind") == "step" and var.get("key") == "field":
                out = self.steps.get(int(var.get("step") or 0)) or {}
                src = self.field(out.get("table_id") or self.rule.table_id, var.get("field"))
            if target_field is not None and src is not None and src.field_type == target_field.field_type:
                return raw
            if target_field is not None and (target_field.field_type or "") in ("number", "currency", "percent", "progress"):
                return raw
            return self.resolve_text(var)
        if isinstance(spec, dict) and spec.get("type") == "static":
            return spec.get("value")
        return spec

    def resolve_conditions(self, conds: list) -> list:
        out = []
        for c in conds or []:
            v = c.get("value")
            if isinstance(v, dict) and v.get("type") in ("var", "static"):
                v = self.value_for(None, v) if v.get("type") == "static" else self.resolve_raw(v["var"])
            out.append({**c, "value": v})
        return out


def _user_name(db: Session, uid) -> str:
    u = db.get(User, int(uid)) if uid is not None and str(uid).isdigit() else None
    return u.username if u else ""


def _record_ids(db: Session, table_id: int) -> list[int]:
    return [r.id for r in db.query(Record.id).filter_by(table_id=table_id).order_by(Record.id).all()]


# ---------- 动作执行 ----------

def _act_send(rc: RunContext, a: dict) -> tuple[dict, str]:
    db = rc.db
    trig = rc.steps.get(1) or {}
    rec = trig.get("record") or {}
    content = rc.render(a.get("content"))
    title = a.get("title") or rc.rule.name
    tid = rc.rule.table_id
    link = f"/smart/table/{tid}" + (f"?record={rec['id']}" if rec.get("id") else "")
    if a["channel"] == "groupMessage":
        text = f"{title}\n{content}" if title else content
        with httpx.Client(timeout=10) as client:
            resp = client.post(a["webhookUrl"], json={"msgtype": "text", "text": {"content": text}})
        if resp.status_code >= 400:
            raise RuntimeError(f"群消息发送失败：HTTP {resp.status_code}")
        return {"sent": 1}, "已发送群消息"
    recipients = set(a.get("to") or [])
    for fn in a.get("toFields") or []:
        v = rec.get(fn)
        for x in (v if isinstance(v, list) else [v]):
            if x is not None and str(x).isdigit():
                recipients.add(int(x))
    if not recipients:
        return {"sent": 0}, "没有可接收消息的成员"
    for uid in recipients:
        notify_user(db, uid, title, content, link=link, ref_type="smart_automation", ref_id=rc.rule.id)
    db.commit()
    return {"sent": len(recipients)}, f"已发送给 {len(recipients)} 人"


def _act_find(rc: RunContext, a: dict) -> tuple[dict, str]:
    fields = rc.fields(a["tableId"])
    conds = rc.resolve_conditions(a.get("conditions"))
    recs = [r for r in json_store.all_dicts(rc.db, a["tableId"], fields, normalized=True)
            if match_conditions(r, fields, conds, a.get("match", "all"))]
    if not recs and a.get("onNotFound") == "abort":
        raise AbortChain("未查找到记录，已按配置终止")
    ids = {r["id"] for r in recs[:MAX_BATCH]}
    client_rows = [r for r in json_store.all_dicts(rc.db, a["tableId"], fields) if r["id"] in ids]
    return ({"table_id": a["tableId"], "records": client_rows, "record": client_rows[0] if client_rows else None,
             "count": len(recs), "ids": [r["id"] for r in client_rows]},
            f"找到 {len(recs)} 条记录")


def _values_data(rc: RunContext, table_id: int, values: list) -> dict:
    data = {}
    for v in values or []:
        f = rc.field(table_id, v["fieldId"])
        if f is None:
            continue
        data[f.field_name] = rc.value_for(f, v.get("value"))
    return data


def _act_create(rc: RunContext, a: dict) -> tuple[dict, str]:
    mt = rc.db.get(MetaTable, a["tableId"])
    fields = rc.fields(mt.id)
    data = _values_data(rc, mt.id, a.get("values"))
    rec = json_store.create_record(rc.db, mt, fields, data, user="自动化",
                                   owner_id=rc.rule.created_by, actor_type="automation")
    smart_events.record_created(rc.db, mt, rec, actor_id=rc.rule.created_by,
                                actor_type="automation", depth=rc.depth + 1)
    return ({"table_id": mt.id, "record": rec, "count": 1, "operator": "自动化",
             "time": datetime.now().strftime("%Y-%m-%d %H:%M")}, "已新增 1 条记录")


def _act_update(rc: RunContext, a: dict) -> tuple[dict, str]:
    mt = rc.db.get(MetaTable, a["tableId"])
    fields = rc.fields(mt.id)
    target = a.get("target")
    if target == "triggered":
        trig = rc.steps.get(1) or {}
        rid = (trig.get("record") or {}).get("id")
        ids = [rid] if rid and trig.get("table_id") == mt.id else []
    elif target == "found":
        out = rc.steps.get(int(a.get("foundStep") or 0)) or {}
        ids = list(out.get("ids") or [])
    elif target == "matching":
        conds = rc.resolve_conditions(a.get("conditions"))
        ids = [r["id"] for r in json_store.all_dicts(rc.db, mt.id, fields, normalized=True)
               if match_conditions(r, fields, conds, a.get("match", "all"))]
    else:
        ids = _record_ids(rc.db, mt.id)
    ids = ids[:MAX_BATCH]
    data = _values_data(rc, mt.id, a.get("values"))
    if not data:
        return {"table_id": mt.id, "count": 0, "ids": []}, "没有要修改的内容"
    done = []
    for rid in ids:
        try:
            before = json_store.get_record(rc.db, mt.id, rid, fields)
        except HTTPException:
            continue
        after = json_store.update_record(rc.db, mt, fields, rid, data, user="自动化",
                                         editor_id=None, actor_type="automation")
        smart_events.record_updated(rc.db, mt, before, after, list(data), actor_id=rc.rule.created_by,
                                    actor_type="automation", depth=rc.depth + 1)
        done.append(rid)
    return ({"table_id": mt.id, "count": len(done), "ids": done, "operator": "自动化",
             "time": datetime.now().strftime("%Y-%m-%d %H:%M")}, f"已修改 {len(done)} 条记录")


ACTIONS = {"sendMessage": _act_send, "findRecords": _act_find,
           "createRecord": _act_create, "updateRecords": _act_update}


# ---------- 运行 ----------

def run_rule(db: Session, rule: SmartAutomation, trigger_out: dict, depth: int = 0) -> SmartAutomationRun:
    run = SmartAutomationRun(rule_id=rule.id, status="running", started_at=datetime.now(),
                             trigger_snapshot={k: v for k, v in trigger_out.items() if k != "records"})
    db.add(run)
    db.commit()
    rc = RunContext(db, rule, depth)
    rc.steps[1] = trigger_out
    results, status, error = [], "success", None
    for i, a in enumerate(rule.actions or [], start=2):
        fn = ACTIONS.get(a.get("type"))
        try:
            out, msg = fn(rc, a)
            rc.steps[i] = out
            results.append({"step": i, "type": a.get("type"), "status": "success", "message": msg})
        except AbortChain as e:
            results.append({"step": i, "type": a.get("type"), "status": "skipped", "message": str(e)})
            break
        except Exception as e:  # noqa: BLE001 — 单步失败记日志并中止后续
            db.rollback()
            detail = e.detail if isinstance(e, HTTPException) else str(e)
            results.append({"step": i, "type": a.get("type"), "status": "failed", "message": str(detail)[:500]})
            status = "failed" if i == 2 else "partial"
            error = str(detail)[:2000]
            break
    run = db.get(SmartAutomationRun, run.id)
    run.status = status
    run.step_results = results
    run.error = error
    run.finished_at = datetime.now()
    db.commit()
    return run


def _trigger_matches(db: Session, rule: SmartAutomation, event: dict) -> bool:
    trig = rule.trigger_config or {}
    if event["actor_type"] == "automation" and not trig.get("triggerByAutomation"):
        return False
    fields = get_meta_fields(db, rule.table_id)
    try:
        rec = json_store.normalized_one(db, rule.table_id, event["record_id"], fields)
    except HTTPException:
        return False   # 记录已被删除
    if event["type"] == "recordUpdated":
        watch = trig.get("watchFields") or []
        if watch and not set(watch) & set(event.get("changed") or []):
            return False
    if event["type"] == "recordCreated" and not match_conditions(rec, fields, trig.get("rowConditions"), "all"):
        return False
    flt = trig.get("filter") or {}
    return match_conditions(rec, fields, flt.get("conditions"), flt.get("match", "all"))


def trigger_output(db: Session, rule: SmartAutomation, event: dict | None) -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if not event:
        return {"table_id": rule.table_id, "time": now, "operator": "定时触发"}
    fields = get_meta_fields(db, rule.table_id)
    labels = {f.field_name: f.label for f in fields}
    try:
        record = json_store.get_record(db, rule.table_id, event["record_id"], fields)
    except HTTPException:
        record = event.get("after") or {}
    operator = {"ai": "AI", "automation": "自动化"}.get(event.get("actor_type")) or _user_name(db, event.get("actor_id"))
    return {"table_id": rule.table_id, "record": record, "operator": operator,
            "operatorId": event.get("actor_id"), "time": now,
            "changed": [labels.get(k, k) for k in event.get("changed") or []]}


def handle_event(db: Session, event: dict) -> None:
    rules = (db.query(SmartAutomation)
             .filter_by(table_id=event["table_id"], enabled=True).order_by(SmartAutomation.id).all())
    for rule in rules:
        if (rule.trigger_config or {}).get("type") != event["type"]:
            continue
        try:
            if not _trigger_matches(db, rule, event):
                continue
            run_rule(db, rule, trigger_output(db, rule, event), depth=event.get("depth", 0))
        except Exception:  # noqa: BLE001
            log.exception("automation rule %s failed", rule.id)
            db.rollback()


def run_manual(db: Session, rule: SmartAutomation, record_id: int | None = None) -> SmartAutomationRun:
    """手动运行（编辑器「试运行」）：事件型规则取指定记录或最新一条记录作为触发记录，不校验条件。"""
    ttype = (rule.trigger_config or {}).get("type")
    if ttype == "schedule":
        return run_rule(db, rule, trigger_output(db, rule, None))
    if record_id is None:
        last = db.query(Record).filter_by(table_id=rule.table_id).order_by(Record.id.desc()).first()
        if not last:
            raise HTTPException(400, "表中还没有记录，无法试运行")
        record_id = last.id
    event = {"type": ttype, "table_id": rule.table_id, "record_id": record_id,
             "actor_type": "user", "actor_id": rule.created_by, "changed": []}
    return run_rule(db, rule, trigger_output(db, rule, event))


def run_scheduled(rule_id: int) -> None:
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        rule = db.get(SmartAutomation, rule_id)
        if rule and rule.enabled and (rule.trigger_config or {}).get("type") == "schedule":
            run_rule(db, rule, trigger_output(db, rule, None))
    finally:
        db.close()


def cron_kwargs(schedule: dict) -> dict:
    hh, mm = (int(x) for x in (schedule.get("time") or "09:00").split(":"))
    kw = {"hour": hh, "minute": mm}
    if schedule.get("freq") == "weekly":
        kw["day_of_week"] = ",".join(WEEKDAY_CRON[d - 1] for d in schedule.get("weekdays") or [1])
    elif schedule.get("freq") == "monthly":
        kw["day"] = ",".join(str(d) for d in schedule.get("monthDays") or [1])
    return kw


def register_jobs(scheduler, db: Session) -> None:
    """scheduler.reload_jobs 调用：注册启用的定时规则。"""
    from apscheduler.triggers.cron import CronTrigger
    for rule in db.query(SmartAutomation).filter_by(enabled=True).all():
        trig = rule.trigger_config or {}
        if trig.get("type") != "schedule":
            continue
        try:
            scheduler.add_job(run_scheduled, CronTrigger(**cron_kwargs(trig.get("schedule") or {})),
                              args=[rule.id], id=f"smart_auto_{rule.id}", replace_existing=True,
                              misfire_grace_time=300)
        except (ValueError, TypeError):
            log.warning("invalid schedule for automation %s", rule.id)


def entry_name(db: Session, table_id: int) -> str:
    e = db.query(SmartDocEntry).filter(SmartDocEntry.ref_table_id == table_id).first()
    return e.name if e else ""
