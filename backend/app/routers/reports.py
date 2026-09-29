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
from ..services import report_dataset as ds_mod
from ..services.report_export import DEFAULT_ECHARTS_CDN, export_html, export_xlsx
from ..utils.access import check_owner_or_admin, get_table_access
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/reports", tags=["reports"])

# 报表模板市场（与工作流模板市场同一模式：/api/report-templates）
templates_router = APIRouter(prefix="/api/report-templates", tags=["report-templates"])


@templates_router.get("")
def list_report_templates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.report_templates import list_templates
    return list_templates(db, user)


class InstallIn(BaseModel):
    with_demo_data: bool = False   # 为新建的表生成 50 条示例数据


@templates_router.post("/{key}/install")
def install_report_template(key: str, payload: InstallIn | None = None,
                            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """一键安装报表模板：复用/建表（可选示例数据）→ 校验 → 落库（默认停用推送）。"""
    from ..services.report_templates import install_template
    return install_template(db, user, key, with_demo_data=(payload or InstallIn()).with_demo_data)

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
        "layout": tpl.layout_json, "source": tpl.source_json,
        "datasets": tpl.datasets_json or [],
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
    rule.enabled = payload.enabled
    rule.range_json = payload.range
    rule.blocks_json = payload.blocks
    rule.layout_json = payload.layout
    rule.source_json = payload.source
    rule.datasets_json = payload.datasets or None
    # table_id 反规范化：v3 取首个数据集的基表（列表展示/旧逻辑兼容），旧格式原样
    rule.table_id = payload.datasets[0]["base_table_id"] if payload.datasets else payload.table_id
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
    append: bool = False   # 已有报表上的追加意图：只生成本次要求的区块


@router.post("/ai-assist")
def ai_assist(payload: AiAssistIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """自然语言描述 → LLM 生成报表配置（名称/时间口径/区块），不落库。"""
    if not payload.description.strip():
        raise HTTPException(400, "请填写报表需求描述")
    get_table_access(db, payload.table_id, user)
    fields = get_meta_fields(db, payload.table_id)
    try:
        return assist_report(db, fields, payload.description.strip(), append=payload.append)
    except LLMError as e:
        raise HTTPException(400, str(e))


@router.post("")
def create_template(payload: ReportTemplateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_table_access(db, payload.table_id, user)
    _check_datasets_access(db, ds_mod.normalize_datasets(payload.datasets or None, payload.table_id, payload.source), user)
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
    _check_datasets_access(db, ds_mod.normalize_datasets(payload.datasets or None, payload.table_id, payload.source), user)
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


@router.post("/{tpl_id}/duplicate")
def duplicate_template(tpl_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """复制报表：区块/布局/数据集全量克隆；推送配置不复制（避免副本自动发推送），默认停用。"""
    tpl = db.get(ReportTemplate, tpl_id)
    if not tpl:
        raise HTTPException(404, "报表模板不存在")
    check_owner_or_admin(tpl.user_id, user)
    new = ReportTemplate(
        user_id=user.id, name=f"{tpl.name}（副本）", description=tpl.description, enabled=False,
        table_id=tpl.table_id,
        range_json=tpl.range_json, blocks_json=tpl.blocks_json, layout_json=tpl.layout_json,
        source_json=tpl.source_json, datasets_json=tpl.datasets_json, filters_json=tpl.filters_json,
        schedule_json={}, push_json={},
    )
    db.add(new)
    db.commit()
    db.refresh(new)
    return _out(db, new)


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


def _check_datasets_access(db: Session, datasets: list, user: User) -> None:
    """数据集的基表与关联表逐张校验数据权限（防借报表绕过表授权）。"""
    for d in datasets or []:
        try:
            get_table_access(db, int(d.get("base_table_id")), user)
        except (TypeError, ValueError):
            raise HTTPException(400, f"数据集基表 id 无效：{d.get('base_table_id')}")
        for j in d.get("joins") or []:
            try:
                get_table_access(db, int(j.get("table_id")), user)
            except (TypeError, ValueError):
                raise HTTPException(400, "关联表 id 无效")


class AiBlockConfigIn(BaseModel):
    block_type: str
    description: str
    fields: list[dict] = []   # 前端数据集字段 [{field_name, label, data_type, options}]（含关联/计算字段）
    current: dict | None = None   # 区块当前配置（编辑语义：按需求修改，其余保留）


@router.post("/ai-block-config")
def ai_block_config(payload: AiBlockConfigIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """AI 帮我设置这个区块：区块类型 + 一句话需求 → 该区块的配置 patch（不落库，前端合并后保存）。"""
    if not payload.description.strip():
        raise HTTPException(400, "请描述你想要的配置")
    from types import SimpleNamespace
    fields = [SimpleNamespace(
        field_name=str(f.get("field_name") or ""), label=str(f.get("label") or f.get("field_name") or ""),
        data_type=str(f.get("data_type") or "varchar"),
        options=f.get("options") if isinstance(f.get("options"), dict) else {},
    ) for f in payload.fields if f.get("field_name")]
    # 文本块没有数据集（不需要字段清单）；其余类型必须有字段
    if not fields and payload.block_type != "text":
        raise HTTPException(400, "缺少数据集字段信息")
    from ..services.llm.gateway import assist_block_config
    try:
        return assist_block_config(db, fields, payload.block_type, payload.description.strip(),
                                   current=payload.current)
    except LLMError as e:
        raise HTTPException(400, str(e))


class ExprCheckIn(BaseModel):
    expr: str
    fields: list[dict] = []   # [{field_name, data_type}]：数据集可用字段（含关联带前缀）


@router.post("/expr-check")
def expr_check(payload: ExprCheckIn, user: User = Depends(get_current_user)):
    """计算字段表达式实时校验（不落库）：语法 + 字段存在性 + 结果类型推断。"""
    from types import SimpleNamespace

    from ..services import expr as expr_mod
    allow = {str(f.get("field_name")) for f in payload.fields if f.get("field_name")}
    fbn = {str(f.get("field_name")): SimpleNamespace(data_type=f.get("data_type"))
           for f in payload.fields if f.get("field_name")}
    try:
        node = expr_mod.parse(payload.expr, allow_fields=allow)
        return {"ok": True, "type": expr_mod.infer_type(node, fbn)}
    except expr_mod.ExprError as e:
        return {"ok": False, "error": str(e)}


@router.post("/{tpl_id}/run")
def run_report(tpl_id: int, payload: dict | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = db.get(ReportTemplate, tpl_id)
    if not tpl:
        raise HTTPException(404, "报表模板不存在")
    check_owner_or_admin(tpl.user_id, user)
    payload = payload or {}
    draft = payload.get("draft")
    if draft is not None:
        # 试运行沙盒：不落库，完整校验（含数据集权限）后用瞬态模板执行
        from types import SimpleNamespace
        if not isinstance(draft, dict):
            raise HTTPException(400, "draft 必须是对象")
        tin = ReportTemplateIn(
            name=tpl.name, table_id=tpl.table_id, enabled=False,
            range=draft.get("range") or tpl.range_json or {},
            blocks=draft.get("blocks") if draft.get("blocks") is not None else (tpl.blocks_json or []),
            layout=draft.get("layout", tpl.layout_json),
            source=draft.get("source", tpl.source_json),
            datasets=draft.get("datasets") if draft.get("datasets") is not None else (tpl.datasets_json or []),
            filter_fields=draft.get("filter_fields") if draft.get("filter_fields") is not None else (tpl.filters_json or []),
            schedule={}, push={},
        )
        validate_template(db, tin)
        _check_datasets_access(db, ds_mod.normalize_datasets(tin.datasets or None, tin.table_id, tin.source), user)
        tpl = SimpleNamespace(
            id=tpl.id, name=tpl.name, table_id=tpl.table_id, user_id=tpl.user_id,
            range_json=tin.range, blocks_json=tin.blocks, layout_json=tin.layout,
            source_json=tin.source, datasets_json=tin.datasets or None, filters_json=tin.filter_fields,
        )
    else:
        _check_datasets_access(db, ds_mod.template_datasets(tpl), user)
    return run_template(db, tpl, _range_override(payload.get("range"), None, None, None),
                        viewer_filters=payload.get("filters"), links=payload.get("links"),
                        block_pages=payload.get("block_pages"), block_overrides=payload.get("block_overrides"))


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
                       _range_override(payload.get("range"), None, None, None), payload.get("filters"),
                       payload.get("links"))


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
    _check_datasets_access(db, ds_mod.template_datasets(tpl), user)
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


@router.post("/{tpl_id}/preview-push")
def preview_push(tpl_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """推送内容预览：运行报表并渲染邮件 HTML / 机器人 Markdown，不实际发送、不写日志。"""
    tpl = db.get(ReportTemplate, tpl_id)
    if not tpl:
        raise HTTPException(404, "报表模板不存在")
    check_owner_or_admin(tpl.user_id, user)
    get_table_access(db, tpl.table_id, user)
    from ..services.report_engine import render_email_html, render_markdown
    result = run_template(db, tpl)
    push = tpl.push_json or {}
    subject = (push.get("subject") or "【{name}】{range_label}") \
        .replace("{name}", tpl.name).replace("{range_label}", result["range"]["label"])
    return {"subject": subject, "html": render_email_html(result), "markdown": render_markdown(result)}


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
