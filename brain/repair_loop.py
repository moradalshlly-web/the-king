"""
brain/repair_loop.py
====================
Self-repair loop for MOROAI.

Workflow:
    1. Verify the file
    2. If broken, ask MOROAI to fix it (targeted repair)
    3. Verify again
    4. Up to 3 attempts
    5. Record all attempts in learning.db
"""

import os
from typing import Dict, Any, Optional

try:
    from brain.core_paths import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = os.path.expanduser("~/moroai")


REPAIR_SYSTEM = """You are MOROAI's file repair specialist.

The user will give you:
    - The current content of a file
    - A list of specific errors found by an automated verifier

Your task:
    - Output ONLY the corrected file content.
    - Do NOT wrap in markdown fences.
    - Do NOT add explanations.
    - Change ONLY what is necessary to fix the reported errors.
    - Keep everything else exactly as it was.
"""


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
    return t + "\n" if not t.endswith("\n") else t


def repair_file(brain, path: str, original_prompt: str = "",
                max_attempts: int = 3,
                on_attempt=None) -> Dict[str, Any]:
    """
    Try to make 'path' pass the deterministic verifier.

    brain         : a MOROAI instance (for calling LLM)
    path          : project-relative path
    original_prompt : the user's original request (context)
    max_attempts  : maximum repair attempts
    on_attempt    : optional callback(attempt, verification) for progress

    Returns:
        {
          success: bool,
          attempts: int,
          final_score: float,
          final_passed: bool,
          history: [...],
        }
    """
    try:
        from tools.deterministic_verifier import verify_file
    except Exception as e:
        return {"success": False, "error": f"verifier missing: {e}", "attempts": 0}

    history = []

    # First check (attempt 0 — before any repair)
    v0 = verify_file(path, save=True)
    history.append({"attempt": 0, "passed": v0.get("passed"), "score": v0.get("score"),
                    "failed": v0.get("failed_checks", [])})

    if on_attempt:
        try:
            on_attempt(0, v0)
        except Exception:
            pass

    if v0.get("passed"):
        return {
            "success": True,
            "attempts": 0,
            "final_score": v0.get("score"),
            "final_passed": True,
            "history": history,
        }

    # Repair attempts
    for attempt in range(1, max_attempts + 1):
        content = _read_file(path)
        if content is None:
            return {"success": False, "error": "file vanished", "attempts": attempt,
                    "history": history}

        failed_checks = ", ".join(v0.get("failed_checks", []) or ["unknown"])

        repair_prompt = (
            "الملف الحالي:\n\n"
            "-----BEGIN FILE-----\n"
            + content[:8000]
            + "\n-----END FILE-----\n\n"
            "الأخطاء التي اكتشفها المدقق الآلي:\n"
            f"  {failed_checks}\n\n"
            "سياق الطلب الأصلي:\n"
            f"  {original_prompt[:500] if original_prompt else '(غير متوفر)'}\n\n"
            "أصلح الملف بأقل تغييرات ممكنة، وأخرج الملف كاملاً فقط."
        )

        resp = brain.ask(
            prompt=repair_prompt,
            content_class="standard",
            system=REPAIR_SYSTEM,
            temperature=0.2,
        )

        if not resp.success:
            history.append({"attempt": attempt, "passed": False,
                            "score": 0.0, "failed": ["llm_error"],
                            "error": resp.error})
            continue

        new_content = _strip_fences(resp.text or "")
        if not new_content.strip():
            history.append({"attempt": attempt, "passed": False,
                            "score": 0.0, "failed": ["empty_output"]})
            continue

        if not _write_file(path, new_content):
            history.append({"attempt": attempt, "passed": False,
                            "score": 0.0, "failed": ["write_error"]})
            break

        # Verify again
        v = verify_file(path, save=True)
        history.append({
            "attempt": attempt,
            "passed": v.get("passed"),
            "score": v.get("score"),
            "failed": v.get("failed_checks", []),
        })

        if on_attempt:
            try:
                on_attempt(attempt, v)
            except Exception:
                pass

        if v.get("passed"):
            # Record the success pattern
            try:
                from memory.learning import LearningMemory
                m = LearningMemory()
                m.record_pattern(
                    pattern_type="repair_success",
                    pattern_key=f"attempt_{attempt}",
                    severity="info",
                    notes=f"نُجح الإصلاح بعد {attempt} محاولة",
                )
            except Exception:
                pass

            return {
                "success": True,
                "attempts": attempt,
                "final_score": v.get("score"),
                "final_passed": True,
                "history": history,
            }

        # Update v0 for the next round
        v0 = v

    # All attempts failed
    try:
        from memory.learning import LearningMemory
        m = LearningMemory()
        m.record_pattern(
            pattern_type="repair_failure",
            pattern_key=",".join(v0.get("failed_checks", []) or ["unknown"]),
            severity="high",
            notes=f"فشل الإصلاح بعد {max_attempts} محاولات",
        )
    except Exception:
        pass

    return {
        "success": False,
        "attempts": max_attempts,
        "final_score": v0.get("score"),
        "final_passed": False,
        "history": history,
    }


# ═══════════════════════════════════════════════
# Self-test
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print("repair_loop module loaded.")
    print("Usage: repair_file(brain, path, original_prompt, max_attempts=3)")
