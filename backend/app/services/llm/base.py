"""LLM Provider 抽象：所有供应商实现统一接口，网关按配置切换。"""
from abc import ABC, abstractmethod


class LLMError(Exception):
    pass


class LLMProvider(ABC):
    def __init__(self, base_url: str | None, api_key: str, model: str, vision_model: str | None = None):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.model = model
        self.vision_model = vision_model or model
        # 最近一次调用的 token 用量 {"prompt_tokens": n, "completion_tokens": n}，由实现类在响应后更新
        self.last_usage: dict = {}

    @abstractmethod
    def complete(self, prompt: str, system: str | None = None) -> str:
        """文本补全，返回模型原始文本输出。"""

    @abstractmethod
    def recognize(self, images: list[bytes], prompt: str, system: str | None = None) -> str:
        """多模态识别：传入 JPEG 字节列表 + 文本指令，返回模型原始文本输出。
        实现类使用 vision_model。不支持视觉的服务应抛 LLMError。"""
