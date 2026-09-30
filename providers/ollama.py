"""
providers/ollama.py
===================

Ollama provider adapter for MOROAI.

Ollama can run locally, or on a remote server via Cloudflare Tunnel.
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


OLLAMA_DEFAULT_CONFIG = ProviderConfig(
    name="ollama",
    enabled=True,
    priority=4,
    models=["qwen2.5:7b", "qwen2.5:3b", "phi3:mini"],
    capabilities=["chat"],
    api_key_env="OLLAMA_HOST",
    base_url="http://127.0.0.1:11434",
    is_free=True,
    paid_fallback_allowed=False,
    daily_limit=0,
    rpm_limit=0,
)


class OllamaProvider(BaseProvider):
    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or OLLAMA_DEFAULT_CONFIG)
        # Try rendezvous first (auto-detects Colab URL from Gist)
        env_host = ""
        try:
            from brain.rendezvous import get_url as _get_url
            env_host = _get_url(force=False) or ""
        except Exception:
            pass

        # Fallback to environment variable
        if not env_host:
            env_host = os.getenv("OLLAMA_HOST", "").strip()

        if env_host:
            self.config = ProviderConfig(
                name=self.config.name,
                enabled=self.config.enabled,
                priority=self.config.priority,
                models=list(self.config.models),
                capabilities=list(self.config.capabilities),
                api_key_env=self.config.api_key_env,
                base_url=env_host.rstrip("/"),
                is_free=True,
                paid_fallback_allowed=False,
                daily_limit=0,
                rpm_limit=0,
            )

    @property
    def name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        if not self.config.enabled or self.is_in_cooldown():
            return False
        return bool(self.config.base_url)

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
            return self._error_response("Ollama unavailable", code=503)

        chosen_model = model or self.config.models[0]

        full_prompt = prompt
        if system:
            full_prompt = system + "\n\n" + prompt

        payload = {
            "model": chosen_model,
            "prompt": full_prompt,
            "stream": False,
        }

        url = f"{self.config.base_url}/api/generate"
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            text = body.get("response", "") or ""
            return AIResponse(
                text=text,
                model=chosen_model,
                provider=self.name,
                success=True,
                latency_ms=self._elapsed_ms(start),
            )
        except urllib.error.HTTPError as e:
            return self._error_response(f"HTTP {e.code}: {e.reason}", code=e.code)
        except urllib.error.URLError as e:
            return self._error_response(f"Network: {e.reason}", code=503)
        except Exception as e:
            return self._error_response(f"{type(e).__name__}: {e}", code=500)


if __name__ == "__main__":
    p = OllamaProvider()
    print(f"Name     : {p.name}")
    print(f"Base URL : {p.config.base_url}")
    print(f"Models   : {p.list_models()}")
    print(f"Available: {p.is_available()}")
