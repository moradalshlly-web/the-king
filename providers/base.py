"""
providers/base.py
=================

Abstract base interface for all AI providers in MOROAI.

MOROAI is the coordinator. Providers are resources it calls, NOT controllers.
Every provider MUST implement this interface.

Free-First Policy:
    - is_free must be True (no paid providers allowed)
    - If quota is exhausted, MOROAI switches to another free provider
    - MOROAI NEVER falls back to a paid provider

Inspiration (no code copied):
    - EasyAgent (MIT): unified provider interface
    - ScratchAgent (MIT): strict separation between data and logic
    - tollfree (MIT): failover logic across free-tier providers
    - multi-ai-provider-patterns: registry + circuit breaker pattern
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List
from time import time


# ============================================================
# Data Structures
# ============================================================

@dataclass
class ProviderConfig:
    """Configuration for a single provider."""

    name: str
    enabled: bool = True
    priority: int = 1

    # Model and capability information
    models: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=lambda: ["chat"])

    # Connection
    api_key_env: str = ""
    base_url: str = ""

    # Free-First policy (mandatory)
    is_free: bool = True
    paid_fallback_allowed: bool = False

    # Rate limits (real numbers from providers, updated 2026)
    daily_limit: int = 0          # requests per day (0 = unlimited)
    rpm_limit: int = 0            # requests per minute (0 = unlimited)
    tpm_limit: int = 0            # tokens per minute (0 = unlimited)
    tpd_limit: int = 0            # tokens per day (0 = unlimited)

    # Circuit breaker
    consecutive_failures: int = 0
    cooldown_until: float = 0.0   # unix timestamp; provider is offline until this


@dataclass
class AIResponse:
    """Unified response shape from any provider."""
    text: str
    model: str
    provider: str
    success: bool
    error: Optional[str] = None
    error_code: Optional[int] = None
    tokens_used: Optional[int] = None
    latency_ms: Optional[float] = None


# ============================================================
# Abstract Base Interface
# ============================================================

class BaseProvider(ABC):
    """Abstract base class that every provider MUST implement."""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self._client = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider name."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is ready to use (key present, enabled, not in cooldown)."""
        pass

    @abstractmethod
    def chat(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AIResponse:
        """Send a message and get a response."""
        pass

    @abstractmethod
    def list_models(self) -> List[str]:
        """Return available model names."""
        pass

    # -------- Helper methods (shared by all subclasses) --------

    def supports(self, capability: str) -> bool:
        """Check if this provider supports a given capability."""
        return capability in self.config.capabilities

    def is_free(self) -> bool:
        """Check if this provider is free. Always True in MOROAI."""
        return bool(self.config.is_free)

    def is_in_cooldown(self) -> bool:
        """Check if provider is in circuit-breaker cooldown."""
        return time() < self.config.cooldown_until

    def record_success(self) -> None:
        """Reset failure counter after a successful call."""
        self.config.consecutive_failures = 0

    def record_failure(self, threshold: int = 3, cooldown_sec: int = 300) -> None:
        """
        Increment failure counter.
        After 'threshold' consecutive failures, enter cooldown for 'cooldown_sec'.
        """
        self.config.consecutive_failures += 1
        if self.config.consecutive_failures >= threshold:
            self.config.cooldown_until = time() + cooldown_sec

    def _error_response(
        self,
        error: str,
        code: Optional[int] = None,
    ) -> AIResponse:
        """Build a standard error response."""
        return AIResponse(
            text="",
            model="",
            provider=self.name,
            success=False,
            error=error,
            error_code=code,
        )

    def _start_timer(self) -> float:
        """Start measuring elapsed time."""
        return time()

    def _elapsed_ms(self, start: float) -> float:
        """Compute elapsed time in milliseconds."""
        return round((time() - start) * 1000, 2)

    def _call_with_retry(self, func, *args, max_attempts=3, **kwargs):
        """Retry a function call with exponential backoff."""
        import time
        for attempt in range(1, max_attempts + 1):
            result = func(*args, **kwargs)
            # إذا نجح، أعد النتيجة فورًا
            if result.success:
                return result
            # إذا فشل بسبب خطأ شبكة أو معدل، أعد المحاولة
            code = result.error_code or 0
            if code in (429, 408, 500, 502, 503, 504):
                if attempt < max_attempts:
                    wait = 2 ** (attempt - 1)  # 1s, 2s, 4s
                    time.sleep(wait)
                    continue
            # خطأ آخر لا يستحق إعادة المحاولة
            return result
        return result


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    print("BaseProvider module loaded successfully.")
    print(f"  - ProviderConfig : {ProviderConfig}")
    print(f"  - AIResponse     : {AIResponse}")
    print(f"  - BaseProvider   : {BaseProvider}")
