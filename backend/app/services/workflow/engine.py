"""工作流执行引擎：定义校验 + 主循环 + 任务队列 + 审批恢复。规范 §6。

执行入口两种：
- run_now：同步执行（手动 / 试运行 / 定时调度线程内），调用方等待结果；
- enqueue_run：创建 Run + 投 WorkflowJob，由 process_due_jobs（调度器 5s 轮询）异步执行。
  记录变更 / webhook 触发只投递不执行，保证写入与回调接口的响应速度。
"""
import copy
import re
import threading
import time
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...database import SessionLocal
from ...models import User, Workflow, WorkflowJob, WorkflowNodeRun, WorkflowRun
from ...utils.access import get_table_access
from . import nodes  # noqa: F401  — import 即注册全部内置节点类型
from .nodes.base import NodeContext, NodeResult
from .registry import REGISTRY, validate_config
from .template import jsonable, render_config

MAX_STEPS = 200          # 单 Run 最大节点执行步数，兜底防意外死循环
NODE_ID_RE = re.compile(r"^[a-z0-9_]{1,64}$")

# 节点类型 → 保存时校验的表权限
TABLE_PERM = {"query_records": "can_view", "create_record": "can_create", "update_record": "can_edit"}

_tls = threading.local()


def current_workflow_id() -> int | None:
    """当前线程正在执行的工作流 id（记录触发器据此防止自触发死循环）。"""
    return getattr(_tls, "workflow_id", None)


class WorkflowError(Exception):
    """定义校验 / 恢复审批等业务性错误，路由层转 400。"""


# ---------- 定义校验 ----------

def validate_definition(db: Session, trigger: dict, nodes: list, edges: list, user: User) -> None:
    """保存前校验：节点类型/config、图结构（DAG、单起点、全连通）、触发器、表权限。"""
    if not nodes:
        raise WorkflowError("至少需要一个节点")
    ids = [n.get("id") for n in nodes]
    if len(set(ids)) != len(ids):
        raise WorkflowError("节点 id 重复")
    for n in nodes:
        nid = n.get("id") or ""
        if not NODE_ID_RE.match(nid):
            raise WorkflowError(f"节点 id 非法：{nid}（仅小写字母/数字/下划线，≤64 字符）")
        cls = REGISTRY.get(n.get("type"))
        if cls is None:
            raise WorkflowError(f"未知节点类型：{n.get('type')}")
        errors = validate_config(f"节点 {nid}", cls.config_schema, n.get("config") or {})
        if errors:
            raise WorkflowError(errors[0])
        perm = TABLE_PERM.get(n.get("type"))
        table_id = (n.get("config") or {}).get("table_id")
        if perm and isinstance(table_id, int):
            _check_table(db, table_id, user, perm, f"节点 {nid}")

    edges = edges or []
    idset = set(ids)
    for e in edges:
        if e.get("from") not in idset or e.get("to") not in idset:
            raise WorkflowError("连线引用了不存在的节点")
    starts = [i for i in ids if not any(e.get("to") == i for e in edges)]
    if len(starts) != 1:
        raise WorkflowError("流程必须有且只有一个起始节点（没有入线的节点）")
    # 拓扑排序：判环 + 全连通
    indeg = {i: 0 for i in ids}
    adj = {i: [] for i in ids}
    for e in edges:
        adj[e["from"]].append(e["to"])
        indeg[e["to"]] += 1
    queue = [i for i in ids if indeg[i] == 0]
    seen = 0
    while queue:
        x = queue.pop()
        seen += 1
        for y in adj[x]:
            indeg[y] -= 1
            if indeg[y] == 0:
                queue.append(y)
    if seen != len(ids):
        raise WorkflowError("流程存在循环或孤立节点，v1 不支持回边")

    t = trigger or {}
    ttype = t.get("type") or "manual"
    if ttype in ("interval", "cron"):   # 定时触发：格式与任务模块 schedule_json 一致
        from .. import scheduler as sched   # 延迟 import：scheduler 反向依赖本模块
        if sched.trigger_of(t) is None:
            raise WorkflowError("定时配置无效（间隔分钟 ≥ 1，或合法 cron 表达式）")
    elif ttype in ("record_created", "record_updated"):
        if not isinstance(t.get("table_id"), int):
            raise WorkflowError("请配置监听的数据表")
        _check_table(db, t["table_id"], user, "can_view", "触发器")
    elif ttype in ("webhook", "manual"):
        pass
    else:
        raise WorkflowError(f"未知触发类型：{ttype}")


def _check_table(db: Session, table_id: int, user: User, perm: str, where: str) -> None:
    try:
        access = get_table_access(db, table_id, user)
    except HTTPException:
        raise WorkflowError(f"{where}：数据表不存在或无权限")
    if not getattr(access, perm):
        label = {"can_view": "查看", "can_create": "新增", "can_edit": "编辑"}[perm]
        raise WorkflowError(f"{where}：没有该数据表的{label}权限")


# ---------- 执行 ----------

def _summary(run: WorkflowRun) -> dict:
    return {"id": run.id, "status": run.status, "tokens_used": run.tokens_used or 0, "error": run.error}


def create_run(db: Session, wf: Workflow, trigger: str, trigger_data: dict | None = None) -> WorkflowRun:
    run = WorkflowRun(
        workflow_id=wf.id, trigger=trigger, status="pending",
        context_json={"trigger": jsonable(trigger_data or {}), "nodes": {}},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _enqueue(db: Session, run_id: int, node_id: str | None = None, kind: str = "start",
             execute_after: datetime | None = None) -> None:
    db.add(WorkflowJob(run_id=run_id, node_id=node_id, kind=kind,
                       execute_after=execute_after or datetime.now()))
    db.commit()


def enqueue_run(db: Session, wf: Workflow, trigger: str, trigger_data: dict | None = None) -> WorkflowRun:
    """创建 Run 并投队列，由 process_due_jobs 异步执行。"""
    run = create_run(db, wf, trigger, trigger_data)
    _enqueue(db, run.id, kind="start")
    return run


def run_now(workflow_id: int, trigger: str = "manual", trigger_data: dict | None = None) -> dict | None:
    """同步创建并执行一个 Run（手动 / 试运行 / 定时调度）。"""
    db = SessionLocal()
    try:
        wf = db.get(Workflow, workflow_id)
        if not wf:
            return None
        run_id = create_run(db, wf, trigger, trigger_data).id
    finally:
        db.close()
    return execute_run(run_id)


def run_scheduled(workflow_id: int) -> None:
    """APScheduler 回调：仅 enabled 的工作流才执行。"""
    db = SessionLocal()
    try:
        wf = db.get(Workflow, workflow_id)
        if not wf or not wf.enabled:
            return
    finally:
        db.close()
    run_now(workflow_id, trigger="schedule")


def _successors(edges: list, nid: str, branch: str | None) -> list[str]:
    """后继节点：无 branch 的边恒走；带 branch 的边仅当节点输出 branch 匹配时走。"""
    return [
        e.get("to") for e in edges
        if e.get("from") == nid and (e.get("branch") is None or (branch is not None and e.get("branch") == branch))
    ]


def execute_run(run_id: int, resume_from: str | None = None, retry: bool = False) -> dict | None:
    """主循环。resume_from + retry=False：从该节点的后继继续（审批/延迟恢复）；retry=True：重跑该节点。"""
    db = SessionLocal()
    try:
        run = db.get(WorkflowRun, run_id)
        if not run:
            return None
        if run.status in ("success", "failed", "cancelled"):
            return _summary(run)
        wf = db.get(Workflow, run.workflow_id)
        if not wf:
            return None
        run.status = "running"
        db.commit()

        # 必须深拷贝：直接改 ORM 加载的 JSON 对象会污染"原始值"，
        # flush 时新旧值相等导致 UPDATE 被跳过（单节点 Run 会丢 context）
        context = copy.deepcopy(run.context_json) or {"trigger": {}, "nodes": {}}
        context.setdefault("nodes", {})
        nodes_by_id = {n["id"]: n for n in (wf.nodes_json or [])}
        edges = wf.edges_json or []
        user = db.get(User, wf.user_id)
        username = user.username if user else str(wf.user_id)

        if resume_from:
            if retry:
                queue = [resume_from]
            else:
                prev = context["nodes"].get(resume_from) or {}
                queue = _successors(edges, resume_from, prev.get("branch"))
        else:
            starts = [nid for nid in nodes_by_id if not any(e.get("to") == nid for e in edges)]
            queue = starts[:1]

        steps = 0
        _tls.workflow_id = wf.id
        try:
            while queue and steps < MAX_STEPS:
                nid = queue.pop(0)
                node = nodes_by_id.get(nid)
                if not node:
                    continue
                steps += 1
                rendered = render_config(context, node.get("config") or {})
                nr = WorkflowNodeRun(
                    run_id=run.id, node_id=nid, node_type=node.get("type"),
                    status="running", input_json=jsonable(rendered), started_at=datetime.now(),
                )
                db.add(nr)
                db.commit()

                t0 = time.perf_counter()
                try:
                    impl_cls = REGISTRY.get(node.get("type"))
                    if impl_cls is None:
                        raise WorkflowError(f"未知节点类型：{node.get('type')}")
                    nctx = NodeContext(
                        db=db, workflow=wf, run_id=run.id,
                        user_id=wf.user_id, username=username,
                        context=context, config=rendered,
                    )
                    result = impl_cls().execute(nctx)
                    if not isinstance(result, NodeResult):
                        raise WorkflowError("节点未返回 NodeResult")
                except Exception as e:  # noqa: BLE001 — 节点任何异常都落日志，按 on_error 处理
                    result = NodeResult(status="failed", error=str(e)[:500])

                nr.status = result.status if result.status in ("success", "waiting") else "failed"
                nr.output_json = jsonable(result.output)
                nr.error = result.error
                nr.tokens_used = result.tokens_used or 0
                nr.duration_ms = int((time.perf_counter() - t0) * 1000)
                nr.finished_at = datetime.now()
                run.tokens_used = (run.tokens_used or 0) + nr.tokens_used
                context["nodes"][nid] = jsonable(result.output)
                run.context_json = dict(context)   # JSON 列需整体重赋值才触发 UPDATE
                db.commit()

                if result.status == "waiting":
                    run.status = "waiting"
                    if result.resume_after:   # delay 节点：到期自动从后继继续
                        _enqueue(db, run.id, node_id=nid, kind="resume", execute_after=result.resume_after)
                    db.commit()
                    return _summary(run)

                if result.status == "failed":
                    on_error = node.get("on_error") or {}
                    policy = on_error.get("policy") or "stop"
                    if policy == "retry":
                        max_attempts = int(on_error.get("max_attempts") or 3)
                        fails = db.query(WorkflowNodeRun).filter_by(
                            run_id=run.id, node_id=nid, status="failed").count()
                        if fails < max_attempts:
                            backoff = int(on_error.get("backoff_seconds") or 60)
                            _enqueue(db, run.id, node_id=nid, kind="retry",
                                     execute_after=datetime.now() + timedelta(seconds=backoff * (2 ** (fails - 1))))
                            run.status = "waiting"
                            db.commit()
                            return _summary(run)
                        policy = "stop"   # 重试耗尽，降级为 stop
                    if policy == "continue":
                        queue.extend(_successors(edges, nid, None))
                        continue
                    run.status = "failed"
                    run.error = result.error
                    run.finished_at = datetime.now()
                    db.commit()
                    return _summary(run)

                queue.extend(_successors(edges, nid, result.output.get("branch")))

            run.status = "success" if steps < MAX_STEPS else "failed"
            if steps >= MAX_STEPS:
                run.error = f"超过最大执行步数（{MAX_STEPS}），疑似配置错误"
            run.finished_at = datetime.now()
            db.commit()
            return _summary(run)
        finally:
            _tls.workflow_id = None
    finally:
        db.close()


# ---------- 任务队列 ----------

def process_due_jobs(limit: int = 10) -> None:
    """领取到期 job 并执行。由调度器每 5 秒轮询（单进程部署足够）。"""
    db = SessionLocal()
    due = []
    try:
        jobs = (
            db.query(WorkflowJob)
            .filter(WorkflowJob.status == "pending", WorkflowJob.execute_after <= datetime.now())
            .order_by(WorkflowJob.id)
            .limit(limit)
            .all()
        )
        for j in jobs:
            j.status = "running"
            j.locked_at = datetime.now()
            due.append((j.id, j.run_id, j.kind, j.node_id))
        db.commit()
    finally:
        db.close()

    for job_id, run_id, kind, node_id in due:
        try:
            if kind == "start":
                execute_run(run_id)
            elif kind == "resume":
                execute_run(run_id, resume_from=node_id)
            elif kind == "retry":
                execute_run(run_id, resume_from=node_id, retry=True)
            _finish_job(job_id, "done")
        except Exception as e:  # noqa: BLE001 — 单个 job 失败不影响其他
            print(f"[workflow] job {job_id} 执行异常：{e}", flush=True)
            _retry_or_kill_job(job_id)


def _finish_job(job_id: int, status: str) -> None:
    db = SessionLocal()
    try:
        j = db.get(WorkflowJob, job_id)
        if j:
            j.status = status
            db.commit()
    finally:
        db.close()


def _retry_or_kill_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        j = db.get(WorkflowJob, job_id)
        if j:
            j.attempts = (j.attempts or 0) + 1
            if j.attempts >= 5:
                j.status = "dead"
            else:
                j.status = "pending"
                j.execute_after = datetime.now() + timedelta(seconds=60 * j.attempts)
            db.commit()
    finally:
        db.close()


# ---------- 审批恢复 ----------

def resume_approval(db: Session, node_run_id: int, user: User, approved: bool, comment: str = "") -> dict:
    """审批人点通过/驳回：补写节点输出，从后继节点同步恢复执行。"""
    nr = db.get(WorkflowNodeRun, node_run_id)
    if not nr or nr.node_type != "approval" or nr.status != "waiting":
        raise WorkflowError("该审批不存在或已处理")
    run = db.get(WorkflowRun, nr.run_id)
    wf = db.get(Workflow, run.workflow_id)
    if not run or not wf:
        raise WorkflowError("执行记录不存在")
    out = nr.output_json or {}
    approvers = (out.get("approval") or {}).get("approver_user_ids") or [wf.user_id]
    if user.role != "admin" and user.id not in approvers and user.id != wf.user_id:
        raise WorkflowError("你不是该审批的审批人")

    nr.output_json = {**out, "approved": bool(approved), "comment": comment or "", "approver_id": user.id}
    nr.status = "success"
    nr.finished_at = datetime.now()
    context = copy.deepcopy(run.context_json) or {"trigger": {}, "nodes": {}}   # 深拷贝原因同上
    context.setdefault("nodes", {})[nr.node_id] = jsonable(nr.output_json)
    run.context_json = context
    db.commit()
    run_id = run.id
    node_id = nr.node_id
    return execute_run(run_id, resume_from=node_id)
