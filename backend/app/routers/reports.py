"""报表模板管理 + 在线生成 + 导出 + 定时推送。"""
import json
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ReportRunLog, ReportTemplate, User
from ..schemas import ReportTemplateIn
from ..services import scheduler as sched
from ..services.llm import LLMError
from ..services.llm.gateway import assist_report
from ..services.meta_service import get_meta_fields, get_meta_table
from ..services.report_engine import drill_chart, push_template, run_template, validate_template
from ..services.report_export import DEFAULT_ECHARTS_CDN, export_html, export_xlsx
from ..utils.access import check_owner_or_admin, get_table_access
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/reports", tags=["reports"])

RANGE_MODE_LABELS = {
    "today": "今天", "yesterday": "昨天", "past_7d": "近7天", "past_30d": "近30天",
    "this_week": "本周", "last_week": "上周", "this_month": "本月",
    "last_month": "上月", "this_quarter": "本季度", "this_year": "今年", "custom": "自定义",
}


def _out(db: Session, tpl: ReportTemplate) -> dict:
    mt = get_meta_table(db, tpl.table_id)
    last_run = (
        db.query(ReportRunLog)
        .filter(ReportRunLog.template_id == tpl.id)
        .order_by(ReportRunLog.id.desc())
        .first()
    )
    rng = tpl.range_json or {}
    return {
        "id": tpl.id, "name": tpl.name, "description": tpl.description,
        "table_id": tpl.table_id, "table_label": mt.label if mt else f"表#{tpl.table_id}",
        "enabled": tpl.enabled,
        "range": rng, "blocks": tpl.blocks_json or [],
        "filter_fields": tpl.filters_json or [],
        "schedule": tpl.schedule_json or {}, "push": tpl.push_json or {},
        "range_desc": RANGE_MODE_LABELS.get(rng.get("mode") or "this_week", rng.get("mode")),
        "block_count": len(tpl.blocks_json or []),
        "created_at": tpl.created_at.isoformat(sep=" ") if tpl.created_at else None,
        "updated_at": tpl.updated_at.isoformat(sep=" ") if tpl.updated_at else None,
        "last_run": {
            "run_at": last_run.run_at.isoformat(sep=" "),
            "range_label": last_run.range_label, "sent": last_run.sent_count,
            "error": last_run.error,
        } if last_run else None,
    }


def _apply(rule: ReportTemplate, payload: ReportTemplateIn) -> None:
    rule.name = payload.name.strip()
    rule.description = payload.description
    rule.table_id = payload.table_id
    rule.enabled = payload.enabled
    rule.range_json = payload.range
    rule.blocks_json = payload.blocks
    rule.filters_json = payload.filter_fields
    rule.schedule_json = payload.schedule
    rule.push_json = payload.push
    rule.updated_at = datetime.now()


@router.get("")
def list_templates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(ReportTemplate).filter(ReportTemplate.user_id == user.id).order_by(ReportTemplate.id.desc()).all()
    return [_out(db, t) for t in rows]


@router.get("/{tpl_id}")
def get_template(tpl_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = db.get(ReportTemplate, tpl_id)
    if not tpl:
        raise HTTPException(404, "报表模板不存在")
    check_owner_or_admin(tpl.user_id, user)
    return _out(db, tpl)


class AiAssistIn(BaseModel):
    table_id: int
    description: str


@router.post("/ai-assist")
def ai_assist(payload: AiAssistIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """自然语言描述 → LLM 生成报表配置（名称/时间口径/区块），不落库。"""
    if not payload.description.strip():
        raise HTTPException(400, "请填写报表需求描述")
    get_table_access(db, payload.table_id, user)
    fields = get_meta_fields(db, payload.table_id)
    try:
        return assist_report(db, fields, payload.description.strip())
    except LLMError as e:
        raise HTTPException(400, str(e))


@router.post("")
def create_template(payload: ReportTemplateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_table_access(db, payload.table_id, user)
    validate_template(db, payload)
    tpl = ReportTemplate(user_id=user.id)
    _apply(tpl, payload)
    db.add(tpl)
    db.commit()
    sched.reload_jobs()
    return _out(db, tpl)


@router.put("/{tpl_id}")
def update_template(tpl_id: int, payload: ReportTemplateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = db.get(ReportTemplate, tpl_id)
    if not tpl:
        raise HTTPException(404, "报表模板不存在")
    check_owner_or_admin(tpl.user_id, user)
    get_table_access(db, payload.table_id, user)
    validate_template(db, payload)
    _apply(tpl, payload)
    db.commit()
    sched.reload_jobs()
    return _out(db, tpl)


@router.delete("/{tpl_id}")
def delete_template(tpl_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = db.get(ReportTemplate, tpl_id)
    if not tpl:
        raise HTTPException(404, "报表模板不存在")
    check_owner_or_admin(tpl.user_id, user)
    from ..models import SharedLink
    db.query(SharedLink).filter(SharedLink.resource_type == "report", SharedLink.resource_id == tpl.id).delete()
    db.delete(tpl)
    db.commit()
    sched.reload_jobs()
    return {"ok": True}


@router.post("/{tpl_id}/toggle")
def toggle_template(tpl_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = db.get(ReportTemplate, tpl_id)
    if not tpl:
        raise HTTPException(404, "报表模板不存在")
    check_owner_or_admin(tpl.user_id, user)
    tpl.enabled = not tpl.enabled
    db.commit()
    sched.reload_jobs()
    return _out(db, tpl)


def _range_override(range_cfg: dict | None, mode: str | None, start: str | None, end: str | None) -> dict | None:
    """合并 run 请求体 / export query 参数里的口径覆盖。"""
    override = dict(range_cfg or {})
    if mode:
        override["mode"] = mode
    if start:
        override["start"] = start
    if end:
        override["end"] = end
    return override or None


@router.post("/{tpl_id}/run")
def run_report(tpl_id: int, payload: dict | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = db.get(ReportTemplate, tpl_id)
    if not tpl:
        raise HTTPException(404, "报表模板不存在")
    check_owner_or_admin(tpl.user_id, user)
    get_table_access(db, tpl.table_id, user)  # 数据权限跟随表的分享权限（被撤权后不可再跑）
    payload = payload or {}
    return run_template(db, tpl, _range_override(payload.get("range"), None, None, None),
                        viewer_filters=payload.get("filters"))


@router.post("/{tpl_id}/drill")
def report_drill(tpl_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """图表/透视表下钻：{block_id, group_index?, series_index?, range?, filters?} → 该图表单元的明细记录。
    chart 区块 group_index 必填；pivot 区块 group_index=行下标、series_index=列下标，None 表示合计行/列。"""
    tpl = db.get(ReportTemplate, tpl_id)
    if not tpl:
        raise HTTPException(404, "报表模板不存在")
    check_owner_or_admin(tpl.user_id, user)
    get_table_access(db, tpl.table_id, user)
    gi = payload.get("group_index")
    try:
        group_index = int(gi) if gi is not None else None
    except (TypeError, ValueError):
        raise HTTPException(400, "group_index 无效")
    si = payload.get("series_index")
    try:
        series_index = int(si) if si is not None else None
    except (TypeError, ValueError):
        raise HTTPException(400, "series_index 无效")
    return drill_chart(db, tpl, payload.get("block_id") or "", group_index, series_index,
                       _range_override(payload.get("range"), None, None, None), payload.get("filters"))


@router.get("/{tpl_id}/export")
def export_report(tpl_id: int, format: str = "xlsx", mode: str | None = None,
                  start: str | None = None, end: str | None = None, filters: str | None = None,
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    tpl = db.get(ReportTemplate, tpl_id)
    if not tpl:
        raise HTTPException(404, "报表模板不存在")
    check_owner_or_admin(tpl.user_id, user)
    get_table_access(db, tpl.table_id, user)
    viewer_filters = None
    if filters:
        try:
            viewer_filters = json.loads(filters)
        except ValueError:
            raise HTTPException(400, "filters 参数不是合法 JSON")
    result = run_template(db, tpl, _range_override(None, mode, start, end), viewer_filters=viewer_filters)
    base = f"{tpl.name}-{result['range']['label'].split('（')[0]}"

    if format == "xlsx":
        buf = export_xlsx(result)
        filename = quote(f"{base}.xlsx")
        return StreamingResponse(
            buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=utf-8''{filename}"},
        )
    if format == "html":
        from ..services.actions import get_setting
        cdn = get_setting(db, "report_echarts_cdn").get("url") or DEFAULT_ECHARTS_CDN
        html = export_html(result, cdn)
        filename = quote(f"{base}.html")
        return Response(
            html, media_type="text/html",
            headers={"Content-Disposition": f"attachment; filename*=utf-8''{filename}"},
        )
    raise HTTPException(400, "format 只能是 xlsx 或 html")


@router.post("/{tpl_id}/test-push")
def test_push(tpl_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = db.get(ReportTemplate, tpl_id)
    if not tpl:
        raise HTTPException(404, "报表模板不存在")
    check_owner_or_admin(tpl.user_id, user)
    get_table_access(db, tpl.table_id, user)
    result = push_template(tpl_id, trigger="manual")
    if result is None:
        raise HTTPException(404, "报表模板不存在")
    if result.get("error"):
        raise HTTPException(400, result["error"])
    return result


@router.get("/{tpl_id}/runs")
def list_runs(tpl_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = db.get(ReportTemplate, tpl_id)
    if not tpl:
        raise HTTPException(404, "报表模板不存在")
    check_owner_or_admin(tpl.user_id, user)
    rows = (
        db.query(ReportRunLog)
        .filter_by(template_id=tpl_id)
        .order_by(ReportRunLog.id.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": r.id, "trigger": r.trigger,
            "run_at": r.run_at.isoformat(sep=" ") if r.run_at else None,
            "range_label": r.range_label, "sent_count": r.sent_count, "error": r.error,
        }
        for r in rows
    ]
