"""
brain/router_v2.py
==================
Smart router that uses real provider metrics.

Combines:
    - router.py (task type detection — reused)
    - provider_scorer.py (real performance)

Logic:
    1. Detect task type (from router.py)
    2. For each available provider, compute:
         score = metrics_score + base_priority_bonus
    3. Skip providers in cooldown
    4. Return the best.

Falls back to router.py if metrics are empty.
"""

from typing import List, Dict, Any, Optional

from brain import router as legacy_router
from brain import provider_scorer as scorer


# Base priority (like router.py's order, but smaller weights)
# 20 points bonus for first, 18 for second, etc.
def _base_bonus(provider: str, task_type: str) -> float:
    prefs = legacy_router.PREFERENCES.get(task_type, legacy_router.PREFERENCES["general"])
    if provider not in prefs:
        return 0.0
    rank = prefs.index(provider)
    return max(0.0, 20.0 - rank * 2)


def pick_best(task_type: str, available: List[str]) -> Optional[str]:
    """
    Pick the best provider for the task, using metrics + base priority.
    Returns None if nothing is available.
    """
    if not available:
        return None

    candidates = []
    for p in available:
        # Skip providers on cooldown
        if scorer.in_cooldown(p, task_type):
            continue
        s = scorer.score(p, task_type)
        b = _base_bonus(p, task_type)
        candidates.append((p, s + b, s, b))

    # If all in cooldown -> fall back to full list (don't starve)
    if not candidates:
        candidates = [(p, 50.0, 50.0, 0.0) for p in available]

    # Sort by total desc
    candidates.sort(key=lambda x: x[1], reverse=True)
    best = candidates[0][0]

    # Fallback to legacy if metrics empty (all at 50)
    has_metrics = any(s != 50.0 for _, _, s, _ in candidates)
    if not has_metrics:
        legacy = legacy_router.pick_provider(task_type, available)
        if legacy:
            return legacy

    return best


def pick_model(task_type: str, provider: str) -> Optional[str]:
    """Reuse legacy model preferences."""
    return legacy_router.pick_model(task_type, provider)


def analyze(message: str, available: List[str]) -> Dict[str, Any]:
    """
    Same output shape as router.analyze() — drop-in replacement.
    """
    task_type = legacy_router.detect_task_type(message)
    provider = pick_best(task_type, available)
    model = pick_model(task_type, provider) if provider else None

    # Gather scores for transparency
    scores = {}
    for p in available:
        scores[p] = {
            "score": scorer.score(p, task_type),
            "cooldown": scorer.in_cooldown(p, task_type),
        }

    return {
        "task_type": task_type,
        "provider": provider,
        "model": model,
        "scores": scores,
        "reason": f"v2: task='{task_type}' -> provider='{provider}' (metrics-based)",
    }


# ═══════════════════════════════════════════════
# Self-test
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    available = ["groq", "gemini", "nvidia", "ollama_cloud", "openrouter", "ollama"]

    print("Router V2 — with no metrics yet")
    print("=" * 60)
    tests = [
        "اكتب لي دالة بايثون",
        "حلل لي هذه الرواية",
        "ترجم هذه الفقرة",
        "مرحبا كيف حالك",
    ]
    for t in tests:
        r = analyze(t, available)
        print(f"Input : {t}")
        print(f"Type  : {r['task_type']}")
        print(f"Chosen: {r['provider']} / {r['model']}")
        print(f"Score : {r['scores'].get(r['provider'], {})}")
        print()

    print("=" * 60)
    print("Now simulate: nvidia fails 3 times for 'code'")
    scorer.record_failure("nvidia", "code")
    scorer.record_failure("nvidia", "code")
    scorer.record_failure("nvidia", "code")
    scorer.record_success("groq", "code", 1200)
    scorer.record_success("groq", "code", 900)
    scorer.record_success("groq", "code", 1100)

    r = analyze("اكتب لي دالة بايثون", available)
    print(f"After failure, chose: {r['provider']}")
    print(f"Scores: {r['scores']}")

    # Clean up test data
    print()
    print("(Test data written to memory/data/provider_metrics.json)")
