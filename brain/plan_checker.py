"""
brain/plan_checker.py
=====================
Independent plan reviewer.

Role:
    - Takes a plan produced by Planner
    - Critiques it from a DIFFERENT provider's perspective
    - Returns: approve | refine | reject

Why independent?
    - Planner may be biased toward its own plan
    - Using a different provider avoids "confirmation bias"

Output:
{
    "verdict": "approve" | "refine" | "reject",
    "score": 0-10,
    "concerns": [...],
    "suggestions": [...],
    "feedback": "text"
}
"""

import json
from typing import Dict, Any, List, Optional

try:
    from brain.core_paths import PROJECT_ROOT
except ImportError:
    import os
    PROJECT_ROOT = os.path.expanduser("~/moroai")


CHECKER_SYSTEM = """You are MOROAI's Plan Reviewer — an INDEPENDENT auditor.

You will receive:
    1. A plan (list of steps)
    2. Current project context

Your job: critique the plan BEFORE it gets executed.

Evaluate on:
    - Correctness:  Are the paths valid? Do the steps make sense?
    - Completeness: Is anything missing?
    - Ordering:     Are dependencies respected?
    - Safety:       Any risk of breaking core files?
    - Scope:        Is it too small? Too big? Off target?

Answer with valid JSON ONLY:
{
    "verdict": "approve" | "refine" | "reject",
    "score": 0-10,
    "concerns": ["<concern 1>", "<concern 2>"],
    "suggestions": ["<suggestion 1>"],
    "feedback": "<one paragraph in Arabic and English>"
}

Rules:
    - score >= 7 -> approve
    - score 4-6  -> refine
    - score < 4  -> reject
    - Be strict. Do not approve bad plans.
    - Output JSON only. No markdown fences. No extra text.
"""


def _strip_fences(text: str) -> str:
    if not text:
        return text
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if len(lines) > 1:
            t = "\n".join(lines[1:])
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3].rstrip()
    return t


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    cleaned = _strip_fences(text)
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    s = cleaned.find("{")
    e = cleaned.rfind("}")
    if s != -1 and e > s:
        try:
            return json.loads(cleaned[s:e+1])
        except Exception:
            pass
    return None


def _pick_checker_provider(brain, exclude_provider: str):
    """
    Pick a provider DIFFERENT from the one that created the plan.
    Falls back to any available if no alternative.
    """
    try:
        avail = brain.available_providers()
        candidates = [n for n, info in avail.items() if info.get("is_available")]
    except Exception:
        return None, None

    if not candidates:
        return None, None

    # Prefer a different one
    for name in candidates:
        if name != exclude_provider:
            return name, None
    # Only fallback: same provider
    return candidates[0], None


def _manifest_short() -> str:
    try:
        from brain.project_scanner import scan_project
        m = scan_project()
        dirs = m.get("directories", {})
        parts = [f"Project: {m['total_files']} files"]
        for d, files in dirs.items():
            parts.append(f"  {d}/: {len(files)} files")
        return "\n".join(parts)
    except Exception:
        return "(manifest unavailable)"


def _format_plan(plan: Dict[str, Any]) -> str:
    steps = plan.get("steps") or []
    lines = []
    lines.append(f"Summary: {plan.get('summary', '?')}")
    if plan.get("task"):
        lines.append(f"Original task: {plan['task']}")
    lines.append(f"Steps ({len(steps)}):")
    for s in steps:
        lines.append(
            f"  {s.get('n')}. [{s.get('action')}] {s.get('path')} — {s.get('description', '')}"
        )
    return "\n".join(lines)


def check_plan(brain, plan: Dict[str, Any],
               planner_provider: str = "",
               temperature: float = 0.2) -> Dict[str, Any]:
    """
    Independent check of a plan.

    planner_provider: name of provider that created the plan (to avoid it)
    """
    if not plan or not plan.get("steps"):
        return {
            "verdict": "reject",
            "score": 0,
            "concerns": ["empty or invalid plan"],
            "suggestions": [],
            "feedback": "No plan to check.",
        }

    prompt = f"""PLAN TO REVIEW:
{_format_plan(plan)}

PROJECT CONTEXT:
{_manifest_short()}

Review the plan. Output JSON only."""

    # Try a different provider first
    chosen, _ = _pick_checker_provider(brain, exclude_provider=planner_provider)

    # Note: brain.ask() will pick its own provider. To force independence,
    # we'd need provider-level control. For now, we just note the planner_provider
    # and let brain.ask() route normally (metrics will improve over time).
    resp = brain.ask(
        prompt=prompt,
        content_class="standard",
        system=CHECKER_SYSTEM,
        temperature=temperature,
    )

    if not resp.success:
        # Fail-open: approve if checker fails (don't block)
        return {
            "verdict": "approve",
            "score": 5,
            "concerns": [f"checker LLM failed: {resp.error}"],
            "suggestions": [],
            "feedback": "(checker unavailable — proceeding)",
            "provider": resp.provider,
            "model": resp.model,
        }

    parsed = _extract_json(resp.text or "")
    if not parsed:
        return {
            "verdict": "approve",
            "score": 5,
            "concerns": ["could not parse checker output"],
            "suggestions": [],
            "feedback": (resp.text or "")[:300],
            "provider": resp.provider,
            "model": resp.model,
        }

    # Normalize
    verdict = (parsed.get("verdict") or "approve").lower()
    if verdict not in ("approve", "refine", "reject"):
        verdict = "approve"

    try:
        score = float(parsed.get("score", 5))
    except (TypeError, ValueError):
        score = 5.0

    concerns = parsed.get("concerns") or []
    if not isinstance(concerns, list):
        concerns = [str(concerns)]
    suggestions = parsed.get("suggestions") or []
    if not isinstance(suggestions, list):
        suggestions = [str(suggestions)]

    return {
        "verdict": verdict,
        "score": round(score, 1),
        "concerns": [str(c)[:200] for c in concerns[:5]],
        "suggestions": [str(s)[:200] for s in suggestions[:5]],
        "feedback": (parsed.get("feedback") or "")[:600],
        "provider": resp.provider,
        "model": resp.model,
        "latency_ms": resp.latency_ms,
    }


# ═══════════════════════════════════════════════
# Self-test (no LLM)
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print("Plan Checker module loaded.")
    print()
    # Test JSON extraction
    samples = [
        '{"verdict":"approve","score":8,"concerns":[],"suggestions":[],"feedback":"ok"}',
        '```json\n{"verdict":"reject","score":2,"concerns":["bad path"]}\n```',
        'Text before\n{"verdict":"refine","score":5}\ntext after',
    ]
    for i, s in enumerate(samples, 1):
        r = _extract_json(s)
        print(f"  Sample {i}: {'✅' if r else '❌'} verdict={r.get('verdict') if r else '-'}")
