"""MCP（Model Context Protocol）服务：把用户启用的工作流暴露为 MCP tools。

无依赖实现 Streamable HTTP 的最小子集：initialize / ping / tools/list / tools/call，
单 POST 端点 + JSON 响应（不支持 SSE 流与会话状态，无状态足够）。
鉴权：URL 路径中的 per-user token（见 routers/mcp.py）。
"""
import json
import re

from sqlalchemy.orm import Session

from ...models import User, Workflow
from . import engine

PROTOCOL_VERSION = "2024-11-05"


def _enabled_workflows(db: Session, user: User) -> list[Workflow]:
    return (
        db.query(Workflow)
        .filter(Workflow.user_id == user.id, Workflow.enabled.is_(True))
        .order_by(Workflow.id)
        .all()
    )


def _tool_defs(workflows: list[Workflow]) -> list[dict]:
    tools = [{
        "name": "list_workflows",
        "description": "列出账号中所有已启用的工作流（id、名称、说明、触发方式）",
        "inputSchema": {"type": "object", "properties": {}},
    }]
    for wf in workflows:
        t = (wf.trigger_json or {}).get("type") or "manual"
        tools.append({
            "name": f"run_workflow_{wf.id}",
            "description": f"执行工作流「{wf.name}」（触发方式：{t}）。{wf.description or ''}".strip(),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "params": {
                        "type": "object",
                        "description": "手动触发参数（流程模板中可用 {trigger.params.xxx} 引用），可为空对象",
                    },
                },
            },
        })
    return tools


def _ok(rid, result) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _text(text: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _call_tool(db: Session, user: User, name: str, args: dict) -> dict:
    if name == "list_workflows":
        wfs = _enabled_workflows(db, user)
        data = [
            {"id": w.id, "name": w.name, "description": w.description,
             "trigger": (w.trigger_json or {}).get("type") or "manual"}
            for w in wfs
        ]
        return _text(json.dumps(data, ensure_ascii=False))

    m = re.fullmatch(r"run_workflow_(\d+)", name or "")
    if not m:
        return _text(f"未知工具：{name}", is_error=True)
    wf = db.get(Workflow, int(m.group(1)))
    if not wf or wf.user_id != user.id or not wf.enabled:
        return _text("工作流不存在、未启用或不属于当前账号", is_error=True)
    params = args.get("params") if isinstance(args.get("params"), dict) else {}
    result = engine.run_now(wf.id, trigger="manual", trigger_data={"params": params})
    if not result:
        return _text("执行失败", is_error=True)
    return _text(json.dumps(result, ensure_ascii=False),
                 is_error=result.get("status") not in ("success", "waiting"))


def handle_message(db: Session, user: User, msg: dict) -> dict | None:
    """处理一条 JSON-RPC 消息；通知类返回 None（调用方回 202）。"""
    if not isinstance(msg, dict):
        return _err(None, -32600, "Invalid Request")
    method = msg.get("method")
    rid = msg.get("id")
    if not isinstance(method, str):
        return _err(rid, -32600, "Invalid Request")
    if method.startswith("notifications/"):
        return None
    if method == "initialize":
        return _ok(rid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "grt-workflows", "version": "1.0.0"},
        })
    if method == "ping":
        return _ok(rid, {})
    if method == "tools/list":
        return _ok(rid, {"tools": _tool_defs(_enabled_workflows(db, user))})
    if method == "tools/call":
        params = msg.get("params") or {}
        return _ok(rid, _call_tool(db, user, params.get("name"), params.get("arguments") or {}))
    return _err(rid, -32601, f"Method not found: {method}")
