"""AI 助手动作执行：/execute 的唯一写入口 —— 执行前重新鉴权 + 重新校验（不信任 chat 阶段的输出）。
另含问答 spec 清洗与受控聚合求值（复用报表引擎语义，杜绝 text-to-SQL）。"""
from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import MetaTable, User, Workflow
from ..schemas import TableCreate
from ..utils.access import check_owner_or_admin, get_table_access
from ..utils.rbac import perm_value
from . import dyn_engine, meta_service
from .dyn_engine import log_audit
from .records_export import export_blank_xlsx, export_records_xlsx
from .uploads import save_generated

FILL_MAX = 50            # 单次填表条数上限
QUERY_TABLE_MAX = 50     # 问答清单行数上限
EXPORT_MAX = 5000        # 导出记录数上限（另受 dyn_engine 页大小上限约束）
_SYSTEM_FIELDS = {"id", "created_at", "updated_at"}
_DATE_SYSTEM_FIELDS = {"created_at", "updated_at"}


# ---------- 筛选与问答 spec 清洗（chat 阶段 align 调用） ----------

def clean_assistant_filters(flt: dict | None, fields_by_name: dict, notes: list) -> dict:
    """清洗问答/导出的筛选规则：字段白名单 + 操作符 + 值按类型校验（与报表 align 同规则）。"""
    rules = []
    for r in ((flt or {}).get("rules") or []):
        if not isinstance(r, dict):
            continue
        name, op = r.get("field"), r.get("op")
        if name not in fields_by_name and name not in _SYSTEM_FIELDS:
            continue
        if op not in dyn_engine.FILTER_OPS:
            continue
        if not dyn_engine.rule_value_ok(fields_by_name.get(name), op, r.get("value")):
            notes.append(f"筛选条件「{name} {op}」的值无效已丢弃")
            continue
        rules.append({"field": name, "op": op, "value": r.get("value")})
    return {"logic": "AND", "rules": rules}


def clean_query_spec(fields: list, spec: dict) -> tuple[dict | None, list]:
    """把问答 spec 清洗为报表引擎区块配置。返回 ({kind, block, range} | None, notes)。"""
    from .report_engine import CHART_AGG_TYPES, GROUP_KINDS

    notes = []
    fbn = {f.field_name: f for f in fields}
    kind = spec.get("kind")
    filters = clean_assistant_filters(spec.get("filters"), fbn, notes)
    range_spec = spec.get("range") if isinstance(spec.get("range"), dict) else None

    def check_agg(agg, field):
        agg = agg or "count"
        if agg not in CHART_AGG_TYPES:
            return None
        if agg == "count":
            return {"agg": "count", "field": None}
        if agg == "count_distinct":
            return {"agg": agg, "field": field} if field in fbn or field in _SYSTEM_FIELDS else None
        f = fbn.get(field or "")
        if f is None or f.data_type not in ("int", "decimal"):
            return None
        return {"agg": agg, "field": field}

    if kind == "stat":
        m = check_agg(spec.get("agg"), spec.get("field"))
        if m is None:
            notes.append("问答的聚合方式或统计字段无效")
            return None, notes
        return {"kind": "stat", "block": {"type": "stat", **m, "filters": filters}, "range": range_spec}, notes

    if kind == "chart":
        g = spec.get("group") or {}
        gkind = g.get("kind") if g.get("kind") in GROUP_KINDS else "field"
        gfield = g.get("field")
        gf = fbn.get(gfield or "")
        if gfield not in _DATE_SYSTEM_FIELDS and gf is None:
            notes.append(f"分组字段无效：{gfield}")
            return None, notes
        if gkind in ("day", "week", "month") and not (
            (gf is not None and gf.data_type in ("date", "datetime")) or gfield in _DATE_SYSTEM_FIELDS
        ):
            notes.append("按日/周/月分组需要日期类型字段")
            return None, notes
        m = check_agg(spec.get("agg"), spec.get("field"))
        if m is None:
            notes.append("问答的聚合方式或统计字段无效")
            return None, notes
        return {
            "kind": "chart",
            "block": {"type": "chart", "chart_type": "bar",
                      "group": {"kind": gkind, "field": gfield}, **m, "filters": filters},
            "range": range_spec,
        }, notes

    if kind == "table":
        cols = [c for c in (spec.get("columns") or []) if c in fbn or c in _SYSTEM_FIELDS]
        if not cols:
            cols = list(fbn)[:5]
        try:
            limit = min(max(int(spec.get("limit") or 20), 1), QUERY_TABLE_MAX)
        except (TypeError, ValueError):
            limit = 20
        return {
            "kind": "table",
            "block": {"type": "table", "columns": cols, "limit": limit,
                      "sort_by": "created_at", "sort_order": "desc", "filters": filters},
            "range": range_spec,
        }, notes

    notes.append(f"不支持的问答类型：{kind}")
    return None, notes


def _query_range(range_spec: dict | None):
    """问答时间口径：缺省为全部时间（宽区间覆盖）。"""
    from .report_engine import RANGE_MODES, ReportError, resolve_time_range

    rng = range_spec or {}
    if rng.get("mode") in RANGE_MODES:
        try:
            start, end, label = resolve_time_range(
                {"mode": rng["mode"], "date_field": rng.get("date_field") or "created_at"})
            return rng.get("date_field") or "created_at", start, end, label
        except ReportError:
            pass
    return "created_at", datetime(1970, 1, 1), datetime.now() + timedelta(days=1), "全部时间"


def run_query_spec(db: Session, mt: MetaTable, fields: list, spec: dict) -> dict:
    """按清洗后的 spec 走报表引擎求值（双引擎对齐）。"""
    from . import report_engine as re_mod

    date_field, start, end, range_label = _query_range(spec.get("range"))
    block = dict(spec["block"], id="q1")
    if mt.storage_mode == "json":
        fake_tpl = SimpleNamespace(id=None, name="数据问答", blocks_json=[block])
        out = re_mod._run_py(db, mt, fields, fake_tpl, date_field, start, end, range_label)["blocks"][0]
    else:
        _, fields, table = dyn_engine.load_business(db, mt.id)
        fbn = {f.field_name: f for f in fields}
        fn = {"stat": re_mod._eval_stat, "chart": re_mod._eval_chart, "table": re_mod._eval_table}[spec["kind"]]
        out = fn(db, table, fbn, block, date_field, start, end)
    out["range_label"] = range_label
    return out


# ---------- 动作执行（/execute） ----------

def execute_action(db: Session, user: User, type_: str, payload: dict) -> dict:
    if type_ == "fill_records":
        return _exec_fill(db, user, payload or {})
    if type_ == "create_table":
        return _exec_create_table(db, user, payload or {})
    if type_ == "create_report":
        return _exec_create_report(db, user, payload or {})
    if type_ == "create_task":
        return _exec_create_task(db, user, payload or {})
    if type_ == "gen_excel":
        return _exec_gen_excel(db, user, payload or {})
    if type_ == "run_workflow":
        return _exec_run_workflow(db, user, payload or {})
    if type_ == "alter_table":
        return _exec_alter_table(db, user, payload or {})
    raise HTTPException(400, f"不支持的动作类型：{type_}")


def _exec_alter_table(db: Session, user: User, payload: dict) -> dict:
    """AI 修改表结构：重新鉴权（仅主人/admin）后执行 ops 序列。"""
    access = get_table_access(db, int(payload.get("table_id") or 0), user)
    if not (access.is_owner or access.is_admin):
        raise HTTPException(404, "数据表不存在")
    ops = payload.get("ops") or []
    if not ops:
        raise HTTPException(400, "没有要执行的结构变更")
    try:
        result = meta_service.alter_business_table(db, access.table, ops)
    except meta_service.MetaError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    log_audit(db, "alter_table", access.table.id, after={"ops": ops}, user=user.username)
    db.commit()
    return {"type": "alter_table", "table_id": access.table.id, "table_label": access.table.label, **result}


def _exec_run_workflow(db: Session, user: User, payload: dict) -> dict:
    """执行用户自己的工作流（同步），返回执行摘要 + run_id 供跳转轨迹页。"""
    from .workflow import engine as wf_engine

    try:
        wf_id = int(payload.get("workflow_id") or 0)
    except (TypeError, ValueError):
        wf_id = 0
    wf = db.get(Workflow, wf_id)
    if not wf:
        raise HTTPException(404, "工作流不存在")
    check_owner_or_admin(wf.user_id, user)
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    result = wf_engine.run_now(wf.id, trigger="manual", trigger_data={"params": params})
    return {
        "type": "run_workflow", "workflow_id": wf.id, "workflow_name": wf.name,
        **(result or {"status": "failed", "error": "执行失败"}),
    }


def _exec_fill(db: Session, user: User, payload: dict) -> dict:
    access = get_table_access(db, int(payload.get("table_id")), user)
    if not access.can_create:
        raise HTTPException(404, "数据表不存在")
    records = payload.get("records") or []
    if not records:
        raise HTTPException(400, "没有要填入的记录")
    if len(records) > FILL_MAX:
        raise HTTPException(400, f"单次最多填入 {FILL_MAX} 条")
    ok, fail, ids = 0, [], []
    for i, rec in enumerate(records):
        try:
            r = dyn_engine.create_record(db, access.table.id, rec, user=user.username)
            ok += 1
            ids.append(r["id"])
        except HTTPException as e:
            fail.append({"index": i, "reason": str(e.detail)[:200]})
        except Exception as e:  # noqa: BLE001 — 单条失败不阻塞其余
            db.rollback()
            fail.append({"index": i, "reason": str(e)[:200]})
    return {"type": "fill_records", "ok": ok, "fail": fail, "record_ids": ids,
            "table_id": access.table.id, "table_label": access.table.label}


def _exec_create_table(db: Session, user: User, payload: dict) -> dict:
    limit = perm_value(db, user, "max_tables")
    if limit is not None:
        owned = db.query(MetaTable).filter(MetaTable.owner_id == user.id).count()
        if owned >= limit:
            raise HTTPException(403, f"已达到数据表上限（{limit} 张），请联系管理员提升额度")
    label = str(payload.get("label") or "").strip()[:64] or "新建数据表"
    try:
        tc = TableCreate(label=label, fields=payload.get("fields") or [], storage_mode="json")
    except Exception as e:  # noqa: BLE001 — pydantic 校验失败统一 400
        raise HTTPException(400, f"字段定义无效：{e}")
    try:
        mt = meta_service.create_business_table(db, tc, owner_id=user.id)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, f"建表失败：{e}")
    log_audit(db, "create_table", mt.id, after={"name": mt.name, "label": mt.label}, user=user.username)
    db.commit()
    return {"type": "create_table", "table_id": mt.id, "table_label": mt.label}


def _exec_create_report(db: Session, user: User, payload: dict) -> dict:
    """创建报表模板（默认不启用推送），复用报表模板的完整校验。"""
    from ..models import ReportTemplate
    from ..schemas import ReportTemplateIn
    from .report_engine import validate_template

    access = get_table_access(db, int(payload.get("table_id")), user)
    tin = ReportTemplateIn(
        name=str(payload.get("name") or "AI 报表")[:128],
        table_id=access.table.id,
        enabled=False,
        range=payload.get("range") or {"mode": "this_week"},
        blocks=payload.get("blocks") or [],
        filter_fields=[],
        schedule={},
        push={},
    )
    validate_template(db, tin)
    tpl = ReportTemplate(user_id=user.id)
    tpl.name = tin.name.strip()
    tpl.table_id = tin.table_id
    tpl.enabled = False
    tpl.range_json = tin.range
    tpl.blocks_json = tin.blocks
    tpl.filters_json = []
    tpl.schedule_json = {}
    tpl.push_json = {}
    db.add(tpl)
    db.commit()
    return {"type": "create_report", "report_id": tpl.id, "name": tpl.name}


def _exec_create_task(db: Session, user: User, payload: dict) -> dict:
    """创建任务规则（默认停用，需到任务页启用），复用任务路由的完整校验。"""
    from ..models import TaskRule
    from ..schemas import TaskRuleIn

    access = get_table_access(db, int(payload.get("table_id")), user)
    try:
        tin = TaskRuleIn(
            name=str(payload.get("name") or "AI 任务")[:128],
            table_id=access.table.id,
            enabled=False,
            condition_mode=payload.get("condition_mode") or "structured",
            condition=payload.get("condition") or {},
            schedule=payload.get("schedule") or {"type": "cron", "expr": "0 9 * * *"},
            action=payload.get("action") or {},
            cooldown_hours=int(payload.get("cooldown_hours") or 24),
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"任务配置无效：{e}")
    from ..routers.tasks import _validate as validate_task  # 延迟导入避免循环依赖
    validate_task(db, tin, user)
    rule = TaskRule(
        user_id=user.id, name=tin.name, table_id=tin.table_id, enabled=False,
        condition_mode=tin.condition_mode, condition_json=tin.condition,
        schedule_json=tin.schedule, action_json=tin.action,
        cooldown_hours=tin.cooldown_hours, max_per_run=tin.max_per_run,
    )
    db.add(rule)
    db.commit()
    from . import scheduler as sched
    sched.reload_jobs()
    return {"type": "create_task", "task_id": rule.id, "name": rule.name}


def _exec_gen_excel(db: Session, user: User, payload: dict) -> dict:
    mode = payload.get("mode")
    if mode == "blank":
        label = str(payload.get("label") or "").strip()[:64] or "表格模板"
        try:
            tc = TableCreate(label=label, fields=payload.get("fields") or [], storage_mode="json")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"字段定义无效：{e}")
        sample_rows = [r for r in (payload.get("sample_rows") or [])[:20] if isinstance(r, list)]
        buf = export_blank_xlsx(tc.label, [f.model_dump() for f in tc.fields], sample_rows)
        filename = f"{tc.label}.xlsx"
    elif mode == "export":
        access = get_table_access(db, int(payload.get("table_id")), user)
        fields = meta_service.get_meta_fields(db, access.table.id)
        fbn = {f.field_name: f for f in fields}
        # 筛选规则重新校验（不信任 chat 输出）
        filters = clean_assistant_filters(payload.get("filters"), fbn, [])
        res = dyn_engine.list_records(db, access.table.id, 1, EXPORT_MAX, filters["rules"], "id", "asc",
                                      page_cap=EXPORT_MAX)
        columns = ([{"prop": f.field_name, "label": f.label} for f in fields]
                   + [{"prop": "created_at", "label": "创建时间"}])
        buf = export_records_xlsx(access.table.label, columns, res["items"])
        filename = f"{access.table.label}-导出.xlsx"
    else:
        raise HTTPException(400, "mode 必须是 blank 或 export")
    file_id = save_generated(buf.getvalue(), filename)
    return {"type": "gen_excel", "file_id": file_id, "filename": filename}
