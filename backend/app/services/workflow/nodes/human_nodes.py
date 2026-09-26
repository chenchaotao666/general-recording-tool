"""human 类节点：人工审批（差异化节点，规范 §7）。执行到此处暂停，审批后恢复。"""
from ...notify import notify_user
from ..registry import register
from .base import NodeContext, NodeResult, NodeType


@register
class ApprovalNode(NodeType):
    type = "approval"
    name = "人工审批"
    category = "human"
    description = "暂停流程并通知审批人，通过/驳回后流程继续"
    config_schema = {
        "type": "object",
        "required": ["title"],
        "properties": {
            "title": {"type": "string", "format": "template", "title": "审批标题"},
            "detail_template": {"type": "string", "format": "template", "title": "审批详情模板"},
            "approver_user_ids": {"type": "array", "title": "审批人（用户 id 列表，空 = 工作流归属人）"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {
            "approved": {"type": "boolean"},
            "comment": {"type": "string"},
            "approver_id": {"type": "integer"},
        },
    }

    def execute(self, ctx: NodeContext) -> NodeResult:
        from ....utils.auth import create_approval_token
        title = (ctx.config.get("title") or "").strip() or f"【{ctx.workflow.name}】待审批"
        detail = (ctx.config.get("detail_template") or "").strip()
        approvers = [int(i) for i in (ctx.config.get("approver_user_ids") or []) if str(i).strip().isdigit()]
        if not approvers:
            approvers = [ctx.user_id]
        # 免登审批链接（7 天签名 token）：点开即可通过/驳回，无需登录
        public_link = f"/approve/{create_approval_token(ctx.node_run_id)}"
        for uid in approvers:
            notify_user(ctx.db, uid, title, detail or "请前往处理审批。", link=public_link)
        return NodeResult(status="waiting", output={
            "approval": {"title": title, "detail": detail, "approver_user_ids": approvers},
        })
