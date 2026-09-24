"""ai 类节点：LLM 处理。token 用量经 provider.last_usage 上报（规范 §6.4）。"""
from ....models import LLMProvider as LLMProviderRow
from ...llm.base import LLMError
from ...llm.gateway import build_provider, extract_json, get_default_provider
from ..registry import register
from .base import NodeContext, NodeResult, NodeType, WorkflowNodeError


@register
class LlmTransformNode(NodeType):
    type = "llm_transform"
    name = "LLM 处理"
    category = "ai"
    description = "调用大模型处理文本：总结、分类、提取、生成，可输出结构化 JSON"
    config_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string", "format": "template", "title": "提示词"},
            "system": {"type": "string", "format": "textarea", "title": "系统提示词"},
            "provider_id": {"type": "integer", "format": "provider-ref", "title": "模型供应商（缺省用默认）"},
            "output_format": {"type": "string", "enum": ["text", "json"], "enumNames": ["文本", "JSON"], "default": "text", "title": "输出格式"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "data": {"type": "object", "description": "output_format=json 时的解析结果"},
            "usage": {"type": "object"},
        },
    }

    def execute(self, ctx: NodeContext) -> NodeResult:
        prompt = (ctx.config.get("prompt") or "").strip()
        if not prompt:
            raise WorkflowNodeError("未配置提示词")
        provider_id = ctx.config.get("provider_id")
        if provider_id:
            row = ctx.db.get(LLMProviderRow, provider_id)
            if not row:
                raise WorkflowNodeError(f"模型供应商不存在：{provider_id}")
            provider = build_provider(row)
        else:
            provider = get_default_provider(ctx.db)
        try:
            text = provider.complete(prompt, ctx.config.get("system") or None)
        except LLMError as e:
            raise WorkflowNodeError(str(e))
        usage = getattr(provider, "last_usage", None) or {}
        tokens = int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)

        output = {"text": text, "usage": usage}
        if ctx.config.get("output_format") == "json":
            try:
                output["data"] = extract_json(text)
            except Exception as e:
                raise WorkflowNodeError(f"LLM 输出不是合法 JSON：{e}")
        return NodeResult(output=output, tokens_used=tokens)
