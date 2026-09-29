"""
providers/gemini.py
===================

Google Gemini provider adapter for MOROAI.

Free tier (2026):
    - 1,500 requests/day on flash-lite
    - 15 requests/minute
    - No credit card required

API endpoint:
    POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key=KEY
    Body: {"contents":[...], "systemInstruction":{...}}
    Response: candidates[0].content.parts[0].text

Inspiration (no code copied):
    - Google AI docs: v1beta generateContent format
    - ScratchAgent (MIT): error handling
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


GEMINI_DEFAULT_CONFIG = ProviderConfig(
    name="gemini",
    enabled=True,
    priority=2,
    models=[
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
        "gemini-3.7-flash",
    ],
    capabilities=["chat", "code"],
    api_key_env="GEMINI_API_KEY",
    base_url="https://generativelanguage.googleapis.com/v1beta/models",
    is_free=True,
    paid_fallback_allowed=False,
    daily_limit=1500,
    rpm_limit=15,
)


class GeminiProvider(BaseProvider):
    """Concrete implementation of BaseProvider for Google Gemini."""

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or GEMINI_DEFAULT_CONFIG)

    @property
    def name(self) -> str:
        return "gemini"

    def is_available(self) -> bool:
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
        start = self._start_timer()

        if not self.is_available():
            return self._error_response(
                f"Provider '{self.name}' unavailable (cooldown or missing key).",
                code=503,
            )

        chosen_model = model or self.config.models[0]
        if not chosen_model:
            return self._error_response("No model specified.", code=400)

        # Build Gemini-specific payload
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        payload = {"contents": contents}

        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        gen_cfg = {"temperature": temperature}
        if max_tokens:
            gen_cfg["maxOutputTokens"] = max_tokens
        payload["generationConfig"] = gen_cfg

        api_key = os.getenv(self.config.api_key_env, "").strip()
        url = f"{self.config.base_url}/{chosen_model}:generateContent?key={api_key}"

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": "MOROAI/0.1",
        }

        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers=headers, method="POST",
        )

        try:
            return self._call_with_retry(self._do_request, req, start)
        except Exception as e:
            return self._error_response(f"{type(e).__name__}: {e}", code=500)

    def _do_request(self, req, start):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                body = json.loads(raw)

            # Extract text
            text = ""
            candidates = body.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if parts:
                    text = parts[0].get("text", "") or ""

            # Token usage
            tokens = None
            usage = body.get("usageMetadata", {})
            if usage:
                tokens = usage.get("totalTokenCount")

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
            return self._error_response(f"Invalid JSON: {e}", code=500)

        except Exception as e:
            return self._error_response(
                f"Unexpected: {type(e).__name__}: {e}", code=500,
            )


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    p = GeminiProvider()
    print(f"Provider name    : {p.name}")
    print(f"Is free?         : {p.is_free()}")
    print(f"Is available?    : {p.is_available()}")
    print(f"Models           : {p.list_models()}")
    print(f"Supports 'code'? : {p.supports('code')}")
    print(f"Daily limit      : {p.config.daily_limit}")
