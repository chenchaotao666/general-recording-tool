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

    example_config = {"channel": "notify", "title": "提醒",
                            "template": "有一条新记录，请处理：{trigger.record}"}
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
        # 整体模板引用数字输出（如 {nodes.x.count}）时拿到的是 int，先归一成字符串
        content = str(ctx.config.get("template") or "").strip()
        if not content:
            raise WorkflowNodeError("未配置内容模板")
        title = str(ctx.config.get("title") or "").strip()
        head = f"【{ctx.workflow.name}】{title}" if title else f"【{ctx.workflow.name}】"

        if ctx.dry_run:
            # 试运行沙盒：算出发送对象与内容预览，不真实触达
            return NodeResult(output=self._simulated(ctx, channel, head, content))

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

    def _simulated(self, ctx: NodeContext, channel: str, head: str, content: str) -> dict:
        """试运行沙盒输出：各通道只算接收人/地址，不真实发送。"""
        base = {"simulated": True, "channel": channel, "preview": f"{head}\n{content}"}
        if channel == "notify":
            user_ids = self._notify_user_ids(ctx)
            return {**base, "sent": len(user_ids), "recipients": [str(u) for u in user_ids]}
        if channel in ("email", "sms"):
            recipients = _split_recipients(ctx.config.get("recipients"))
            return {**base, "sent": len(recipients), "recipients": recipients}
        url = (ctx.config.get("webhook_url") or "").strip()
        return {**base, "sent": 1 if url else 0, "recipients": [url] if url else []}


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
            "workflow_id": {"type": "integer", "format": "workflow-ref", "title": "子流程",
                            "description": "只有触发方式为「被动调用」的工作流才能作为子流程（被调用的流程不应有自己的自动触发器）；"
                                           "下拉列表里只列出可选的子流程"},
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
        if ctx.dry_run:
            # 试运行沙盒：不真实调用子流程
            return NodeResult(output={"status": "simulated", "run_id": 0, "simulated": True})
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

    example_config = {"method": "GET", "url": "https://api.example.com/data", "timeout_seconds": 30}
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
        if ctx.dry_run:
            # 试运行沙盒：不真实发起 HTTP 请求，只回显将要发送的内容
            return NodeResult(output={"status": 0, "body": None, "simulated": True,
                                      "request": {"method": method, "url": url,
                                                  "headers": ctx.config.get("headers") or {},
                                                  "body": ctx.config.get("body") if method != "GET" else None}})
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


@register
class PushReportNode(NodeType):
    """推送报表：生成并推送已配置好的报表（走该报表的推送渠道），作为流程的结果归档。"""
    type = "push_report"
    name = "推送报表"
    category = "action"
    description = "生成并推送一张已配置好的报表（邮件/群机器人）；推送渠道、阈值告警在报表的「设置」里配置"

    example_config = {"report_id": 1}
    config_schema = {
        "type": "object",
        "required": ["report_id"],
        "properties": {
            "report_id": {"type": "integer", "format": "report-ref", "title": "报表",
                          "description": "要生成并推送的报表（推送渠道在报表设置里配置）"},
            "range_mode": {"type": "string", "title": "口径覆盖（可选）",
                           "enum": ["today", "yesterday", "past_7d", "past_30d", "this_week", "last_week",
                                    "this_month", "last_month", "this_quarter", "this_year", "custom"],
                           "enumNames": ["今天", "昨天", "近 7 天", "近 30 天", "本周", "上周",
                                         "本月", "上月", "本季度", "今年", "自定义区间"],
                           "description": "留空 = 按报表自身口径生成；选择后仅本次按该口径"},
            "range_start": {"type": "string", "title": "起始日期（自定义区间）", "description": "YYYY-MM-DD"},
            "range_end": {"type": "string", "title": "结束日期（自定义区间）", "description": "YYYY-MM-DD"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {"sent": {"type": "integer"}, "skipped": {"type": "boolean"},
                       "range_label": {"type": "string"}},
    }

    def _load_tpl(self, ctx: NodeContext):
        from ....models import ReportTemplate, User
        from ....utils.rbac import tenant_role
        rid = ctx.config.get("report_id")
        if not isinstance(rid, int):
            raise WorkflowNodeError("未选择报表")
        tpl = ctx.db.get(ReportTemplate, rid)
        u = ctx.db.get(User, ctx.user_id)
        if not tpl or (tpl.user_id != ctx.user_id
                       and (not u or tenant_role(ctx.db, u, tpl.tenant_id) != "admin")):
            raise WorkflowNodeError("报表不存在或无权限")
        return tpl

    def _range_override(self, ctx: NodeContext) -> dict | None:
        mode = (ctx.config.get("range_mode") or "").strip()
        if not mode:
            return None
        if mode == "custom":
            start = (ctx.config.get("range_start") or "").strip()
            end = (ctx.config.get("range_end") or "").strip()
            if not start or not end:
                raise WorkflowNodeError("自定义区间需要起止日期")
            return {"mode": "custom", "start": start, "end": end}
        return {"mode": mode}

    def execute(self, ctx: NodeContext) -> NodeResult:
        from ....models import User
        from ...report_engine import _guard_met, push_template, run_template

        tpl = self._load_tpl(ctx)
        ov = self._range_override(ctx)
        if ctx.dry_run:
            # 试运行沙盒：真实生成一次（只读），算出将发送的渠道与阈值告警结果，不真实推送
            result = run_template(ctx.db, tpl, range_override=ov,
                                  viewer=ctx.db.get(User, ctx.user_id))
            push = tpl.push_json or {}
            n_recipients = len([s for s in str(push.get("recipients") or "").split(",") if s.strip()])
            n_webhooks = len([w for w in (push.get("webhooks") or []) if (w.get("url") or "").strip()])
            skipped = not _guard_met(result, push.get("guard") or {})
            return NodeResult(output={"simulated": True, "sent": 0, "skipped": skipped,
                                      "channels": n_recipients + n_webhooks,
                                      "range_label": result["range"]["label"]})
        result = push_template(tpl.id, trigger="manual", range_override=ov, viewer_id=ctx.user_id)
        if result is None:
            raise WorkflowNodeError("报表不存在")
        if result.get("error"):
            raise WorkflowNodeError(f"报表推送失败：{result['error']}")
        return NodeResult(output={"sent": result.get("sent") or 0, "skipped": bool(result.get("skipped")),
                                  "range_label": result.get("range_label")})
