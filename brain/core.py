"""
brain/core.py
=============

The central brain of MOROAI.

Cycle:
    PERCEIVE → ASSESS → PLAN → EXECUTE → REFLECT

Enforces:
    - D1..D7 prime directives
    - Owner age profile (D7)
    - 7-day ban when a minor tampers with the profile

Inspiration (no code copied):
    - ScratchAgent (MIT): PERCEIVE/ASSESS/EXECUTE/REFLECT
    - Genetic Prompt Engineering (2026): directive hash verification
    - Nexus Memory (MIT): memory integrated into reasoning
    - MAP (Nature): classify before execute
"""

import os
import hashlib
from typing import Optional, Dict, Any

from brain.core_paths import PROJECT_ROOT
from brain import prime_directives as PD
from brain import router as task_router
from brain import owner_profile as OP

from memory.checkpoint import CheckpointManager
from memory.manager import MemoryManager
from memory.learning import LearningMemory
from memory.workspace import WorkspaceManager

from providers.registry import ProviderRegistry
from providers.groq import GroqProvider
from providers.gemini import GeminiProvider
from providers.openrouter import OpenRouterProvider
from providers.ollama import OllamaProvider
from providers.base import AIResponse
from brain.identity import load_identity


# ============================================================
# Constants
# ============================================================

CONTENT_CLASSES = {"standard", "research", "media", "sensitive"}

DIRECTIVES_HASH_FILE = ".moroai/directives.sha256"


# ============================================================
# The Brain
# ============================================================

class MOROAI:
    """The central coordinator of MOROAI."""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = os.path.abspath(project_root or PROJECT_ROOT)

        # Identity
        self.identity = load_identity()

        # Subsystems
        self.memory = MemoryManager()
        self.learning = LearningMemory()
        self.checkpoints = CheckpointManager(self.project_root)
        self.workspace = WorkspaceManager(self.project_root)
        self.registry = ProviderRegistry()

        # Register providers
        self._register_providers()

        # Verify integrity of prime directives
        self._verify_directives()

        # ---- Owner profile + ban handling ----
        self.banned = False
        self.ban_seconds = 0
        self.owner = None

        # Check for existing ban
        banned, sec = OP.is_banned(self.project_root)
        if banned:
            self.banned = True
            self.ban_seconds = sec
            return

        # Try to load the profile
        try:
            self.owner = OP.load_profile(self.project_root)
        except ValueError:
            # Tampered profile → interactive handler
            self.owner = OP.handle_integrity_failure(
                self.project_root,
                reason="Owner profile was modified or is invalid.",
            )

        # No profile at all → first run → ask
        if self.owner is None and not self.banned:
            self.owner = OP.handle_integrity_failure(
                self.project_root,
                reason="No owner profile found (first run).",
            )
            # If the user turned out to be a minor, a ban was just created
            banned, sec = OP.is_banned(self.project_root)
            if banned:
                self.banned = True
                self.ban_seconds = sec

    # -------- Setup --------

    def _register_providers(self) -> None:
        """Register all available free providers."""
        try:
            self.registry.register("groq", GroqProvider())
        except Exception:
            pass
        try:
            self.registry.register("gemini", GeminiProvider())
        except Exception:
            pass
        try:
            self.registry.register("openrouter", OpenRouterProvider())
        except Exception:
            pass
        try:
            self.registry.register("ollama", OllamaProvider())
        except Exception:
            pass

    def _verify_directives(self) -> None:
        """Compute SHA-256 of prime_directives.py and record if it changed."""
        path = os.path.join(self.project_root, "brain", "prime_directives.py")
        if not os.path.exists(path):
            return

        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()

        store = os.path.join(self.project_root, DIRECTIVES_HASH_FILE)
        os.makedirs(os.path.dirname(store), exist_ok=True)

        previous = None
        if os.path.exists(store):
            with open(store, "r", encoding="utf-8") as f:
                previous = f.read().strip()

        if previous != digest:
            with open(store, "w", encoding="utf-8") as f:
                f.write(digest)

    # -------- Public API --------

    def ask(
        self,
        prompt: str,
        content_class: str = "standard",
        system: Optional[str] = None,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> AIResponse:
        """Main entry: receive prompt, route, execute, remember."""

        # 0. BAN CHECK
        if self.banned:
            days = self.ban_seconds // 86400
            hours = (self.ban_seconds % 86400) // 3600
            return AIResponse(
                text="",
                model="",
                provider="core",
                success=False,
                error=(
                    f"Access denied. You are banned for {days}d {hours}h "
                    f"due to age-policy violation."
                ),
            )

        # 1. PERCEIVE + ASSESS
        if content_class not in CONTENT_CLASSES:
            return AIResponse(
                text="",
                model="",
                provider="core",
                success=False,
                error=(
                    f"Invalid content_class '{content_class}'. "
                    f"Must be one of {sorted(CONTENT_CLASSES)}."
                ),
            )

        # 2. AGE CHECK (Directive D7)
        if not OP.is_content_allowed(content_class, self.owner):
            return AIResponse(
                text="",
                model="",
                provider="core",
                success=False,
                error=(
                    f"Content class '{content_class}' is not permitted "
                    f"under the current owner profile."
                ),
            )

        # 3. RECALL: search for relevant lessons
        lessons = self.learning.search_lessons(prompt, limit=3)
        lessons_text = ""
        if lessons:
            bullets = "\n".join(f"- {l['rule']}" for l in lessons)
            lessons_text = (
                "\n\nRelevant lessons learned from past interactions:\n"
                + bullets
            )

        # 3. SMART ROUTING (pick best model for this task type)
        if model is None:
            try:
                avail = self.available_providers()
                available = [n for n, info in avail.items() if info.get("is_available")]
                routing = task_router.analyze(prompt, available)
                if routing.get("model"):
                    model = routing["model"]
            except Exception:
                pass

        # 4. EXECUTE via registry (with automatic fallback)
        # Merge MOROAI identity + lessons + any per-call system prompt
        parts = [self.identity]
        if lessons_text:
            parts.append(lessons_text.strip())
        if system:
            parts.append(system)
        combined_system = "\n\n".join(parts)

        response = self.registry.call_with_fallback(
            prompt=prompt,
            model=model,
            system=combined_system,
            temperature=temperature,
        )

        # 5. REFLECT: save to memory + learning DB
        self._log(prompt, response, content_class)
        try:
            self.learning.save_episode(
                prompt=prompt,
                response=response.text,
                success=response.success,
                provider=response.provider,
                model=response.model,
                latency_ms=response.latency_ms,
                tokens_used=response.tokens_used,
                content_class=content_class,
                error=response.error,
            )
        except Exception:
            pass

        return response

    def available_providers(self) -> Dict[str, Any]:
        """Report registered providers and their availability."""
        out = {}
        for p in self.registry.all():
            out[p.name] = {
                "is_free": p.is_free(),
                "is_available": p.is_available(),
                "in_cooldown": p.is_in_cooldown(),
                "priority": p.config.priority,
                "models": p.list_models(),
            }
        return out

    # -------- Internal --------

    def _log(self, prompt: str, response: AIResponse, content_class: str) -> None:
        """Persist interaction to memory (never raises)."""
        try:
            self.memory.save_interaction(
                prompt=prompt,
                response_text=response.text,
                provider=response.provider,
                model=response.model,
                success=response.success,
                error=response.error,
                tokens_used=response.tokens_used,
                latency_ms=response.latency_ms,
                metadata={"content_class": content_class},
            )
        except Exception:
            pass


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    print("Booting MOROAI brain...\n")

    brain = MOROAI()

    if brain.banned:
        days = brain.ban_seconds // 86400
        print(f"⛔ BANNED for {days} days. Cannot run self-test.")
        raise SystemExit(1)

    # Show registered providers
    print("Registered providers:")
    for name, info in brain.available_providers().items():
        status = "✅ available" if info["is_available"] else "❌ unavailable"
        print(f"  - {name}: {status} (free={info['is_free']}, priority={info['priority']})")
    print()

    # Ask a real question
    print("Sending test prompt (Arabic)...")
    resp = brain.ask(
        prompt="Say 'MOROAI alive' in Arabic, nothing else.",
        system="Reply in one short line.",
        temperature=0.3,
    )

    print("─" * 50)
    if resp.success:
        print(f"✅ SUCCESS")
        print(f"   Text     : {resp.text}")
        print(f"   Provider : {resp.provider}")
        print(f"   Model    : {resp.model}")
        print(f"   Latency  : {resp.latency_ms} ms")
    else:
        print(f"❌ FAILED")
        print(f"   Error    : {resp.error}")
        print(f"   Code     : {resp.error_code}")
    print("─" * 50)

    # Test invalid content_class
    print("\nTesting invalid content_class...")
    bad = brain.ask("hello", content_class="invalid")
    print(f"  Success : {bad.success}")
    assert bad.success is False
    print(f"  Error   : {bad.error[:70]}...")

    print("\n✅ Brain self-test done.")
