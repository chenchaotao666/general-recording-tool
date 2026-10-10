"""工作流管理 + 执行 + 审批 + 节点目录。webhook 触发走 public_router（免登录，secret 校验）。"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Workflow, WorkflowNodeRun, WorkflowRun
from ..schemas import WorkflowIn
from ..services import scheduler as sched
from ..services.workflow import engine
from ..services.workflow.engine import WorkflowError
from ..services.workflow.registry import get_node_types
from ..services.workflow.template import jsonable
from ..utils.access import check_owner_or_admin
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/workflows", tags=["workflows"])
public_router = APIRouter(prefix="/api/workflows", tags=["workflows-public"])
templates_router = APIRouter(prefix="/api/workflow-templates", tags=["workflow-templates"])


@templates_router.get("")
def list_workflow_templates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """模板市场：内置场景模板列表（附所需表是否已存在）。"""
    from ..services.workflow.templates import list_templates
    return list_templates(db, user)


class InstallIn(BaseModel):
    with_demo_data: bool = False   # 为新建的表生成 50 条示例数据


@templates_router.post("/{key}/install")
def install_workflow_template(key: str, payload: InstallIn | None = None,
                              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """一键安装模板：自动建表（或复用同名表）→ 生成工作流（默认停用）→ 跳画布确认。"""
    from ..services.workflow.templates import install_template
    try:
        return install_template(db, user, key, with_demo_data=(payload or InstallIn()).with_demo_data)
    except WorkflowError as e:
        raise HTTPException(400, str(e))


def _get_own(db: Session, wf_id: int, user: User) -> Workflow:
    wf = db.get(Workflow, wf_id)
    if not wf:
        raise HTTPException(404, "工作流不存在")
    check_owner_or_admin(wf.user_id, user, db, wf.tenant_id)
    return wf


def _out(db: Session, wf: Workflow) -> dict:
    last_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.workflow_id == wf.id, WorkflowRun.trigger != "test")
        .order_by(WorkflowRun.id.desc())
        .first()
    )
    t = wf.trigger_json or {}
    out = {
        "id": wf.id, "name": wf.name, "description": wf.description,
        "enabled": wf.enabled, "trigger": t,
        "nodes": wf.nodes_json or [], "edges": wf.edges_json or [],
        "created_at": wf.created_at.isoformat(sep=" ") if wf.created_at else None,
        "last_run": {
            "run_at": last_run.started_at.isoformat(sep=" ") if last_run.started_at else None,
            "status": last_run.status, "tokens_used": last_run.tokens_used, "error": last_run.error,
        } if last_run else None,
    }
    if t.get("type") == "webhook":
        out["webhook_url"] = f"/api/workflows/webhook/{wf.id}/{t.get('secret')}"
    if t.get("type") == "form":
        out["form_url"] = f"/form/{wf.id}/{t.get('secret')}"   # 前端公开表单页路由（免登录）
    return out


@router.post("/check")
def check_workflow(payload: WorkflowIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """保存前体检（不落库、不抛 400）：返回全部问题 [{node_id, field, level, message}]，
    前端据此在画布上标注错误节点并给出字段级定位。"""
    return {"issues": engine.lint_definition(db, dict(payload.trigger or {"type": "manual"}),
                                             payload.nodes, payload.edges, user)}


@router.get("/node-types")
def node_types(user: User = Depends(get_current_user)):
    """节点目录：前端画布渲染与 AI 生成的共同数据源。"""
    return get_node_types()


@router.get("/pending-approvals")
def pending_approvals(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """我的待办审批：全部 waiting 状态审批节点中，我是审批人/归属人（admin 全量）的清单。
    注意必须声明在 GET /{wf_id} 之前，否则 "pending-approvals" 会被当作 wf_id 匹配。"""
    rows = (
        db.query(WorkflowNodeRun, WorkflowRun, Workflow)
        .join(WorkflowRun, WorkflowNodeRun.run_id == WorkflowRun.id)
        .join(Workflow, WorkflowRun.workflow_id == Workflow.id)
        .filter(WorkflowNodeRun.node_type == "approval", WorkflowNodeRun.status == "waiting")
        .order_by(WorkflowNodeRun.id.desc())
        .limit(100)
        .all()
    )
    out = []
    for nr, run, wf in rows:
        approvers = ((nr.output_json or {}).get("approval") or {}).get("approver_user_ids") or [wf.user_id]
        # 工作流所属租户的 admin 可见全量（跨租户不可见）
        from ..utils.rbac import tenant_role
        is_admin = tenant_role(db, user, wf.tenant_id) == "admin"
        if not is_admin and user.id not in approvers and user.id != wf.user_id:
            continue
        ap = (nr.output_json or {}).get("approval") or {}
        out.append({
            "node_run_id": nr.id, "run_id": run.id, "workflow_id": wf.id,
            "workflow_name": wf.name, "title": ap.get("title") or "待审批",
            "detail": ap.get("detail") or "",
            "started_at": nr.started_at.isoformat(sep=" ") if nr.started_at else None,
        })
    return out


class AiAssistIn(BaseModel):
    description: str


@router.post("/ai-assist")
def ai_assist(payload: AiAssistIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """自然语言描述 → LLM 生成工作流定义（trigger/nodes/edges），不落库，前端画布加载后确认保存。"""
    if not payload.description.strip():
        raise HTTPException(400, "请填写工作流需求描述")
    from ..services.llm.base import LLMError
    from ..services.workflow.ai_assist import assist_workflow
    try:
        return assist_workflow(db, user, payload.description.strip())
    except LLMError as e:
        raise HTTPException(400, str(e))


class AiNodeConfigIn(BaseModel):
    node_type: str
    description: str
    context: dict | None = None   # 前端画布推导的上下文（条件/多路分支：判断对象候选 + 可用字段）


@router.post("/ai-node-config")
def ai_node_config(payload: AiNodeConfigIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """AI 帮我配这个节点：节点类型 + 一句话需求 → 该节点的 config（schema 校验，不落库）。"""
    from ..services.llm.base import LLMError
    from ..services.workflow.ai_assist import assist_node_config
    try:
        return assist_node_config(db, user, payload.node_type, payload.description, payload.context)
    except (LLMError, WorkflowError) as e:
        raise HTTPException(400, str(e))


@router.post("/{wf_id}/ai-explain")
def ai_explain(wf_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """AI 流程解读：3-5 句大白话说明这个工作流在干什么（接手别人的流程时用）。"""
    wf = _get_own(db, wf_id, user)
    from ..services.workflow.ai_assist import explain_workflow
    try:
        return explain_workflow(db, user, wf)
    except Exception as e:
        raise HTTPException(400, f"解读失败：{e}")


@router.get("")
def list_workflows(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Workflow).filter(Workflow.user_id == user.id).order_by(Workflow.id.desc()).all()
    return [_out(db, w) for w in rows]


@router.post("")
def create_workflow(payload: WorkflowIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    trigger = dict(payload.trigger or {"type": "manual"})
    try:
        engine.validate_definition(db, trigger, payload.nodes, payload.edges, user)
    except WorkflowError as e:
        raise HTTPException(400, str(e))
    if trigger.get("type") in ("webhook", "form") and not trigger.get("secret"):
        trigger["secret"] = uuid.uuid4().hex
    from ..services.tenancy import default_tenant_id
    wf = Workflow(
        user_id=user.id, tenant_id=default_tenant_id(db, user),
        name=payload.name, description=payload.description,
        enabled=payload.enabled, trigger_json=trigger,
        nodes_json=payload.nodes, edges_json=payload.edges,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    sched.reload_jobs()
    return _out(db, wf)


@router.get("/{wf_id}")
def get_workflow(wf_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(db, _get_own(db, wf_id, user))


@router.put("/{wf_id}")
def update_workflow(wf_id: int, payload: WorkflowIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wf = _get_own(db, wf_id, user)
    trigger = dict(payload.trigger or {"type": "manual"})
    try:
        engine.validate_definition(db, trigger, payload.nodes, payload.edges, user)
    except WorkflowError as e:
        raise HTTPException(400, str(e))
    if trigger.get("type") in ("webhook", "form") and not trigger.get("secret"):
        trigger["secret"] = (wf.trigger_json or {}).get("secret") or uuid.uuid4().hex
    wf.name, wf.description, wf.enabled = payload.name, payload.description, payload.enabled
    wf.trigger_json, wf.nodes_json, wf.edges_json = trigger, payload.nodes, payload.edges
    wf.updated_at = datetime.now()
    db.commit()
    sched.reload_jobs()
    return _out(db, wf)


@router.delete("/{wf_id}")
def delete_workflow(wf_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wf = _get_own(db, wf_id, user)
    db.delete(wf)
    db.commit()
    sched.reload_jobs()
    return {"ok": True}


@router.post("/{wf_id}/toggle")
def toggle_workflow(wf_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wf = _get_own(db, wf_id, user)
    wf.enabled = not wf.enabled
    db.commit()
    sched.reload_jobs()
    return _out(db, wf)


class RunIn(BaseModel):
    params: dict = {}
    node_id: str | None = None   # 单节点试运行：执行完该节点即停


@router.post("/{wf_id}/run")
def run_workflow(wf_id: int, payload: RunIn | None = None, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """立即执行一次（同步，返回执行结果摘要）。"""
    _get_own(db, wf_id, user)
    result = engine.run_now(wf_id, trigger="manual", trigger_data={"params": (payload or RunIn()).params})
    return result or {"error": "执行失败"}


@router.post("/{wf_id}/test-run")
def test_run_workflow(wf_id: int, payload: RunIn | None = None, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """试运行：真实执行并标记 trigger=test，返回 run id 供查询完整节点轨迹。
    带 node_id 时执行到该节点为止（单节点试运行）。"""
    wf = _get_own(db, wf_id, user)
    payload = payload or RunIn()
    if payload.node_id and not any(n.get("id") == payload.node_id for n in (wf.nodes_json or [])):
        raise HTTPException(400, f"节点不存在：{payload.node_id}")
    result = engine.run_now(wf_id, trigger="test", trigger_data={"params": payload.params},
                            stop_after=payload.node_id, dry_run=True)   # 试运行沙盒：副作用节点只模拟不真实生效
    return result or {"error": "执行失败"}


@router.get("/{wf_id}/runs")
def list_runs(wf_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_own(db, wf_id, user)
    rows = (
        db.query(WorkflowRun)
        .filter_by(workflow_id=wf_id)
        .order_by(WorkflowRun.id.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": r.id, "trigger": r.trigger, "status": r.status,
            "tokens_used": r.tokens_used, "error": r.error,
            "started_at": r.started_at.isoformat(sep=" ") if r.started_at else None,
            "finished_at": r.finished_at.isoformat(sep=" ") if r.finished_at else None,
        }
        for r in rows
    ]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """执行详情：Run + 全部 NodeRun 轨迹（审批操作也基于这里的 waiting 节点）。"""
    run = db.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(404, "执行记录不存在")
    wf = _get_own(db, run.workflow_id, user)
    node_runs = (
        db.query(WorkflowNodeRun)
        .filter_by(run_id=run_id)
        .order_by(WorkflowNodeRun.id)
        .all()
    )
    return {
        "id": run.id, "workflow_id": wf.id, "workflow_name": wf.name,
        "trigger": run.trigger, "status": run.status,
        "tokens_used": run.tokens_used, "error": run.error,
        "started_at": run.started_at.isoformat(sep=" ") if run.started_at else None,
        "finished_at": run.finished_at.isoformat(sep=" ") if run.finished_at else None,
        "node_runs": [
            {
                "id": nr.id, "node_id": nr.node_id, "node_type": nr.node_type,
                "status": nr.status, "input": nr.input_json, "output": nr.output_json,
                "tokens_used": nr.tokens_used, "duration_ms": nr.duration_ms, "error": nr.error,
                "warnings": nr.warnings_json or [],
                "started_at": nr.started_at.isoformat(sep=" ") if nr.started_at else None,
                "finished_at": nr.finished_at.isoformat(sep=" ") if nr.finished_at else None,
            }
            for nr in node_runs
        ],
    }


class ApproveIn(BaseModel):
    approved: bool
    comment: str = ""


@router.post("/node-runs/{node_run_id}/approve")
def approve_node(node_run_id: int, payload: ApproveIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """审批人通过/驳回：从暂停点恢复执行（同步，返回恢复后的执行摘要）。"""
    try:
        return engine.resume_approval(db, node_run_id, user, payload.approved, payload.comment)
    except WorkflowError as e:
        raise HTTPException(400, str(e))


@public_router.post("/webhook/{wf_id}/{secret}")
async def webhook_trigger(wf_id: int, secret: str, request: Request, db: Session = Depends(get_db)):
    """外部系统回调触发（免登录，URL 即凭证）。只投递不执行，保证回调响应速度。"""
    wf = db.get(Workflow, wf_id)
    t = (wf.trigger_json or {}) if wf else {}
    if not wf or not wf.enabled or t.get("type") != "webhook" or t.get("secret") != secret:
        raise HTTPException(404, "Not found")
    try:
        body = await request.json()
    except Exception:
        body = {}
    params = {**dict(request.query_params), **(body if isinstance(body, dict) else {})}
    run = engine.enqueue_run(db, wf, "webhook", {"params": jsonable(params)})
    tpl = t.get("response_template")
    if tpl:
        # 自定义响应（验签/对接场景）：用 {trigger.params.xxx} 渲染；内容是 JSON 则按 JSON 返回
        import json as _json
        from fastapi.responses import PlainTextResponse
        from ..services.workflow.template import now_vars, render_string
        text = render_string({"trigger": {"params": params}, "now": now_vars()}, str(tpl))
        try:
            return _json.loads(text)
        except ValueError:
            return PlainTextResponse(text)
    return {"ok": True, "run_id": run.id}


# ---------- 免登审批（签名链接，URL 即凭证，7 天有效） ----------

def _approval_by_token(db: Session, token: str) -> WorkflowNodeRun:
    from ..utils.auth import decode_approval_token
    nr = db.get(WorkflowNodeRun, decode_approval_token(token))
    if not nr or nr.node_type != "approval":
        raise HTTPException(404, "审批不存在")
    return nr


@public_router.get("/approval/{token}")
def approval_public_info(token: str, db: Session = Depends(get_db)):
    """免登审批页的信息（标题/详情/状态）。"""
    nr = _approval_by_token(db, token)
    run = db.get(WorkflowRun, nr.run_id)
    wf = db.get(Workflow, run.workflow_id) if run else None
    out = nr.output_json or {}
    ap = out.get("approval") or {}
    return {
        "title": ap.get("title") or "待审批",
        "detail": ap.get("detail") or "",
        "workflow_name": wf.name if wf else "",
        "status": nr.status,                      # waiting / success（已处理）
        "approved": out.get("approved"),
        "comment": out.get("comment") or "",
        "created_at": nr.started_at.isoformat(sep=" ") if nr.started_at else None,
    }


@public_router.post("/approval/{token}")
def approval_public_act(token: str, payload: ApproveIn, db: Session = Depends(get_db)):
    """免登通过/驳回：以工作流归属人身份恢复执行（链接本身即凭证）。"""
    nr = _approval_by_token(db, token)
    if nr.status != "waiting":
        raise HTTPException(400, "该审批已处理")
    run = db.get(WorkflowRun, nr.run_id)
    wf = db.get(Workflow, run.workflow_id) if run else None
    owner = db.get(User, wf.user_id) if wf else None
    if not owner:
        raise HTTPException(404, "审批不存在")
    try:
        return engine.resume_approval(db, nr.id, owner, payload.approved, payload.comment)
    except WorkflowError as e:
        raise HTTPException(400, str(e))


# ---------- 公开表单（表单触发器，免登录，URL 即凭证） ----------

def _get_form_wf(db: Session, wf_id: int, secret: str) -> tuple[Workflow, dict]:
    wf = db.get(Workflow, wf_id)
    t = (wf.trigger_json or {}) if wf else {}
    if not wf or not wf.enabled or t.get("type") != "form" or t.get("secret") != secret:
        raise HTTPException(404, "Not found")
    return wf, t


@public_router.get("/form/{wf_id}/{secret}")
def form_meta(wf_id: int, secret: str, db: Session = Depends(get_db)):
    """公开表单的渲染元数据：表字段（图片字段除外，公开页不支持上传）。"""
    wf, t = _get_form_wf(db, wf_id, secret)
    from ..services import dyn_engine
    mt, fields = dyn_engine.load_meta(db, t["table_id"])
    return {
        "name": wf.name, "description": wf.description or "", "table_label": mt.label,
        "fields": [
            {"field_name": f.field_name, "label": f.label, "data_type": f.data_type,
             "widget": f.widget, "options": f.options or {}, "nullable": f.nullable,
             "default_value": f.default_value}
            for f in fields if f.data_type != "image"
        ],
    }


@public_router.post("/form/{wf_id}/{secret}")
async def form_submit(wf_id: int, secret: str, request: Request, db: Session = Depends(get_db)):
    """公开表单提交：写入数据表（沿用 dyn_engine 校验）+ 触发工作流（trigger.record = 新记录）。"""
    wf, t = _get_form_wf(db, wf_id, secret)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(400, "提交内容格式错误")
    from ..services import dyn_engine
    _, fields = dyn_engine.load_meta(db, t["table_id"])
    allowed = {f.field_name for f in fields if f.data_type != "image"}
    data = {k: v for k, v in body.items() if k in allowed}   # 只收表字段，其余丢弃
    record = dyn_engine.create_record(db, t["table_id"], data, user="公开表单")   # 422 由 dyn_engine 抛出
    run = engine.enqueue_run(db, wf, "form", {"record": jsonable(record)})
    return {"ok": True, "run_id": run.id}
