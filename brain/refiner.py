"""
brain/refiner.py
================
Iterative refiner for MOROAI — built for EXTENSION.

Today:
    - Loop: critique -> refine -> critique ... until target or max_iterations
    - Records every attempt in `patterns` table
    - Records successful strategies in `skills`
    - Caches what worked for Meta-Learner (future)

Future (extendable without rewrite):
    - Meta-Learner reads patterns + skills to auto-tune prompts
    - Cross-site learning (strategies that work for landing work for blog)
    - Strategy library stored in HF
"""

import os
from typing import Dict, Any, Optional, List

try:
    from brain.core_paths import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = os.path.expanduser("~/moroai")


REFINER_SYSTEM = """You are MOROAI's Refiner — a surgical HTML editor.

You receive:
    1. The current HTML content of a file.
    2. A list of PROBLEMS found by an automated critic.
    3. A list of SUGGESTIONS (visual improvements).

Your job:
    - Fix ALL the listed problems.
    - Apply the suggestions when reasonable.
    - Keep what already works.
    - Do NOT rewrite from scratch.
    - Keep <html lang="ar" dir="rtl" data-theme="purple"> on the first line.

CRITICAL RULES:
    1. Output ONLY the corrected HTML.
    2. No markdown fences. No explanations.
    3. Start with <!DOCTYPE html>, end with </html>.
    4. Preserve the design.css link and all design-system classes.
    5. If content is too short, add meaningful Arabic content.
    6. If placeholders exist, replace with real Arabic text.
"""


# ═══════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════

def _read_file(path: str) -> Optional[str]:
    full = path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)
    if not os.path.isfile(full):
        return None
    try:
        with open(full, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def _write_file(path: str, content: str) -> bool:
    full = path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)
    try:
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception:
        return False


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


def _build_refine_prompt(html: str, issues: List[str],
                         suggestions: List[str]) -> str:
    issues_block = "\n".join(f"  - {i}" for i in issues[:10]) or "  (لا مشاكل ثابتة)"
    suggestions_block = "\n".join(f"  - {s}" for s in suggestions[:6]) or "  (لا اقتراحات)"
    return f"""Current HTML:
-----BEGIN HTML-----
{html[:8000]}
-----END HTML-----

PROBLEMS DETECTED:
{issues_block}

SUGGESTIONS:
{suggestions_block}

Rewrite the HTML fixing all the above. Output the corrected HTML only."""


# ═══════════════════════════════════════════════
# Learning hooks (extensible)
# ═══════════════════════════════════════════════

def _record_attempt(path: str, iteration: int,
                    before_score: float, after_score: float,
                    issues: List[str]) -> None:
    """Record a refinement attempt in `patterns` for Meta-Learner."""
    try:
        from memory.learning import LearningMemory
        m = LearningMemory()
        delta = round(after_score - before_score, 2)
        direction = "up" if delta > 0 else ("down" if delta < 0 else "flat")
        top_issue = (issues or ["unknown"])[0][:60] if issues else "unknown"

        m.record_pattern(
            pattern_type="refine_attempt",
            pattern_key=f"{top_issue}|{direction}",
            severity="info" if delta >= 0 else "medium",
            notes=f"{path} iter={iteration} Δ={delta:+.2f} ({before_score}→{after_score})",
        )
    except Exception:
        pass


def _record_strategy(path: str, iterations: int,
                     final_score: float, initial_score: float) -> None:
    """Record a successful refinement strategy in skills."""
    try:
        from memory.skills import SkillRegistry
        sr = SkillRegistry()
        ext = path.rsplit(".", 1)[-1].lower()
        skill_name = f"تحسين ملفات {ext.upper()}"
        delta = round(final_score - initial_score, 2)
        sr.add(
            name=skill_name,
            domain="media" if ext in ("html", "css") else "code",
            description=f"تحسين تكراري حتى درجة عالية",
            examples=[f"{path}: {initial_score}→{final_score} في {iterations} محاولة"],
            source="refiner",
        )
        sr.record_use(skill_name, success=(final_score >= 7.5),
                      quality=min(5.0, final_score / 2))
    except Exception:
        pass


# ═══════════════════════════════════════════════
# Single refinement pass
# ═══════════════════════════════════════════════

def refine_once(brain, path: str, critique: Dict[str, Any],
                verbose: bool = True) -> Dict[str, Any]:
    """One refinement pass based on a critique."""
    html = _read_file(path)
    if not html:
        return {"success": False, "error": "file unreadable"}

    issues = critique.get("issues") or []
    suggestions = critique.get("suggestions") or []

    # Fallback: if no issues and no suggestions, synthesize from low dimensions
    if not issues and not suggestions:
        dims = critique.get("dimensions") or {}
        for key, val in dims.items():
            if isinstance(val, (int, float)) and val < 8:
                issues.append(f"{key}: score {val}/10 — needs improvement")

    prompt = _build_refine_prompt(html, issues, suggestions)

    resp = brain.ask(
        prompt=prompt,
        content_class="standard",
        system=REFINER_SYSTEM,
        temperature=0.3,
    )

    if not resp.success:
        return {"success": False, "error": resp.error}

    new_html = _strip_fences(resp.text or "")
    if not new_html.strip():
        return {"success": False, "error": "empty response"}

    if "<!DOCTYPE html>" not in new_html.lower() and "<html" not in new_html.lower():
        return {"success": False, "error": "response is not HTML"}

    if not _write_file(path, new_html):
        return {"success": False, "error": "write failed"}

    return {
        "success": True,
        "bytes": len(new_html.encode("utf-8")),
        "provider": resp.provider,
        "model": resp.model,
        "latency_ms": resp.latency_ms,
    }


# ═══════════════════════════════════════════════
# Iterative refinement
# ═══════════════════════════════════════════════

def refine_until(brain, path: str,
                 target: float = 8.0,
                 max_iterations: int = 4,
                 verbose: bool = True) -> Dict[str, Any]:
    """
    Critique -> refine -> critique -> ... until target or max_iterations.

    Records every attempt in patterns + skills for Meta-Learner (future).
    """
    try:
        from brain.visual_critic import critique as run_critique
    except Exception as e:
        return {"success": False, "error": f"critic missing: {e}"}

    history: List[Dict[str, Any]] = []
    current = run_critique(brain, path, use_llm=True)
    initial_score = current.get("overall", 0)

    history.append({
        "iteration": 0,
        "score": initial_score,
        "static": current.get("static_score"),
        "llm": current.get("llm_score"),
        "issues_count": len(current.get("issues") or []),
    })

    if verbose:
        print(f"   🎨 محاولة 0: {initial_score}/10")

    if not current.get("ok"):
        return {"success": False, "error": "critique failed", "history": history}

    if initial_score >= target:
        return {
            "success": True, "reached_target": True, "iterations": 0,
            "initial_score": initial_score, "final_score": initial_score,
            "final_critique": current, "history": history,
        }

    # ── Loop ──
    for i in range(1, max_iterations + 1):
        before = current.get("overall", 0)
        if verbose:
            print(f"   🔧 تحسين {i}/{max_iterations}...")

        r = refine_once(brain, path, current, verbose=verbose)
        if not r.get("success"):
            if verbose:
                print(f"      ❌ {r.get('error')}")
            history.append({"iteration": i, "error": r.get("error")})
            break

        if verbose:
            print(f"      ✅ {r.get('bytes')} bytes — إعادة التقييم...")

        current = run_critique(brain, path, use_llm=True)
        after = current.get("overall", 0)

        # Record attempt (Meta-Learner hook)
        _record_attempt(path, i, before, after, current.get("issues") or [])

        history.append({
            "iteration": i,
            "score": after,
            "static": current.get("static_score"),
            "llm": current.get("llm_score"),
            "issues_count": len(current.get("issues") or []),
            "delta": round(after - before, 2),
        })

        if verbose:
            delta = after - before
            arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "=")
            print(f"      🎨 {after}/10 ({arrow} {abs(delta):.1f})")

        if after >= target:
            _record_strategy(path, i, after, initial_score)
            return {
                "success": True, "reached_target": True, "iterations": i,
                "initial_score": initial_score, "final_score": after,
                "final_critique": current, "history": history,
            }

    # Reached max without hitting target
    final_score = current.get("overall", 0)
    _record_strategy(path, max_iterations, final_score, initial_score)

    return {
        "success": True, "reached_target": False,
        "iterations": max_iterations,
        "initial_score": initial_score, "final_score": final_score,
        "final_critique": current, "history": history,
    }


def render_arabic(result: Dict[str, Any]) -> str:
    """Format the refinement report in Arabic."""
    if not result.get("ok", True):
        return f"❌ تعذّر التحسين: {result.get('error')}"

    reached = result.get("reached_target", False)
    initial = result.get("initial_score", 0)
    final = result.get("final_score", 0)
    iters = result.get("iterations", 0)

    if reached:
        header = f"🔧 التحسين الذاتي: {initial} → {final} في {iters} محاولة ✅"
    else:
        header = f"🔧 التحسين الذاتي: {initial} → {final} (لم يصل الهدف في {iters} محاولات) ⚠️"

    lines = [header]
    for h in result.get("history", []):
        i = h.get("iteration", "?")
        if "error" in h:
            lines.append(f"   {i}. ❌ {h['error']}")
        elif i == 0:
            lines.append(f"   {i}. البداية: {h.get('score')}/10")
        else:
            d = h.get("delta", 0)
            arrow = "↑" if d > 0 else ("↓" if d < 0 else "=")
            lines.append(f"   {i}. {h.get('score')}/10 ({arrow}{abs(d):.1f})")

    return "\n".join(lines)


# ═══════════════════════════════════════════════
# Self-test
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print("Refiner — module loaded (extension-ready)")
    print("Usage: refine_until(brain, path, target=8.0, max_iterations=4)")
    print()
    print("Learning hooks:")
    print("  • every attempt  -> memory.learning.patterns")
    print("  • every success  -> memory.skills")
    print("  • ready for Meta-Learner (future)")
