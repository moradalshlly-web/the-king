"""
providers/ollama_cloud.py
=========================

Ollama Cloud provider adapter for MOROAI.

Free tier: $0, no credit card.
Verified working models (October 2026).
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


# ============================================================
# Verified working models (October 2026)
# ============================================================

OLLAMA_CLOUD_MODELS = {
    # Code + general (fast & powerful)
    "gpt-oss:120b-cloud":       {"type": "code",      "priority": 1, "speed": "fast"},
    "gpt-oss:20b-cloud":        {"type": "fast",      "priority": 1, "speed": "fast"},

    # Multilingual
    "gemma4:31b-cloud":         {"type": "multilingual", "priority": 1, "speed": "medium"},

    # Reasoning
    "nemotron-3-super:cloud":   {"type": "reasoning", "priority": 1, "speed": "slow"},
    "nemotron-3-nano:30b-cloud":{"type": "fast",      "priority": 2, "speed": "fast"},
}


OLLAMA_CLOUD_DEFAULT_CONFIG = ProviderConfig(
    name="ollama_cloud",
    enabled=True,
    priority=2,
    models=list(OLLAMA_CLOUD_MODELS.keys()),
    capabilities=["chat", "code"],
    api_key_env="OLLAMA_API_KEY",
    base_url="https://ollama.com/api/chat",
    is_free=True,
    paid_fallback_allowed=False,
    daily_limit=0,
    rpm_limit=0,
)


class OllamaCloudProvider(BaseProvider):
    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or OLLAMA_CLOUD_DEFAULT_CONFIG)

    @property
    def name(self) -> str:
        return "ollama_cloud"

    def is_available(self) -> bool:
        if not self.config.enabled:
            return False
        if self.is_in_cooldown():
            return False
        return bool(os.getenv(self.config.api_key_env, "").strip())

    def list_models(self) -> List[str]:
        return list(self.config.models)

    def list_models_by_type(self, model_type: str) -> List[str]:
        return [m for m, info in OLLAMA_CLOUD_MODELS.items()
                if info.get("type") == model_type]

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
            return self._error_response("Ollama Cloud unavailable (no API key).", code=503)

        chosen_model = model or self.config.models[0]

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": chosen_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        api_key = os.getenv(self.config.api_key_env, "").strip()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "MOROAI/0.1",
        }

        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        req = urllib.request.Request(
            self.config.base_url, data=data, headers=headers, method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = json.loads(resp.read().decode("utf-8"))

            text = ""
            msg = body.get("message", {})
            if msg:
                text = msg.get("content", "") or ""

            return AIResponse(
                text=text,
                model=chosen_model,
                provider=self.name,
                success=True,
                latency_ms=self._elapsed_ms(start),
            )

        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                pass
            # Mark retired/paid models so router can skip them
            code = e.code
            return self._error_response(
                f"HTTP {code}: {e.reason} | {err_body[:200]}",
                code=code,
            )
        except urllib.error.URLError as e:
            return self._error_response(f"Network: {e.reason}", code=503)
        except Exception as e:
            return self._error_response(f"{type(e).__name__}: {e}", code=500)


if __name__ == "__main__":
    p = OllamaCloudProvider()
    print(f"Name     : {p.name}")
    print(f"Available: {p.is_available()}")
    print(f"Total    : {len(p.list_models())} models")
    print()
    for t in ["code", "multilingual", "reasoning", "fast"]:
        models = p.list_models_by_type(t)
        if models:
            print(f"{t:15}: {models}")
