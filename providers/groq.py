"""
providers/groq.py
=================

Groq provider adapter for MOROAI.

Groq offers fast, free inference for open-source models.
Free-tier limits (verified 2026):
    - 30 requests / minute
    - 14,400 requests / day (for most models)

Environment:
    GROQ_API_KEY : API key from https://console.groq.com/keys

Inspiration (no code copied):
    - ScratchAgent (MIT): error handling pattern
    - EasyAgent (MIT): HTTP request structure
    - multi-ai-provider-patterns: circuit breaker integration
    - tollfree (MIT): 429 quota handling
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
# Default configuration for Groq
# ============================================================

GROQ_DEFAULT_CONFIG = ProviderConfig(
    name="groq",
    enabled=True,
    priority=1,
    models=[
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "llama-3.1-8b-instant",
    ],
    capabilities=["chat", "code"],
    api_key_env="GROQ_API_KEY",
    base_url="https://api.groq.com/openai/v1/chat/completions",
    is_free=True,
    paid_fallback_allowed=False,
    daily_limit=14400,
    rpm_limit=30,
)


# ============================================================
# Groq Provider
# ============================================================

class GroqProvider(BaseProvider):
    """Concrete implementation of BaseProvider for Groq."""

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or GROQ_DEFAULT_CONFIG)

    @property
    def name(self) -> str:
        return "groq"

    def is_available(self) -> bool:
        """Return True if enabled, not in cooldown, and API key is present."""
        if not self.config.enabled:
            return False
        if self.is_in_cooldown():
            return False
        key = os.getenv(self.config.api_key_env, "").strip()
        return bool(key)

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
        """Send a chat request to Groq."""

        start = self._start_timer()

        # 1. Availability check
        if not self.is_available():
            return self._error_response(
                f"Provider '{self.name}' unavailable "
                f"(cooldown={self.is_in_cooldown()}, key_present={bool(os.getenv(self.config.api_key_env))})",
                code=503,
            )

        # 2. Model selection
        chosen_model = model or (self.config.models[0] if self.config.models else "")
        if not chosen_model:
            return self._error_response("No model specified.", code=400)

        # 3. Build payload
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": chosen_model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        # 4. Build HTTP request
        api_key = os.getenv(self.config.api_key_env, "").strip()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "MOROAI/0.1",
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.config.base_url,
            data=data,
            headers=headers,
            method="POST",
        )

        # 5. Execute and handle response
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                body = json.loads(raw)

            text = ""
            if "choices" in body and body["choices"]:
                msg = body["choices"][0].get("message", {})
                text = msg.get("content", "") or ""

            tokens = None
            if "usage" in body:
                tokens = body["usage"].get("total_tokens")

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
            return self._error_response(f"Network error: {e.reason}", code=503)

        except json.JSONDecodeError as e:
            return self._error_response(f"Invalid JSON response: {e}", code=500)

        except Exception as e:
            return self._error_response(
                f"Unexpected error: {type(e).__name__}: {e}",
                code=500,
            )


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    p = GroqProvider()
    print(f"Provider name    : {p.name}")
    print(f"Is free?         : {p.is_free()}")
    print(f"Is available?    : {p.is_available()}")
    print(f"Models           : {p.list_models()}")
    print(f"Supports 'code'? : {p.supports('code')}")
    print(f"Daily limit      : {p.config.daily_limit}")
    print(f"RPM limit        : {p.config.rpm_limit}")
