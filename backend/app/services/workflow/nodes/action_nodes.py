"""action 类节点：触达（通知/邮件/短信/webhook，复用 actions.py 通道）+ HTTP 请求。"""
import ipaddress
from urllib.parse import urlparse

import httpx

from ... import actions
from ...notify import notify_user
from ..registry import register
from .base import NodeContext, NodeResult, NodeType, WorkflowNodeError


def _split_recipients(raw: str) -> list[str]:
    return [s.strip() for s in str(raw or "").replace("，", ",").split(",") if s.strip()]


@register
class SendMessageNode(NodeType):
    type = "send_message"
    name = "发送通知"
    category = "action"
    description = "通过站内通知 / 邮件 / 短信 / Webhook 发送消息"
    config_schema = {
        "type": "object",
        "required": ["channel", "template"],
        "properties": {
            "title": {"type": "string", "format": "template", "title": "标题（可选）"},
            "template": {"type": "string", "format": "template", "title": "内容模板"},
            "channel": {"type": "string", "enum": ["notify", "email", "sms", "webhook", "wecom", "dingtalk"],
                        "enumNames": ["站内通知", "邮件", "短信", "Webhook", "企业微信机器人", "钉钉机器人"],
                        "title": "通道"},
            "notify_targets": {"type": "array", "title": "接收人（好友/群组）",
                               "description": "仅站内通知：['u:用户id', 'g:群组id']，留空 = 发给工作流归属人"},
            "recipients": {"type": "string", "format": "template", "title": "接收人（逗号分隔，邮件/短信必填）"},
            "webhook_url": {"type": "string", "title": "Webhook 地址（webhook/企业微信/钉钉通道必填）"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {"sent": {"type": "integer"}, "recipients": {"type": "array"}},
    }

    def _notify_user_ids(self, ctx: NodeContext) -> list[int]:
        """站内通知接收人：notify_targets 里的好友 id + 群组成员 id 展开去重；空 = 归属人（兼容旧配置）。"""
        from ....models import GroupMember
        raw = ctx.config.get("notify_targets") or []
        uids = {int(t[2:]) for t in raw if isinstance(t, str) and t.startswith("u:") and t[2:].isdigit()}
        gids = [int(t[2:]) for t in raw if isinstance(t, str) and t.startswith("g:") and t[2:].isdigit()]
        if gids:
            rows = ctx.db.query(GroupMember).filter(GroupMember.group_id.in_(gids)).all()
            uids |= {m.user_id for m in rows}
        return sorted(uids) or [ctx.user_id]

    def execute(self, ctx: NodeContext) -> NodeResult:
        channel = ctx.config.get("channel")
        content = (ctx.config.get("template") or "").strip()
        if not content:
            raise WorkflowNodeError("未配置内容模板")
        title = (ctx.config.get("title") or "").strip()
        head = f"【{ctx.workflow.name}】{title}" if title else f"【{ctx.workflow.name}】"

        if channel == "notify":
            from ....models import User
            user_ids = self._notify_user_ids(ctx)
            for uid in user_ids:
                notify_user(ctx.db, uid, head, content, link=f"/workflows/runs/{ctx.run_id}")
            names = [u.username for u in ctx.db.query(User).filter(User.id.in_(user_ids)).all()]
            return NodeResult(output={"sent": len(user_ids), "recipients": names})

        if channel == "email":
            recipients = _split_recipients(ctx.config.get("recipients"))
            if not recipients:
                raise WorkflowNodeError("没有可用的收件人")
            actions.send_smtp(actions.get_setting(ctx.db, "smtp"), recipients, f"{head}提醒", content)
            return NodeResult(output={"sent": len(recipients), "recipients": recipients})

        if channel == "sms":
            tpl = actions.get_setting(ctx.db, "sms_gateway").get("url_template")
            if not tpl:
                raise WorkflowNodeError("未配置短信网关，请到「设置-通知渠道」中配置 URL 模板")
            phones = _split_recipients(ctx.config.get("recipients"))
            if not phones:
                raise WorkflowNodeError("没有可用的手机号")
            from urllib.parse import quote
            for phone in phones:
                url = tpl.replace("{phone}", quote(phone)).replace("{content}", quote(content))
                try:
                    resp = httpx.get(url, timeout=15)
                    if resp.status_code >= 400:
                        raise WorkflowNodeError(f"短信网关返回 {resp.status_code}")
                except httpx.HTTPError as e:
                    raise WorkflowNodeError(f"短信网关请求失败：{e}")
            return NodeResult(output={"sent": len(phones), "recipients": phones})

        if channel == "webhook":
            url = (ctx.config.get("webhook_url") or "").strip() or actions.get_setting(ctx.db, "webhook").get("url")
            if not url:
                raise WorkflowNodeError("未配置 Webhook 地址")
            try:
                resp = httpx.post(url, json={"workflow": ctx.workflow.name, "run_id": ctx.run_id,
                                             "title": head, "content": content}, timeout=15)
                if resp.status_code >= 400:
                    raise WorkflowNodeError(f"Webhook 返回 {resp.status_code}")
            except httpx.HTTPError as e:
                raise WorkflowNodeError(f"Webhook 请求失败：{e}")
            return NodeResult(output={"sent": 1, "recipients": [url]})

        if channel in ("wecom", "dingtalk"):
            # 企业微信/钉钉群机器人：同一套 text 消息格式，errcode=0 为成功
            url = (ctx.config.get("webhook_url") or "").strip()
            if not url:
                raise WorkflowNodeError("未配置机器人 Webhook 地址（群聊 → 添加机器人 → 复制 Webhook）")
            text = f"{head}\n{content}"
            try:
                resp = httpx.post(url, json={"msgtype": "text", "text": {"content": text}}, timeout=15)
                body = resp.json()
            except httpx.HTTPError as e:
                raise WorkflowNodeError(f"机器人推送请求失败：{e}")
            except ValueError:
                raise WorkflowNodeError(f"机器人返回异常（HTTP {resp.status_code}）")
            if resp.status_code >= 400 or body.get("errcode"):
                raise WorkflowNodeError(f"机器人推送失败：{body.get('errmsg') or body}")
            return NodeResult(output={"sent": 1, "recipients": [url]})

        raise WorkflowNodeError(f"未知通知通道：{channel}")


@register
class SubWorkflowNode(NodeType):
    type = "sub_workflow"
    name = "子流程调用"
    category = "action"
    description = "同步调用另一个「被动调用」的工作流并等待其完成（传参在子流程里用 {trigger.params.键} 引用）"
    config_schema = {
        "type": "object",
        "required": ["workflow_id"],
        "properties": {
            "workflow_id": {"type": "integer", "format": "workflow-ref", "title": "子流程"},
            "params": {"type": "object", "title": "传参（可选）",
                       "description": "JSON 对象，子流程里用 {trigger.params.键} 引用"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {"status": {"type": "string"}, "run_id": {"type": "integer"},
                       "tokens_used": {"type": "integer"}},
    }

    def execute(self, ctx: NodeContext) -> NodeResult:
        from .. import engine   # 延迟 import：engine 依赖 nodes 注册，避免循环
        from ....models import Workflow
        from ..template import jsonable

        wf_id = ctx.config.get("workflow_id")
        if not isinstance(wf_id, int):
            raise WorkflowNodeError("未选择子流程")
        stack = engine.call_stack()
        if wf_id in stack:
            raise WorkflowNodeError("不允许循环调用（子流程不能直接或间接调用自己）")
        if len(stack) >= engine.MAX_CALL_DEPTH:
            raise WorkflowNodeError(f"子流程嵌套最多 {engine.MAX_CALL_DEPTH} 层")
        sub = ctx.db.get(Workflow, wf_id)
        if not sub or sub.user_id != ctx.user_id:
            raise WorkflowNodeError("子流程不存在或无权限（只能调用自己的工作流）")
        if (sub.trigger_json or {}).get("type", "manual") != "manual":
            raise WorkflowNodeError("子流程的触发方式必须是「被动调用」（被调用的流程不应有自己的自动触发器）")
        params = ctx.config.get("params") or {}
        if not isinstance(params, dict):
            raise WorkflowNodeError("传参必须是 JSON 对象")
        result = engine.run_now(wf_id, trigger="sub", trigger_data={"params": jsonable(params)})
        if not result:
            raise WorkflowNodeError("子流程执行失败")
        if result.get("status") == "failed":
            raise WorkflowNodeError(f"子流程执行失败：{result.get('error') or ''}")
        # waiting（子流程里有审批/延迟）：不阻塞父流程，子流程恢复后自行走完
        return NodeResult(
            output={"status": result.get("status"), "run_id": result.get("id")},
            tokens_used=result.get("tokens_used") or 0,
        )


@register
class HttpRequestNode(NodeType):
    type = "http_request"
    name = "HTTP 请求"
    category = "action"
    description = "调用任意 HTTP API（通用集成逃生舱）"
    config_schema = {
        "type": "object",
        "required": ["url"],
        "properties": {
            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"], "default": "POST", "title": "方法"},
            "url": {"type": "string", "format": "template", "title": "URL"},
            "headers": {"type": "object", "title": "请求头"},
            "body": {"type": "object", "title": "请求体（JSON）"},
            "timeout_seconds": {"type": "integer", "default": 30, "minimum": 1, "maximum": 120, "title": "超时（秒）"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {"status": {"type": "integer"}, "body": {}},
    }

    def _check_url_allowed(self, ctx: NodeContext, url: str) -> None:
        """SSRF 防护：默认禁止 localhost 与内网网段字面 IP；域名白名单见 设置 workflow_http.allow_domains。"""
        host = (urlparse(url).hostname or "").lower()
        if not host:
            raise WorkflowNodeError("URL 无效")
        allow = actions.get_setting(ctx.db, "workflow_http").get("allow_domains") or []
        if host in allow:
            return
        if host == "localhost" or host.endswith(".localhost"):
            raise WorkflowNodeError("禁止访问本机地址（可在 workflow_http.allow_domains 中放行）")
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise WorkflowNodeError("禁止访问内网地址（可在 workflow_http.allow_domains 中放行）")
        except ValueError:
            pass  # 普通域名：v1 不做 DNS 解析后校验

    def execute(self, ctx: NodeContext) -> NodeResult:
        url = (ctx.config.get("url") or "").strip()
        if not url:
            raise WorkflowNodeError("未配置 URL")
        self._check_url_allowed(ctx, url)
        method = (ctx.config.get("method") or "POST").upper()
        timeout = min(max(int(ctx.config.get("timeout_seconds") or 30), 1), 120)
        try:
            resp = httpx.request(
                method, url,
                headers=ctx.config.get("headers") or None,
                json=ctx.config.get("body") if method != "GET" else None,
                timeout=timeout,
            )
        except httpx.HTTPError as e:
            raise WorkflowNodeError(f"HTTP 请求失败：{e}")
        try:
            body = resp.json()
        except ValueError:
            body = resp.text[:5000]
        return NodeResult(output={"status": resp.status_code, "body": body})
