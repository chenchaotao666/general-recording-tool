"""工作流执行引擎：定义校验 + 主循环 + 任务队列 + 审批恢复。规范 §6。

执行入口两种：
- run_now：同步执行（手动 / 试运行 / 定时调度线程内），调用方等待结果；
- enqueue_run：创建 Run + 投 WorkflowJob，由 process_due_jobs（调度器 5s 轮询）异步执行。
  记录变更 / webhook 触发只投递不执行，保证写入与回调接口的响应速度。
"""
import copy
import difflib
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
from .registry import REGISTRY, _TYPE_CHECKS, validate_config  # noqa: F401 — validate_config 供外部复用
from .template import VAR_TOKEN_RE, jsonable, now_vars, render_config, split_filter, suggest_var

MAX_STEPS = 1000         # 单 Run 最大节点执行步数（循环每轮计步），兜底防意外死循环
NODE_ID_RE = re.compile(r"^[a-z0-9_]{1,64}$")

# 节点类型 → 保存时校验的表权限
TABLE_PERM = {"query_records": "can_view", "create_record": "can_create", "update_record": "can_edit"}

_tls = threading.local()


def current_workflow_id() -> int | None:
    """当前线程正在执行的工作流 id（记录触发器据此防止自触发死循环）。"""
    return getattr(_tls, "workflow_id", None)


def call_stack() -> list[int]:
    """当前线程的工作流调用栈（子流程调用时逐层压入），供子流程节点防循环调用。"""
    return getattr(_tls, "stack", [])


MAX_CALL_DEPTH = 3   # 子流程嵌套上限


class WorkflowError(Exception):
    """定义校验 / 恢复审批等业务性错误，路由层转 400。"""


# ---------- 定义校验 / 保存前体检（lint） ----------

def _find_back_edges(nodes_by_id: dict, edges: list) -> set:
    """回边 = 指向 foreach 节点、且源头可从该 foreach 到达的边（循环体的回路）。

    逐个 foreach 计算：剔除指向它自己的边后做可达性分析，能从它出发走到的节点
    再指回它的边即回边。DAG 校验时剔除回边，执行时据此区分「新鲜入口 / 循环继续」。
    """
    foreach_ids = {nid for nid, n in nodes_by_id.items() if n.get("type") == "foreach"}
    backs = set()
    for f in foreach_ids:
        adj = {}
        for e in edges:
            if e.get("to") == f:
                continue
            adj.setdefault(e.get("from"), []).append(e.get("to"))
        seen, stack = set(), [f]
        while stack:
            x = stack.pop()
            for y in adj.get(x, []):
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        for e in edges:
            if e.get("to") == f and e.get("from") in seen:
                backs.add((e.get("from"), f))
    return backs


def _config_issues(nid: str, cls, config: dict) -> list[tuple[str | None, str]]:
    """单节点配置校验，收集全部字段错误（field, message），语义与 registry.validate_config 一致。
    含 { 的字符串视为模板表达式，跳过类型/枚举校验（渲染发生在执行前）。"""
    out = []
    schema = cls.config_schema or {}
    props = schema.get("properties") or {}
    config = config or {}
    for req in schema.get("required") or []:
        v = config.get(req)
        if v is None or (isinstance(v, str) and not v.strip()):
            out.append((req, f"节点 {nid}：缺少必填配置 {req}"))
    for key, spec in props.items():
        if key not in config or config[key] is None:
            continue
        v = config[key]
        if isinstance(v, str) and "{" in v:
            continue  # 模板字段
        expected = spec.get("type")
        if expected in _TYPE_CHECKS and not _TYPE_CHECKS[expected](v):
            out.append((key, f"节点 {nid}：配置 {key} 应为 {expected}"))
        if "enum" in spec and v not in spec["enum"]:
            out.append((key, f"节点 {nid}：配置 {key} 取值无效（可选：{'/'.join(map(str, spec['enum']))}）"))
    return out


def _send_message_issues(db: Session, nid: str, config: dict) -> list[tuple[str, str | None, str]]:
    """发送通知节点的通道前置检查（level, field, message）：
    把执行期才报的通道配置问题提前到保存前体检。模板表达式（含 {）渲染期才有值，跳过。"""
    out = []
    ch = config.get("channel")
    if not isinstance(ch, str) or "{" in ch:
        return out

    def filled(k: str) -> bool:
        v = config.get(k)
        return isinstance(v, str) and bool(v.strip()) and "{" not in v

    if ch in ("wecom", "dingtalk") and not filled("webhook_url"):
        name = "企业微信" if ch == "wecom" else "钉钉"
        out.append(("error", "webhook_url",
                    f"节点 {nid}：{name}机器人通道必须填 Webhook 地址（群聊 → 添加机器人 → 复制 Webhook）"))
    if ch in ("email", "sms") and not filled("recipients"):
        label = "接收邮箱" if ch == "email" else "接收手机号"
        out.append(("error", "recipients", f"节点 {nid}：{label}未填（可填固定值或插入变量）"))
    # 全局通道设置：缺失时执行必失败，但属于环境配置，给 warning 不阻断保存
    from .. import actions
    if ch == "email" and not actions.get_setting(db, "smtp").get("host"):
        out.append(("warning", "channel",
                    f"节点 {nid}：SMTP 邮件服务未配置，执行会失败——请到「设置-通知渠道」配置"))
    if ch == "sms" and not actions.get_setting(db, "sms_gateway").get("url_template"):
        out.append(("warning", "channel",
                    f"节点 {nid}：短信网关未配置，执行会失败——请到「设置-通知渠道」配置 URL 模板"))
    if ch == "webhook" and not filled("webhook_url") and not actions.get_setting(db, "webhook").get("url"):
        out.append(("error", "webhook_url",
                    f"节点 {nid}：未配置 Webhook 地址（在节点里填，或在「设置-通知渠道」配置全局地址）"))
    return out


def _node_issues(db: Session, n: dict, user: User) -> list[tuple[str | None, str]]:
    """单节点的全部错误（field, message）：类型/配置/表权限/子流程约束。"""
    nid = n.get("id") or ""
    if not NODE_ID_RE.match(nid):
        return [(None, f"节点 id 非法：{nid}（仅小写字母/数字/下划线，≤64 字符）")]
    cls = REGISTRY.get(n.get("type"))
    if cls is None:
        return [(None, f"未知节点类型：{n.get('type')}")]
    if n.get("disabled"):
        return []   # 停用的节点不参与配置/权限校验，允许保存半成品
    out = _config_issues(nid, cls, n.get("config") or {})
    perm = TABLE_PERM.get(n.get("type"))
    table_id = (n.get("config") or {}).get("table_id")
    if perm and isinstance(table_id, int):
        try:
            _check_table(db, table_id, user, perm, f"节点 {nid}")
        except WorkflowError as e:
            out.append(("table_id", str(e)))
    if n.get("type") == "sub_workflow":
        sub_id = (n.get("config") or {}).get("workflow_id")
        if isinstance(sub_id, int):
            sub = db.get(Workflow, sub_id)
            if not sub or (sub.user_id != user.id and user.role != "admin"):
                out.append(("workflow_id", f"节点 {nid}：子流程不存在或无权限"))
            elif (sub.trigger_json or {}).get("type", "manual") != "manual":
                out.append(("workflow_id", f"节点 {nid}：子流程「{sub.name}」的触发方式必须是「被动调用」（被调用的流程不应有自己的自动触发器）"))
    if n.get("type") == "push_report":
        from ...models import ReportTemplate
        rid = (n.get("config") or {}).get("report_id")
        if not isinstance(rid, int):
            out.append(("report_id", f"节点 {nid}：未选择要推送的报表"))
        else:
            tpl = db.get(ReportTemplate, rid)
            if not tpl or (tpl.user_id != user.id and user.role != "admin"):
                out.append(("report_id", f"节点 {nid}：报表不存在或无权限"))
            else:
                push = tpl.push_json or {}
                has_ch = bool(str(push.get("recipients") or "").strip()) or any(
                    (w.get("url") or "").strip() for w in (push.get("webhooks") or []))
                if not has_ch:
                    out.append(("report_id", f"节点 {nid}：报表「{tpl.name}」没配推送渠道（到报表设置里配收件邮箱/群机器人）"))
    return out


def _graph_issues(nodes: list, edges: list) -> list[tuple[str | None, str]]:
    """图结构错误（node_id, message）：边引用、foreach 接线、单起点、DAG 全连通。"""
    out = []
    ids = [n.get("id") for n in nodes]
    idset = set(ids)
    for e in edges:
        if e.get("from") not in idset or e.get("to") not in idset:
            out.append((None, "连线引用了不存在的节点"))
            break
    nodes_by_id = {n["id"]: n for n in nodes}
    backs = _find_back_edges(nodes_by_id, edges)
    dag_edges = [e for e in edges if (e.get("from"), e.get("to")) not in backs]

    # 逐条处理节点的接线规则：出边只能走「每条/完成」两个出口，循环体末尾必须有回边
    for n in nodes:
        if n.get("type") != "foreach" or n.get("disabled"):
            continue
        outs = [e for e in edges if e.get("from") == n["id"]]
        if any(e.get("branch") not in ("loop", "done") for e in outs):
            out.append((n["id"], f"节点 {n['id']}（逐条处理）的出边必须从「每条」或「完成」出口连出"))
        if not any(e.get("branch") == "loop" for e in outs):
            out.append((n["id"], f"节点 {n['id']}（逐条处理）：请把「每条」出口连到循环体"))
        if not any(e.get("branch") == "done" for e in outs):
            out.append((n["id"], f"节点 {n['id']}（逐条处理）：请把「完成」出口连到后续节点"))
        if not any(t == n["id"] for _, t in backs):
            out.append((n["id"], f"节点 {n['id']}（逐条处理）：循环体末尾要连回本节点形成循环"))

    if ids:
        starts = [i for i in ids if not any(e.get("to") == i for e in dag_edges)]
        if len(starts) != 1:
            out.append((None, "流程必须有且只有一个起始节点（没有入线的节点）"))
        # 拓扑排序（剔除回边后）：判环 + 全连通
        indeg = {i: 0 for i in ids}
        adj = {i: [] for i in ids}
        for e in dag_edges:
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
            out.append((None, "流程存在循环或孤立节点（只有逐条处理节点的循环体允许连回）"))
    return out


def _trigger_issues(db: Session, trigger: dict, user: User) -> list[str]:
    t = trigger or {}
    ttype = t.get("type") or "manual"
    if ttype in ("interval", "cron"):   # 定时触发：格式与任务模块 schedule_json 一致
        from .. import scheduler as sched   # 延迟 import：scheduler 反向依赖本模块
        if sched.trigger_of(t) is None:
            return ["定时配置无效（间隔分钟 ≥ 1，或合法 cron 表达式）"]
    elif ttype in ("record_created", "record_updated"):
        if not isinstance(t.get("table_id"), int):
            return ["请配置监听的数据表"]
        try:
            _check_table(db, t["table_id"], user, "can_view", "触发器")
        except WorkflowError as e:
            return [str(e)]
    elif ttype == "form":
        if not isinstance(t.get("table_id"), int):
            return ["请配置表单写入的数据表"]
        try:
            _check_table(db, t["table_id"], user, "can_create", "触发器")
        except WorkflowError as e:
            return [str(e)]
    elif ttype in ("webhook", "manual"):
        pass
    else:
        return [f"未知触发类型：{ttype}"]
    return []


# ---------- lint 专用：变量静态校验 + 悬空出口（warning 级，不阻断保存） ----------

# 变量选择器/AI 预设里的占位符：提示用户替换成真实字段名
_PLACEHOLDER_SEGS = ("字段名", "参数名", "键名")


def _iter_strings(v, top_key=None):
    """递归产出 config 里的全部字符串（附顶层配置 key，供问题定位到字段）。"""
    if isinstance(v, str):
        yield top_key, v
    elif isinstance(v, dict):
        for k, x in v.items():
            yield from _iter_strings(x, top_key if top_key is not None else k)
    elif isinstance(v, list):
        for x in v:
            yield from _iter_strings(x, top_key)


def _ancestors_map(ids: list, edges: list) -> dict:
    parents = {}
    for e in edges:
        parents.setdefault(e.get("to"), []).append(e.get("from"))
    out = {}
    for i in ids:
        seen, stack = set(), list(parents.get(i, []))
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            stack.extend(parents.get(x, []))
        out[i] = seen
    return out


def _trigger_field_names(db: Session, t: dict) -> list[str] | None:
    """触发器监听表的字段名清单（含系统字段），无法确定时返回 None（跳过字段级校验）。"""
    if (t or {}).get("type") not in ("record_created", "record_updated", "form"):
        return None
    tid = t.get("table_id")
    if not isinstance(tid, int):
        return None
    try:
        from ... import dyn_engine
        _, fields = dyn_engine.load_meta(db, tid)
        return [f.field_name for f in fields] + ["id", "created_at", "updated_at"]
    except Exception:   # noqa: BLE001 — 表不可用已由触发器校验报错，这里静默跳过字段级检查
        return None


def _static_var_candidates(nodes: list, trig_fields: list[str] | None, trig_type: str) -> list[str]:
    """lint 期的可引用变量候选集（无运行时数据，只到「节点输出键 / 触发记录字段」层级）。"""
    cands = [f"now.{k}" for k in now_vars()]
    if trig_type in ("record_created", "record_updated", "form"):
        cands.append("trigger.record")
        for f in trig_fields or []:
            cands.append(f"trigger.record.{f}")
    if trig_type == "record_updated":
        cands.append("trigger.old_record")
        for f in trig_fields or []:
            cands.append(f"trigger.old_record.{f}")
    for n in nodes:
        cls = REGISTRY.get(n.get("type"))
        for key in ((cls.output_schema or {}).get("properties") or {}):
            cands.append(f"nodes.{n['id']}.{key}")
    return cands


def _lint_var_path(path: str, node_id: str, nodes_by_id: dict, ancestors: dict,
                   trig_fields: list[str] | None, trig_type: str, candidates: list[str]) -> str | None:
    """静态检查一条变量路径，返回 warning 文案（None = 没问题）。只查可静态确定的错误。"""
    p = path.strip()
    segs = p.split(".")
    if any(s in _PLACEHOLDER_SEGS for s in segs) or "在此插入" in p:
        return f"变量 {{{p}}} 里的占位符还没替换成真实的字段/参数名"
    root = segs[0]
    if root not in ("trigger", "nodes", "now"):
        sug = difflib.get_close_matches(p, candidates, n=1, cutoff=0.45)
        return f"无法识别的变量 {{{p}}}（根应为 trigger/nodes/now）" + (f"，是否想填 {{{sug[0]}}}？" if sug else "")
    if root == "now":
        if len(segs) < 2 or segs[1] not in now_vars():
            sug = difflib.get_close_matches(p, [c for c in candidates if c.startswith("now.")], n=1, cutoff=0.4)
            return f"时间变量 {{{p}}} 不存在" + (f"，是否想填 {{{sug[0]}}}？" if sug else "")
        return None
    if root == "trigger":
        if len(segs) < 2:
            return f"变量 {{{p}}} 写法不完整"
        sub = segs[1]
        if sub == "params":
            return None   # 参数键由调用方决定，静态无法校验
        if sub == "record":
            if trig_type not in ("record_created", "record_updated", "form"):
                return f"当前触发方式没有「触发记录」可引用（{{{p}}}）"
        elif sub == "old_record":
            if trig_type != "record_updated":
                return f"只有「记录修改时」触发器才有变更前记录（{{{p}}}）"
        else:
            return f"触发器变量只有 record / old_record / params，无法识别 {{{p}}}"
        if len(segs) >= 3 and not segs[2].isdigit() and trig_fields:
            if segs[2] not in trig_fields:
                pool = [c for c in candidates if c.startswith(f"trigger.{sub}.")]
                sug = difflib.get_close_matches(p, pool, n=1, cutoff=0.5)
                return f"触发记录里没有字段「{segs[2]}」（{{{p}}}）" + (f"，是否想填 {{{sug[0]}}}？" if sug else "")
        return None
    # root == "nodes"
    if len(segs) < 2:
        return f"变量 {{{p}}} 写法不完整（应为 {{nodes.节点id.输出键}}）"
    nid = segs[1]
    if nid not in nodes_by_id:
        sug = difflib.get_close_matches(nid, list(nodes_by_id), n=1, cutoff=0.5)
        return f"变量引用了不存在的节点「{nid}」（{{{p}}}）" + (f"，是否想填「{sug[0]}」？" if sug else "")
    if nid != node_id and nid not in ancestors.get(node_id, set()):
        return f"节点「{nid}」不是本节点的上游（{{{p}}}），执行时取不到值"
    if len(segs) < 3:
        return None   # 两段式 {nodes.x} = 节点整体输出（dict），合法（如条件分支判断审批结果 {nodes.a_1}）
    key = segs[2]
    if key.isdigit():
        return None
    cls = REGISTRY.get(nodes_by_id[nid].get("type"))
    out_keys = list(((cls.output_schema if cls else {}) or {}).get("properties") or {})
    if out_keys and key not in out_keys:
        sug = difflib.get_close_matches(p, [f"nodes.{nid}.{k}" for k in out_keys], n=1, cutoff=0.45)
        return f"节点「{nid}」没有输出「{key}」（{{{p}}}）" + (f"，是否想填 {{{sug[0]}}}？" if sug else "")
    return None


def _dangling_warnings(nodes: list, edges: list) -> list[tuple[str, str]]:
    """分支类节点的悬空出口（命中该分支时流程会无声结束），warning 级。"""
    out = []
    for n in nodes:
        if n.get("disabled"):
            continue
        ntype = n.get("type")
        outs = {e.get("branch") for e in edges if e.get("from") == n["id"]}
        if ntype == "condition":
            for b, label in (("true", "是"), ("false", "否")):
                if b not in outs:
                    out.append((n["id"], f"「{label}」出口没有连线：条件走该分支时流程到此结束"))
        elif ntype == "switch":
            labels = [c.get("label").strip() for c in (n.get("config") or {}).get("cases") or [] if c.get("label", "").strip()]
            for lb in labels + ["default"]:
                if lb not in outs:
                    shown = "默认" if lb == "default" else lb
                    out.append((n["id"], f"分支「{shown}」出口没有连线：命中该分支时流程到此结束"))
    return out


def lint_definition(db: Session, trigger: dict, nodes: list, edges: list, user: User) -> list[dict]:
    """保存前体检：收集全部问题返回 [{node_id, field, level, message}]，不抛异常。
    level=error 与 validate_definition 同源（保存会被拒）；warning 可保存但建议处理。"""
    nodes = nodes or []
    edges = edges or []
    issues = []

    def err(node_id, field, msg):
        issues.append({"node_id": node_id, "field": field, "level": "error", "message": msg})

    def warn(node_id, field, msg):
        issues.append({"node_id": node_id, "field": field, "level": "warning", "message": msg})

    ids = [n.get("id") for n in nodes]
    if len(set(ids)) != len(ids):
        err(None, None, "节点 id 重复")
    nodes_by_id = {n["id"]: n for n in nodes if n.get("id")}

    for n in nodes:
        for field, msg in _node_issues(db, n, user):
            err(n.get("id"), field, msg)
        if not n.get("disabled"):
            for level, field, msg in _send_message_issues(db, n.get("id") or "", n.get("config") or {}):
                (err if level == "error" else warn)(n.get("id"), field, msg)
    for node_id, msg in _graph_issues(nodes, edges):
        err(node_id, None, msg)
    for msg in _trigger_issues(db, trigger, user):
        err("trigger", None, msg)

    # ---- warning 级 ----
    for node_id, msg in _dangling_warnings(nodes, edges):
        warn(node_id, None, msg)

    t = trigger or {}
    trig_type = t.get("type") or "manual"
    trig_fields = _trigger_field_names(db, t)
    candidates = _static_var_candidates(nodes, trig_fields, trig_type)
    ancestors = _ancestors_map(ids, edges)
    for n in nodes:
        if n.get("disabled"):
            continue
        nid = n.get("id")
        seen_paths = set()
        for key, s in _iter_strings(n.get("config") or {}):
            for m in VAR_TOKEN_RE.finditer(s):
                p = split_filter(m.group(1))[0]   # 剥掉「| 表格」等过滤器再校验路径
                if not p or p in seen_paths:
                    continue
                seen_paths.add(p)
                msg = _lint_var_path(p, nid, nodes_by_id, ancestors, trig_fields, trig_type, candidates)
                if msg:
                    warn(nid, key, msg)
    return issues


def validate_definition(db: Session, trigger: dict, nodes: list, edges: list, user: User) -> None:
    """保存前校验：节点类型/config、图结构（DAG、单起点、全连通）、触发器、表权限。
    允许只有触发器、零节点的半成品（执行时什么都不做），与「停用节点不校验」同一思路。"""
    for issue in lint_definition(db, trigger, nodes, edges, user):
        if issue["level"] == "error":
            raise WorkflowError(issue["message"])


def _check_table(db: Session, table_id: int, user: User, perm: str, where: str) -> None:
    try:
        access = get_table_access(db, table_id, user)
    except HTTPException:
        raise WorkflowError(f"{where}：数据表不存在或无权限")
    if not getattr(access, perm):
        label = {"can_view": "查看", "can_create": "新增", "can_edit": "编辑"}[perm]
        raise WorkflowError(f"{where}：没有该数据表的{label}权限")


# ---------- 执行 ----------

def _var_warnings(context: dict, missing: list) -> list[str]:
    """把渲染期未命中的变量路径转成中文告警（附「是否想填 xxx」模糊建议）。"""
    outs = []
    for p in missing:
        msg = f"变量 {{{p}}} 没有取到值（已按空值渲染）"
        sug = suggest_var(context, p)
        if sug:
            msg += f"，是否想填 {{{sug}}}？"
        outs.append(msg)
    return outs


def _notify_run_failed(db: Session, wf: Workflow, run: WorkflowRun, where: str, error: str | None) -> None:
    """失败主动通知：给归属人发站内通知（失败节点 + 原因 + 跳详情链接）。
    试运行（沙盒）不通知；通知本身失败不阻断主流程。"""
    if run.trigger == "test":
        return
    try:
        from ..notify import notify_user   # engine 在 services/workflow 下，notify 在 services 下
        notify_user(db, wf.user_id, f"【{wf.name}】执行失败",
                    f"节点 {where} 失败：{(error or '')[:200]}\n点击查看详情",
                    link=f"/workflows/runs/{run.id}")
        db.commit()
    except Exception as e:  # noqa: BLE001
        print(f"[workflow] 失败通知发送失败：{e}", flush=True)


def _summary(run: WorkflowRun) -> dict:
    return {"id": run.id, "status": run.status, "tokens_used": run.tokens_used or 0, "error": run.error}


def _latest_record(db: Session, table_id: int | None) -> dict | None:
    """取某表最新一条记录（手动执行 record 触发流程时模拟触发数据用）；失败静默返回 None。"""
    if not isinstance(table_id, int):
        return None
    try:
        from .nodes.data_nodes import query_table
        rows = query_table(db, table_id, None, 1, "id", True)
        return rows[0] if rows else None
    except Exception:  # noqa: BLE001 — 表不存在等场景：无模拟数据，交给下游节点报错
        return None


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


def run_now(workflow_id: int, trigger: str = "manual", trigger_data: dict | None = None,
            stop_after: str | None = None, dry_run: bool = False) -> dict | None:
    """同步创建并执行一个 Run（手动 / 试运行 / 定时调度）。stop_after：执行完该节点即停。
    dry_run：试运行沙盒——有副作用的节点（发通知/HTTP/写表/审批/延迟/子流程）只算效果不真实生效。"""
    db = SessionLocal()
    try:
        wf = db.get(Workflow, workflow_id)
        if not wf:
            return None
        run_id = create_run(db, wf, trigger, trigger_data).id
    finally:
        db.close()
    return execute_run(run_id, stop_after=stop_after, dry_run=dry_run)


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


def execute_run(run_id: int, resume_from: str | None = None, retry: bool = False,
                stop_after: str | None = None, dry_run: bool = False) -> dict | None:
    """主循环。resume_from + retry=False：从该节点的后继继续（审批/延迟恢复）；retry=True：重跑该节点。
    stop_after：成功执行完该节点即结束（单节点试运行）。dry_run：沙盒模拟执行（试运行专用）。"""
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
        # 内置时间变量 {now.xxx}：每次（含恢复）执行都按当下重算，不随 context 落库复用旧值
        context["now"] = now_vars()
        nodes_by_id = {n["id"]: n for n in (wf.nodes_json or [])}
        edges = wf.edges_json or []
        user = db.get(User, wf.user_id)
        username = user.username if user else str(wf.user_id)

        # 手动执行/试运行「记录触发」的流程时没有触发记录：用该表最新一条模拟
        # （否则引用 {trigger.record.xxx} 的节点必挂——如 id 定位条件渲染成空串报「必须是整数」）
        t0 = wf.trigger_json or {}
        if t0.get("type") in ("record_created", "record_updated", "form") \
                and not (context.get("trigger") or {}).get("record"):
            latest = _latest_record(db, t0.get("table_id"))
            if latest:
                context["trigger"]["record"] = jsonable(latest)
                context["trigger"]["_simulated_by_engine"] = True   # 标记：执行详情可区分真实触发与模拟
                if t0.get("type") == "record_updated":
                    context["trigger"].setdefault("old_record", jsonable(latest))

        if resume_from:
            if retry:
                queue = [(resume_from, None)]
            else:
                prev = context["nodes"].get(resume_from) or {}
                queue = [(to, resume_from) for to in _successors(edges, resume_from, prev.get("branch"))]
        else:
            starts = [nid for nid in nodes_by_id if not any(e.get("to") == nid for e in edges)]
            queue = [(starts[0], None)] if starts else []   # 零节点的半成品：空跑直接成功

        steps = 0
        back_edges = _find_back_edges(nodes_by_id, edges)
        prev_stack = getattr(_tls, "stack", [])
        _tls.stack = [*prev_stack, wf.id]   # 子流程嵌套：压栈，退出时恢复（含 workflow_id）
        _tls.workflow_id = wf.id
        try:
            while queue and steps < MAX_STEPS:
                nid, via = queue.pop(0)   # via：由哪个节点连过来（区分 foreach 的新鲜入口与回边继续）
                node = nodes_by_id.get(nid)
                if not node:
                    continue
                steps += 1
                if node.get("disabled"):
                    if via is not None and (via, nid) in back_edges:
                        continue   # 停用的循环节点被回边再次触发：不再走兜底分支，防死循环
                    # 停用的节点：记一条 skipped 轨迹，输出置空，直接走后继
                    db.add(WorkflowNodeRun(
                        run_id=run.id, node_id=nid, node_type=node.get("type"),
                        status="skipped", input_json={}, output_json={},
                        started_at=datetime.now(), finished_at=datetime.now(), duration_ms=0,
                    ))
                    context["nodes"][nid] = {}
                    run.context_json = dict(context)
                    db.commit()
                    # 停用的分支类节点视为走兜底分支，保证流程能继续往下走
                    fallback_branch = getattr(REGISTRY.get(node.get("type")), "disabled_branch", None)
                    queue.extend((to, nid) for to in _successors(edges, nid, fallback_branch))
                    continue
                impl_cls = REGISTRY.get(node.get("type"))
                is_loop = getattr(impl_cls, "is_loop", False)
                if is_loop:
                    loops = context.setdefault("loops", {})
                    if via is None or (via, nid) not in back_edges:
                        loops[nid] = {"index": 0}   # 新鲜入口重置计数；回边进入则沿用
                missing: list = []   # 渲染期未命中的变量路径（路径不存在；值为 None 不算）
                rendered = render_config(context, node.get("config") or {}, missing)
                nr = WorkflowNodeRun(
                    run_id=run.id, node_id=nid, node_type=node.get("type"),
                    status="running", input_json=jsonable(rendered), started_at=datetime.now(),
                    warnings_json=_var_warnings(context, missing),
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
                        context=context, config=rendered, node_id=nid, node_run_id=nr.id,
                        dry_run=dry_run,
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
                if is_loop and result.status == "success":
                    # 推进循环计数：走「完成」分支清状态；走「每条」分支 index+1，回边进来时取下一条
                    if result.output.get("branch") == "done":
                        context.get("loops", {}).pop(nid, None)
                    else:
                        context.setdefault("loops", {}).setdefault(nid, {"index": 0})["index"] += 1
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
                        queue.extend((to, nid) for to in _successors(edges, nid, None))
                        continue
                    run.status = "failed"
                    run.error = result.error
                    run.finished_at = datetime.now()
                    db.commit()
                    _notify_run_failed(db, wf, run, f"「{node.get('name') or nid}」({nid})", result.error)
                    return _summary(run)

                queue.extend((to, nid) for to in _successors(edges, nid, result.output.get("branch")))

                if stop_after and nid == stop_after:
                    # 单节点试运行：执行完目标节点即成功结束
                    run.status = "success"
                    run.finished_at = datetime.now()
                    db.commit()
                    return _summary(run)

            run.status = "success" if steps < MAX_STEPS else "failed"
            if steps >= MAX_STEPS:
                run.error = f"超过最大执行步数（{MAX_STEPS}），疑似配置错误"
            run.finished_at = datetime.now()
            db.commit()
            if run.status == "failed":
                _notify_run_failed(db, wf, run, f"（超过最大执行步数 {MAX_STEPS}）", run.error)
            return _summary(run)
        finally:
            _tls.stack = prev_stack
            _tls.workflow_id = prev_stack[-1] if prev_stack else None
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
