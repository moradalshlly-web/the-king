"""
providers/openrouter.py
=======================

OpenRouter provider adapter for MOROAI.

OpenRouter is an aggregator: one API key, many free models.
Free tier: rate-limited but no credit card required.

Endpoint:
    POST https://openrouter.ai/api/v1/chat/completions
    Header: Authorization: Bearer KEY
    Body: OpenAI-compatible chat format

Inspiration (no code copied):
    - OpenRouter docs: OpenAI-compatible API
    - EasyAgent (MIT): provider adapter pattern
"""

import json
import os
import urllib.request
import urllib.error
from typing import Optional, List

try:
    from .base import BaseProvider, ProviderConfig, AIResponse
except ImportError:
    from base import BaseProvider, ProviderConfig, AIResponse


OPENROUTER_DEFAULT_CONFIG = ProviderConfig(
    name="openrouter",
    enabled=True,
    priority=3,
    models=[
        "cohere/north-mini-code:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "qwen/qwen3.8-27b:free",
    ],
    capabilities=["chat", "code"],
    api_key_env="OPENROUTER_API_KEY",
    base_url="https://openrouter.ai/api/v1/chat/completions",
    is_free=True,
    paid_fallback_allowed=False,
    daily_limit=50,
    rpm_limit=20,
)


class OpenRouterProvider(BaseProvider):
    """Concrete implementation of BaseProvider for OpenRouter."""

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or OPENROUTER_DEFAULT_CONFIG)

    @property
    def name(self) -> str:
        return "openrouter"

    def is_available(self) -> bool:
        if not self.config.enabled:
            return False
        if self.is_in_cooldown():
            return False
        return bool(os.getenv(self.config.api_key_env, "").strip())

    def list_models(self) -> List[str]:
        return list(self.config.models)

    def chat(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AIResponse:
        start = self._start_timer()

        if not self.is_available():
            return self._error_response(
                f"Provider '{self.name}' unavailable.", code=503,
            )

        chosen_model = model or self.config.models[0]

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": chosen_model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        api_key = os.getenv(self.config.api_key_env, "").strip()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "HTTP-Referer": "https://moroai.local",
            "X-Title": "MOROAI",
            "User-Agent": "MOROAI/0.1",
        }

        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        req = urllib.request.Request(
            self.config.base_url, data=data, headers=headers, method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))

            text = ""
            choices = body.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                text = msg.get("content", "") or ""

            tokens = None
            usage = body.get("usage", {})
            if usage:
                tokens = usage.get("total_tokens")

            return AIResponse(
                text=text,
                model=chosen_model,
                provider=self.name,
                success=True,
                tokens_used=tokens,
                latency_ms=self._elapsed_ms(start),
            )

        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                pass
            return self._error_response(
                f"HTTP {e.code}: {e.reason} | {err_body[:300]}",
                code=e.code,
            )
        except urllib.error.URLError as e:
            return self._error_response(f"Network: {e.reason}", code=503)
        except Exception as e:
            return self._error_response(
                f"{type(e).__name__}: {e}", code=500,
            )


if __name__ == "__main__":
    p = OpenRouterProvider()
    print(f"Provider       : {p.name}")
    print(f"Is available?  : {p.is_available()}")
    print(f"Models         : {p.list_models()}")
    print(f"Free?          : {p.is_free()}")
