"""
providers/registry.py
=====================

Central registry for all free AI providers in MOROAI.

Responsibilities:
    - Maintain an ordered list of free providers (by priority)
    - Enforce Free-First policy (no paid providers ever)
    - Provide fallback chain when a provider fails or quota is exhausted

Free-First Policy (enforced):
    - Only providers with is_free=True are loaded.
    - If all free providers fail, raise AllProvidersFailed.
    - MOROAI NEVER falls back to a paid provider.

Inspiration (no code copied):
    - multi-ai-provider-patterns: registry pattern + circuit breaker
    - tollfree (MIT): provider rotation logic
    - kestrel: verified 2026 free-tier limits
"""

from typing import List, Optional, Dict
from dataclasses import asdict
import json

try:
    from .base import BaseProvider, ProviderConfig, AIResponse
except ImportError:
    from base import BaseProvider, ProviderConfig, AIResponse


# ============================================================
# Verified free-tier limits (2026)
# Source: kestrel/free-model-landscape-2026, Free-LLM, provider docs
# ============================================================

FREE_PROVIDER_DEFAULTS: Dict[str, dict] = {
    "groq": {
        "priority": 1,
        "models": [
            "qwen/qwen3.8-27b",
            "openai/gpt-oss-20b",
            "openai/gpt-oss-120b",
            "llama-3.1-8b-instant",
        ],
        "daily_limit": 14400,
        "rpm_limit": 30,
        "api_key_env": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "capabilities": ["chat", "code"],
    },
    "ollama_cloud": {
        "priority": 2,
        "models": [
            "gemma4:31b",
            "glm-4.7",
            "gpt-oss:120b",
            "devstral-small-2:24b",
        ],
        "daily_limit": 0,
        "rpm_limit": 0,
        "api_key_env": "OLLAMA_API_KEY",
        "base_url": "https://ollama.com/api/chat",
        "capabilities": ["chat", "code"],
    },
    "gemini": {
        "priority": 3,
        "models": ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash-lite"],
        "daily_limit": 1500,
        "rpm_limit": 15,
        "api_key_env": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "capabilities": ["chat", "code"],
    },
    "cerebras": {
        "priority": 3,
        "models": ["llama-3.3-70b", "llama-3.1-8b"],
        "daily_limit": 14400,
        "rpm_limit": 30,
        "api_key_env": "CEREBRAS_API_KEY",
        "base_url": "https://api.cerebras.ai/v1/chat/completions",
        "capabilities": ["chat", "code"],
    },
    "sambanova": {
        "priority": 4,
        "models": ["Meta-Llama-3.3-70B-Instruct"],
        "daily_limit": 0,      # unlimited requests (rate-limited only)
        "rpm_limit": 10,
        "api_key_env": "SAMBANOVA_API_KEY",
        "base_url": "https://api.sambanova.ai/v1/chat/completions",
        "capabilities": ["chat"],
    },
    "openrouter": {
        "priority": 4,
        "models": ["cohere/north-mini-code:free", "nvidia/nemotron-3-ultra-550b-a55b:free", "qwen/qwen3.8-27b:free"],
        "daily_limit": 50,
        "rpm_limit": 20,
        "api_key_env": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "capabilities": ["chat"],
    },
}


# ============================================================
# Registry
# ============================================================

class ProviderRegistry:
    """
    Registry of all free providers, ordered by priority.

    Usage:
        registry = ProviderRegistry()
        registry.register("groq", GroqProvider())
        registry.register("gemini", GeminiProvider())
        chain = registry.fallback_chain()   # [groq, gemini, ...]
        response = registry.call_with_fallback("Hello")
    """

    def __init__(self):
        self._providers: Dict[str, BaseProvider] = {}

    def register(self, name: str, provider: BaseProvider) -> None:
        """Register a provider. Rejects non-free providers."""
        if not provider.is_free():
            raise ValueError(
                f"Provider '{name}' is not free. MOROAI only allows free providers."
            )
        self._providers[name] = provider

    def unregister(self, name: str) -> None:
        """Remove a provider from the registry."""
        self._providers.pop(name, None)

    def get(self, name: str) -> Optional[BaseProvider]:
        """Get a provider by name."""
        return self._providers.get(name)

    def all(self) -> List[BaseProvider]:
        """Return all registered providers, sorted by priority."""
        return sorted(
            self._providers.values(),
            key=lambda p: p.config.priority,
        )

    def available(self) -> List[BaseProvider]:
        """Return providers that are currently available (key present, not in cooldown)."""
        return [p for p in self.all() if p.is_available()]

    def fallback_chain(self) -> List[BaseProvider]:
        """
        Return the ordered fallback chain of available providers.
        Providers in cooldown or unavailable are excluded.
        """
        return self.available()

    def call_with_fallback(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AIResponse:
        """
        Try every free provider (in priority order) until one succeeds.
        Within each provider, try every model before moving to the next provider.

        If all providers fail, returns an AIResponse with success=False.
        NEVER falls back to a paid provider.
        """
        chain = self.fallback_chain()
        if not chain:
            return AIResponse(
                text="",
                model="",
                provider="registry",
                success=False,
                error="No free providers available. All may be in cooldown or missing API keys.",
            )

        last_error = ""
        for provider in chain:
            # If specific model requested, try it first, then fall back to others
            if model:
                all_models = provider.list_models()
                models_to_try = [model] + [m for m in all_models if m != model]
            else:
                models_to_try = provider.list_models()
            if not models_to_try:
                continue

            for current_model in models_to_try:
                response = provider.chat(
                    prompt=prompt,
                    model=current_model,
                    system=system,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                if response.success:
                    provider.record_success()
                    return response

                last_error = f"{provider.name}: {response.error}"
                code = response.error_code

                # 401/403 → bad key, skip this provider entirely
                if code in (401, 403):
                    provider.record_failure(threshold=1, cooldown_sec=3600)
                    break

                # 429/404/5xx/timeout → try next model, then next provider
                if code in (429, 404) or (code and 500 <= code < 600):
                    provider.record_failure()
                    continue

            # After trying all models, apply circuit breaker
            provider.record_failure()

        return AIResponse(
            text="",
            model="",
            provider="registry",
            success=False,
            error=f"All free providers failed. Last error: {last_error}",
        )


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    print("ProviderRegistry module loaded successfully.")
    print(f"  - FREE_PROVIDER_DEFAULTS keys: {list(FREE_PROVIDER_DEFAULTS.keys())}")
    print(f"  - ProviderRegistry class: {ProviderRegistry}")
