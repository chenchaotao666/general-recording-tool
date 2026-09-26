"""节点类型基类：NodeResult / NodeContext / NodeType 协议。规范 §4.1。"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session


class WorkflowNodeError(Exception):
    """节点执行失败（业务性错误，如配置缺失、外部服务报错）。引擎据此标记节点 failed。"""


@dataclass
class NodeResult:
    status: str = "success"          # success / failed / waiting
    output: dict = field(default_factory=dict)
    error: str | None = None
    tokens_used: int = 0             # LLM 类节点必须上报
    resume_after: datetime | None = None   # delay 节点：到期自动恢复（引擎投 retry 语义的 resume job）


@dataclass
class NodeContext:
    """注入给节点的执行环境。节点不允许直接 import 引擎内部。"""
    db: Session
    workflow: Any                    # Workflow 记录
    run_id: int
    user_id: int                     # 工作流归属用户（节点以其身份执行）
    username: str
    context: dict                    # 只读视图：trigger + 上游节点输出（+ loops 循环状态）
    config: dict                     # 已渲染模板后的本节点配置
    node_id: str = ""                # 本节点 id（foreach 等需定位自身循环状态）
    node_run_id: int = 0             # 本次执行的 NodeRun id（审批节点生成免登链接用）


class NodeType:
    """节点类型基类。子类定义类属性 + execute，并用 @register 注册。"""
    type: str = ""
    name: str = ""
    category: str = ""               # trigger / data / ai / logic / action / human
    description: str = ""
    config_schema: dict = {}
    output_schema: dict = {}
    disabled_branch: str | None = None   # 节点被停用时走的兜底分支（分支类节点）
    is_loop: bool = False                # 逐条处理节点：引擎据此维护循环计数

    def execute(self, ctx: NodeContext) -> NodeResult:
        raise NotImplementedError
