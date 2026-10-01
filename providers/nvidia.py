"""
providers/nvidia.py
===================

NVIDIA NIM provider adapter for MOROAI.

Free tier: 40 requests/minute, no daily limit.
No credit card required.
80+ models available via https://build.nvidia.com

Verified working models (October 2026).
Uses OpenAI-compatible API (no SDK required).
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


NVIDIA_MODELS = {
    # Reasoners (verified fast)
    "nvidia/nemotron-3-ultra-550b-a55b":    {"type": "reasoning", "priority": 1, "speed": "fast"},
    "nvidia/nemotron-3-super-120b-a12b":    {"type": "reasoning", "priority": 2, "speed": "fast"},

    # Fast (sub-second)
    "openai/gpt-oss-20b":                   {"type": "fast", "priority": 1, "speed": "fast"},
    "nvidia/riva-translate-4b-instruct-v2": {"type": "translate", "priority": 1, "speed": "fast"},

    # Multilingual / heavy
    "google/gemma-4-31b-it":                {"type": "multilingual", "priority": 1, "speed": "slow"},
    "z-ai/glm-5.3-flash":                   {"type": "general", "priority": 1, "speed": "slow"},
}


NVIDIA_DEFAULT_CONFIG = ProviderConfig(
    name="nvidia",
    enabled=True,
    priority=2,
    models=list(NVIDIA_MODELS.keys()),
    capabilities=["chat", "code"],
    api_key_env="NVIDIA_API_KEY",
    base_url="https://integrate.api.nvidia.com/v1/chat/completions",
    is_free=True,
    paid_fallback_allowed=False,
    daily_limit=0,
    rpm_limit=40,
)


class NvidiaProvider(BaseProvider):
    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or NVIDIA_DEFAULT_CONFIG)

    @property
    def name(self) -> str:
        return "nvidia"

    def is_available(self) -> bool:
        if not self.config.enabled:
            return False
        if self.is_in_cooldown():
            return False
        return bool(os.getenv(self.config.api_key_env, "").strip())

    def list_models(self) -> List[str]:
        return list(self.config.models)

    def list_models_by_type(self, model_type: str) -> List[str]:
        return [m for m, info in NVIDIA_MODELS.items() if info.get("type") == model_type]

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
            return self._error_response("NVIDIA NIM unavailable (no API key).", code=503)

        chosen_model = model or self.config.models[0]

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": chosen_model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
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
            with urllib.request.urlopen(req, timeout=180) as resp:
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
    p = NvidiaProvider()
    print(f"Name     : {p.name}")
    print(f"Available: {p.is_available()}")
    print(f"Total    : {len(p.list_models())} models")
    print()
    for m, info in NVIDIA_MODELS.items():
        print(f"  {info['speed']:5s}  {info['type']:15s}  {m}")
