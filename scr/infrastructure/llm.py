from __future__ import annotations

import httpx

from scr.config import settings


class LLMGateway:
    def __init__(self) -> None:
        self._client = httpx.Client(timeout=settings.llm_timeout_seconds)

    @property
    def available(self) -> bool:
        return bool(settings.llm_api_key)

    def complete(self, system: str, prompt: str, temperature: float = 0.2) -> str:
        if not self.available:
            raise RuntimeError("尚未配置模型 API Key")
        if settings.llm_provider == "anthropic":
            response = self._client.post("https://api.anthropic.com/v1/messages", headers={
                "x-api-key": settings.llm_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json",
            }, json={"model": settings.llm_model, "max_tokens": 1800, "temperature": temperature,
                    "system": system, "messages": [{"role": "user", "content": prompt}]})
            response.raise_for_status()
            return "".join(part.get("text", "") for part in response.json().get("content", []))
        base = settings.llm_base_url.rstrip("/")
        response = self._client.post(f"{base}/chat/completions", headers={
            "Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json",
        }, json={"model": settings.llm_model, "temperature": temperature, "messages": [
            {"role": "system", "content": system}, {"role": "user", "content": prompt},
        ]})
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
