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


@templates_router.post("/{key}/install")
def install_workflow_template(key: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """一键安装模板：自动建表（或复用同名表）→ 生成工作流（默认停用）→ 跳画布确认。"""
    from ..services.workflow.templates import install_template
    try:
        return install_template(db, user, key)
    except WorkflowError as e:
        raise HTTPException(400, str(e))


def _get_own(db: Session, wf_id: int, user: User) -> Workflow:
    wf = db.get(Workflow, wf_id)
    if not wf:
        raise HTTPException(404, "工作流不存在")
    check_owner_or_admin(wf.user_id, user)
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
    return out


@router.get("/node-types")
def node_types(user: User = Depends(get_current_user)):
    """节点目录：前端画布渲染与 AI 生成的共同数据源。"""
    return get_node_types()


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
    if trigger.get("type") == "webhook" and not trigger.get("secret"):
        trigger["secret"] = uuid.uuid4().hex
    wf = Workflow(
        user_id=user.id, name=payload.name, description=payload.description,
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
    if trigger.get("type") == "webhook" and not trigger.get("secret"):
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
    """试运行：真实执行并标记 trigger=test，返回 run id 供查询完整节点轨迹。"""
    _get_own(db, wf_id, user)
    result = engine.run_now(wf_id, trigger="test", trigger_data={"params": (payload or RunIn()).params})
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
    return {"ok": True, "run_id": run.id}
