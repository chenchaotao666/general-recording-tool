"""节点包：import 即注册全部内置节点类型。"""
from ..registry import register  # noqa: F401  （供节点模块使用）

from . import action_nodes, ai_nodes, data_nodes, human_nodes, logic_nodes  # noqa: F401,E402
