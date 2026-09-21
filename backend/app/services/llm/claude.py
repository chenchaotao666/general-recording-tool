"""Claude（Anthropic Messages API）。"""
import base64

import httpx

from .base import LLMError, LLMProvider

DEFAULT_BASE_URL = "https://api.anthropic.com"


class ClaudeProvider(LLMProvider):
    def _post(self, body: dict) -> str:
        url = f"{self.base_url or DEFAULT_BASE_URL}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(url, json=body, headers=headers)
                if resp.status_code != 200:
                    raise LLMError(f"模型服务返回 {resp.status_code}：{resp.text[:300]}")
                data = resp.json()
                return "".join(b.get("text", "") for b in data.get("content", []))
        except httpx.HTTPError as e:
            raise LLMError(f"模型服务请求失败：{e}")

    def complete(self, prompt: str, system: str | None = None) -> str:
        body = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        return self._post(body)

    def recognize(self, images: list[bytes], prompt: str, system: str | None = None) -> str:
        content = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(img).decode()},
            }
            for img in images
        ]
        content.append({"type": "text", "text": prompt})
        body = {
            "model": self.vision_model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": content}],
        }
        if system:
            body["system"] = system
        return self._post(body)
