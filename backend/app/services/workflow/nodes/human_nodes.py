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

    example_config = {"title": "待审批：{trigger.record.title}",
                      "detail_template": "申请人：{trigger.record.applicant}\n金额：{trigger.record.amount} 元"}
    config_schema = {
        "type": "object",
        "required": ["title"],
        "properties": {
            "title": {"type": "string", "format": "template", "title": "审批标题"},
            "detail_template": {"type": "string", "format": "template", "title": "审批详情模板"},
            "approver_user_ids": {"type": "array", "title": "审批人（好友/群组）",
                                  "description": "['u:用户id', 'g:群组id']，群组展开为全部成员；留空 = 工作流归属人"},
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
        if ctx.dry_run:
            # 试运行沙盒：不通知审批人、不暂停，模拟"通过"让流程走完
            return NodeResult(output={
                "approved": True, "comment": "（试运行：模拟通过，未通知审批人）",
                "approver_id": 0, "simulated": True,
                "approval": {"title": title, "detail": detail,
                             "approver_user_ids": self._approver_ids(ctx)},
            })
        approvers = self._approver_ids(ctx)
        # 免登审批链接（7 天签名 token）：点开即可通过/驳回，无需登录
        public_link = f"/approve/{create_approval_token(ctx.node_run_id)}"
        for uid in approvers:
            notify_user(ctx.db, uid, title, detail or "请前往处理审批。", link=public_link)
        return NodeResult(status="waiting", output={
            "approval": {"title": title, "detail": detail, "approver_user_ids": approvers},
        })

    @staticmethod
    def _approver_ids(ctx: NodeContext) -> list[int]:
        """审批人：与站内通知接收人同一格式——'u:用户id'/'g:群组id'（群组展开去重），
        兼容旧的纯数字 id 列表；空 = 归属人。"""
        from ....models import GroupMember
        raw = ctx.config.get("approver_user_ids") or []
        uids = {int(i) for i in raw if str(i).strip().isdigit()}   # 兼容纯 id
        uids |= {int(t[2:]) for t in raw if isinstance(t, str) and t.startswith("u:") and t[2:].isdigit()}
        gids = [int(t[2:]) for t in raw if isinstance(t, str) and t.startswith("g:") and t[2:].isdigit()]
        if gids:
            rows = ctx.db.query(GroupMember).filter(GroupMember.group_id.in_(gids)).all()
            uids |= {m.user_id for m in rows}
        return sorted(uids) or [ctx.user_id]
