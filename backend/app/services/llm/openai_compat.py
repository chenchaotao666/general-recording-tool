"""OpenAI 兼容接口：覆盖 OpenAI / DeepSeek / 通义千问(兼容模式) / 智谱 等。"""
import base64

import httpx

from .base import LLMError, LLMProvider

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAICompatProvider(LLMProvider):
    def _post(self, body: dict) -> str:
        url = f"{self.base_url or DEFAULT_BASE_URL}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(url, json=body, headers=headers)
                if resp.status_code == 400 and "response_format" in body:
                    # 部分供应商/视觉模型不支持 response_format，去掉重试一次
                    body.pop("response_format")
                    resp = client.post(url, json=body, headers=headers)
                if resp.status_code != 200:
                    raise LLMError(f"模型服务返回 {resp.status_code}：{resp.text[:300]}")
                return resp.json()["choices"][0]["message"]["content"]
        except httpx.HTTPError as e:
            raise LLMError(f"模型服务请求失败：{e}")

    def complete(self, prompt: str, system: str | None = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._post({
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        })

    def recognize(self, images: list[bytes], prompt: str, system: str | None = None) -> str:
        content = [{"type": "text", "text": prompt}]
        for img in images:
            b64 = base64.b64encode(img).decode()
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": content})
        return self._post({
            "model": self.vision_model,
            "messages": messages,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        })
