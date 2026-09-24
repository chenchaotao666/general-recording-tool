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
            "channel": {"type": "string", "enum": ["notify", "email", "sms", "webhook"],
                        "enumNames": ["站内通知", "邮件", "短信", "Webhook"], "title": "通道"},
            "title": {"type": "string", "format": "template", "title": "标题（可选）"},
            "template": {"type": "string", "format": "template", "title": "内容模板"},
            "recipients": {"type": "string", "format": "template", "title": "接收人（逗号分隔，邮件/短信必填）"},
            "webhook_url": {"type": "string", "title": "Webhook 地址（webhook 通道必填）"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {"sent": {"type": "integer"}, "recipients": {"type": "array"}},
    }

    def execute(self, ctx: NodeContext) -> NodeResult:
        channel = ctx.config.get("channel")
        content = (ctx.config.get("template") or "").strip()
        if not content:
            raise WorkflowNodeError("未配置内容模板")
        title = (ctx.config.get("title") or "").strip()
        head = f"【{ctx.workflow.name}】{title}" if title else f"【{ctx.workflow.name}】"

        if channel == "notify":
            notify_user(ctx.db, ctx.user_id, head, content, link=f"/workflows/{ctx.workflow.id}")
            return NodeResult(output={"sent": 1, "recipients": [ctx.username]})

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

        raise WorkflowNodeError(f"未知通知通道：{channel}")


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
