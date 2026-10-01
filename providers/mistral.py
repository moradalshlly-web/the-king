"""
providers/mistral.py
====================

Mistral AI provider adapter for MOROAI.

Free tier: 1 req/sec, 500K TPM, 1B tokens/month.
No credit card required.

Endpoint: https://api.mistral.ai/v1/chat/completions
OpenAI-compatible API.
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


MISTRAL_MODELS = {
    "mistral-large-latest":  {"type": "reasoning",    "priority": 1},
    "mistral-medium-latest": {"type": "general",      "priority": 1},
    "mistral-small-latest":  {"type": "fast",         "priority": 1},
    "codestral-latest":      {"type": "code",         "priority": 1},
    "open-mistral-nemo":     {"type": "fast",         "priority": 2},
    "pixtral-large-latest":  {"type": "vision",       "priority": 1},
}


MISTRAL_DEFAULT_CONFIG = ProviderConfig(
    name="mistral",
    enabled=True,
    priority=3,
    models=list(MISTRAL_MODELS.keys()),
    capabilities=["chat", "code", "vision"],
    api_key_env="MISTRAL_API_KEY",
    base_url="https://api.mistral.ai/v1/chat/completions",
    is_free=True,
    paid_fallback_allowed=False,
    daily_limit=0,
    rpm_limit=60,
)


class MistralProvider(BaseProvider):
    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or MISTRAL_DEFAULT_CONFIG)

    @property
    def name(self) -> str:
        return "mistral"

    def is_available(self) -> bool:
        if not self.config.enabled:
            return False
        if self.is_in_cooldown():
            return False
        return bool(os.getenv(self.config.api_key_env, "").strip())

    def list_models(self) -> List[str]:
        return list(self.config.models)

    def list_models_by_type(self, model_type: str) -> List[str]:
        return [m for m, info in MISTRAL_MODELS.items() if info.get("type") == model_type]

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
            return self._error_response("Mistral unavailable (no API key).", code=503)

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
            "User-Agent": "MOROAI/0.1",
        }

        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        req = urllib.request.Request(
            self.config.base_url, data=data, headers=headers, method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
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
                f"HTTP {e.code}: {e.reason} | {err_body[:200]}",
                code=e.code,
            )
        except urllib.error.URLError as e:
            return self._error_response(f"Network: {e.reason}", code=503)
        except Exception as e:
            return self._error_response(f"{type(e).__name__}: {e}", code=500)


if __name__ == "__main__":
    p = MistralProvider()
    print(f"Name     : {p.name}")
    print(f"Available: {p.is_available()}")
    print(f"Total    : {len(p.list_models())} models")
    print()
    for t in ["reasoning", "code", "general", "fast", "vision"]:
        models = p.list_models_by_type(t)
        if models:
            print(f"{t:12}: {models}")
