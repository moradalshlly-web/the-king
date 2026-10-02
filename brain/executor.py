"""
brain/executor.py
=================
Executor for MOROAI — turns a plan into concrete files.

Flow:
    1. validate_plan()    -> rejects bad plans before spending tokens
    2. execute_plan()     -> runs each step via Builder
    3. verify + monitor   -> deterministic_verifier + code_monitor
    4. repair_loop        -> fixes broken files (up to 3 attempts)
    5. returns a structured report
"""

import os
from datetime import datetime
from typing import Dict, Any, List, Optional

try:
    from brain.core_paths import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = os.path.expanduser("~/moroai")


# ───────────────────────────────────────────────
# Plan validation (no LLM)
# ───────────────────────────────────────────────

ALLOWED_ACTIONS = {"create", "modify", "delete"}
ALLOWED_FOLDERS = {"brain", "tools", "providers", "memory", "web_new", "config"}

PROTECTED = {
    "cli.py",
    "brain/core.py",
    "brain/evolve.py",
    "brain/prime_directives.py",
    "brain/identity.py",
    "brain/owner_profile.py",
    "brain/planner.py",
    "brain/executor.py",
}


def _first_folder(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else ""


def validate_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate a plan before execution.
    Returns {ok: bool, errors: [...], warnings: [...]}.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(plan, dict):
        return {"ok": False, "errors": ["plan is not a dict"], "warnings": []}

    steps = plan.get("steps") or []
    if not isinstance(steps, list) or not steps:
        return {"ok": False, "errors": ["plan has no steps"], "warnings": []}

    seen_paths = set()
    creates = set()

    for s in steps:
        if not isinstance(s, dict):
            continue
        action = (s.get("action") or "").lower()
        path = (s.get("path") or "").strip()

        if action == "ask":
            continue  # handled by caller

        if action not in ALLOWED_ACTIONS:
            errors.append(f"invalid action: {action}")
            continue

        if not path:
            errors.append("empty path")
            continue

        # folder check
        folder = _first_folder(path)
        if folder and folder not in ALLOWED_FOLDERS:
            errors.append(f"unknown folder '{folder}' in {path}")

        # protected check
        if path in PROTECTED and action in ("modify", "delete"):
            errors.append(f"protected file: {path}")

        # duplicates
        if path in seen_paths:
            warnings.append(f"path used twice: {path}")
        seen_paths.add(path)

        if action == "create":
            creates.add(path)

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


# ───────────────────────────────────────────────
# Single-step execution
# ───────────────────────────────────────────────

def _run_one_step(brain, builder, step: Dict[str, Any],
                  verbose: bool = True) -> Dict[str, Any]:
    """Execute one step. Returns a result dict."""
    action = step.get("action", "create")
    path = step.get("path", "")
    desc = step.get("description", "")

    result = {
        "n": step.get("n"),
        "action": action,
        "path": path,
        "success": False,
        "stage": "start",
        "content_bytes": 0,
        "verification": None,
        "monitor": None,
        "repair": None,
        "error": None,
    }

    if action == "ask":
        result["error"] = "step requires clarification"
        return result

    if action == "delete":
        try:
            full = os.path.join(PROJECT_ROOT, path)
            if os.path.isfile(full):
                os.remove(full)
                result["success"] = True
                result["stage"] = "deleted"
            else:
                result["error"] = "file not found"
        except Exception as e:
            result["error"] = str(e)
        return result

    # ── Generate + Write ──
    try:
        if verbose:
            print(f"   📝 [{action}] {path}")
        gen = builder.generate(path, desc)
        if not gen.get("success"):
            result["error"] = gen.get("error", "generate failed")
            result["stage"] = "generate"
            return result

        content = gen.get("content", "")
        result["content_bytes"] = len(content.encode("utf-8"))

        w = builder.write(path, content)
        if not w.get("success"):
            result["error"] = w.get("error", "write failed")
            result["stage"] = "write"
            return result

        result["stage"] = "written"
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        return result

    # ── Verify ──
    try:
        from tools.deterministic_verifier import verify_file
        v = verify_file(path, save=True)
        result["verification"] = {
            "passed": v.get("passed"),
            "score": v.get("score"),
            "failed": v.get("failed_checks", []),
        }
    except Exception:
        pass

    # ── Monitor ──
    try:
        from brain.code_monitor import inspect_file
        m = inspect_file(path, save=True)
        result["monitor"] = {
            "verdict": m.get("verdict"),
            "issues": m.get("issue_count"),
        }
    except Exception:
        pass

    # ── Repair if verifier failed ──
    if result["verification"] and not result["verification"].get("passed"):
        try:
            from brain.repair_loop import repair_file
            if verbose:
                print(f"   🔧 محاولة إصلاح...")
            r = repair_file(brain, path, original_prompt=desc, max_attempts=3)
            result["repair"] = {
                "success": r.get("success"),
                "attempts": r.get("attempts"),
                "final_score": r.get("final_score"),
            }
            if r.get("success"):
                result["verification"]["passed"] = True
                result["verification"]["score"] = r.get("final_score")
        except Exception:
            pass

    # final success = verify passed (after any repair)
    if result["verification"] is None:
        result["success"] = True  # no verifier available -> assume ok
    else:
        result["success"] = bool(result["verification"].get("passed"))

    result["stage"] = "done"
    return result


# ───────────────────────────────────────────────
# Plan execution
# ───────────────────────────────────────────────

def execute_plan(brain, plan: Dict[str, Any],
                 max_steps: int = 12,
                 verbose: bool = True) -> Dict[str, Any]:
    """
    Execute a plan end-to-end.
    Returns a structured report.
    """
    started = datetime.now()

    # 1. validate
    val = validate_plan(plan)
    if not val["ok"]:
        return {
            "success": False,
            "stage": "validation",
            "errors": val["errors"],
            "warnings": val["warnings"],
            "started": started.isoformat(),
        }

    steps = plan.get("steps") or []
    if len(steps) > max_steps:
        steps = steps[:max_steps]

    # 2. builder
    try:
        from brain.builder import Builder
        builder = Builder(brain)
    except Exception as e:
        return {"success": False, "stage": "builder_init", "error": str(e)}

    # 3. execute
    if verbose:
        print(f"🚀 تنفيذ الخطة ({len(steps)} خطوة)...")
        print()

    results = []
    for step in steps:
        r = _run_one_step(brain, builder, step, verbose=verbose)
        results.append(r)

        if not r["success"]:
            if verbose:
                print(f"      ❌ فشل: {r.get('error') or 'verification failed'}")
        else:
            if verbose:
                v = r.get("verification") or {}
                mark = "✅" if v.get("passed", True) else "⚠️"
                extra = f" (score={v.get('score')})" if v.get("score") is not None else ""
                print(f"      {mark} تم{extra}")

        # stop on "ask"
        if step.get("action") == "ask":
            break

    elapsed = (datetime.now() - started).total_seconds()

    # 4. summary
    ok_steps = sum(1 for r in results if r["success"])
    failed_steps = [r for r in results if not r["success"]]

    return {
        "success": len(failed_steps) == 0,
        "stage": "done",
        "summary": plan.get("summary", ""),
        "steps_total": len(results),
        "steps_ok": ok_steps,
        "steps_failed": len(failed_steps),
        "results": results,
        "elapsed_seconds": round(elapsed, 2),
        "started": started.isoformat(),
        "warnings": val["warnings"],
    }


# ═══════════════════════════════════════════════
# Self-test (no LLM)
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print("Executor module — validation self-test")
    print("=" * 55)

    good_plan = {
        "summary": "test",
        "steps": [
            {"n": 1, "action": "create", "path": "web_new/test.html", "description": "x"},
            {"n": 2, "action": "create", "path": "tools/helper.py", "description": "y"},
        ],
    }
    bad_plan_1 = {
        "steps": [
            {"n": 1, "action": "create", "path": "random_folder/x.py", "description": "z"},
        ],
    }
    bad_plan_2 = {
        "steps": [
            {"n": 1, "action": "modify", "path": "brain/core.py", "description": "no"},
        ],
    }

    for name, p in [("good", good_plan), ("bad_folder", bad_plan_1), ("protected", bad_plan_2)]:
        v = validate_plan(p)
        print(f"  {name}: ok={v['ok']}")
        for e in v["errors"]:
            print(f"     ❌ {e}")
        for w in v["warnings"]:
            print(f"     ⚠️  {w}")
