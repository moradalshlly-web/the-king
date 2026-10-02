"""
brain/planner.py
================
Planner for MOROAI — breaks a natural language task into concrete steps.

Workflow:
    1. Read vision (memory/vision/) + project manifest
    2. Ask LLM to produce a structured plan (JSON)
    3. Validate, sanitize, and return

Output format:
{
    "task": "<original request>",
    "summary": "<one-line plan>",
    "steps": [
        {"n": 1, "action": "create", "path": "...", "description": "..."},
        {"n": 2, "action": "modify", "path": "...", "description": "..."},
    ],
    "reasoning": "<why this plan>"
}
"""

import json
import re
from typing import Dict, Any, Optional, List

try:
    from brain.core_paths import PROJECT_ROOT
except ImportError:
    import os
    PROJECT_ROOT = os.path.expanduser("~/moroai")


PLANNER_SYSTEM = """You are MOROAI's Planner — the architect.

You receive a natural-language request and produce a CONCRETE, ORDERED plan.

Rules:
1. Break the task into 3-10 small steps.
2. Each step MUST have: action ("create" | "modify" | "delete"), path (relative), description (1 sentence).
3. Prefer small files (< 200 lines each).
4. NEVER plan to modify protected files: cli.py, brain/core.py, brain/evolve.py, brain/prime_directives.py, brain/identity.py, brain/owner_profile.py.
5. If the request is unclear, ask ONE clarifying question (with action="ask").
6. Output valid JSON only. No markdown fences. No extra text.

OUTPUT FORMAT (strict):
{
  "summary": "one-line summary of the plan",
  "steps": [
    {"n": 1, "action": "create", "path": "path/to/file.ext", "description": "what this step does"},
    ...
  ],
  "reasoning": "why this plan (1-2 sentences)"
}

If you need clarification:
{
  "summary": "need clarification",
  "steps": [{"n": 1, "action": "ask", "path": "", "description": "the question"}],
  "reasoning": "why we need this"
}
"""


PROTECTED = {
    "cli.py",
    "brain/core.py",
    "brain/evolve.py",
    "brain/prime_directives.py",
    "brain/identity.py",
    "brain/owner_profile.py",
    "brain/planner.py",
}


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
    """Try hard to parse JSON from LLM output."""
    if not text:
        return None
    cleaned = _strip_fences(text)

    # Direct parse
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # Find first { ... last }
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start:end+1])
        except Exception:
            pass

    return None


def _validate_plan(plan: dict) -> Dict[str, Any]:
    """Normalize and validate."""
    if not isinstance(plan, dict):
        return {"success": False, "error": "plan is not a dict"}

    steps_in = plan.get("steps") or []
    if not isinstance(steps_in, list):
        return {"success": False, "error": "steps must be a list"}

    clean_steps = []
    for i, s in enumerate(steps_in, 1):
        if not isinstance(s, dict):
            continue
        action = (s.get("action") or "").strip().lower()
        path = (s.get("path") or "").strip()
        desc = (s.get("description") or "").strip()

        if action == "ask":
            clean_steps.append({
                "n": i, "action": "ask", "path": "",
                "description": desc or "توضيح مطلوب",
            })
            continue

        if action not in ("create", "modify", "delete"):
            continue
        if not path:
            continue

        # Safety: protect core files
        if path in PROTECTED and action in ("modify", "delete"):
            continue

        clean_steps.append({
            "n": i, "action": action, "path": path,
            "description": desc[:200],
        })

    if not clean_steps:
        return {"success": False, "error": "no valid steps"}

    return {
        "success": True,
        "summary": (plan.get("summary") or "")[:200],
        "steps": clean_steps,
        "reasoning": (plan.get("reasoning") or "")[:500],
    }


def plan(brain, task: str, context: str = "",
         max_steps: int = 10,
         temperature: float = 0.3) -> Dict[str, Any]:
    """
    Produce a plan for the given task.

    brain   : MOROAI instance
    task    : natural language request
    context : optional extra context (e.g., current file list)
    """
    if not task or not task.strip():
        return {"success": False, "error": "empty task"}

    # Gather project context
    manifest_summary = ""
    try:
        from brain.project_scanner import scan_project
        m = scan_project()
        dirs = m.get("directories", {})
        parts = [f"Project has {m['total_files']} files ({m['total_bytes']//1024} KB)."]
        for d, files in dirs.items():
            parts.append(f"  {d}/: {len(files)} files")
        manifest_summary = "\n".join(parts)
    except Exception:
        pass

    # Vision (short)
    vision_short = ""
    try:
        from brain.vision import load_vision
        v = load_vision()
        mission = (v.get("mission") or "")[:400]
        if mission:
            vision_short = "MISSION (short):\n" + mission
    except Exception:
        pass

    # Top-level folders (grounding for file paths)
    top_folders = ""
    try:
        from brain.project_scanner import scan_project
        m2 = scan_project()
        dirs = sorted(m2.get("directories", {}).keys())
        top_folders = ", ".join(dirs)
    except Exception:
        top_folders = "brain, tools, providers, memory, web_new, config"

    user_prompt = f"""TASK (from owner, could be Arabic or English):
{task.strip()}

CURRENT PROJECT:
{manifest_summary}

TOP-LEVEL FOLDERS (use these as the base for new paths):
{top_folders}

IMPORTANT RULES:
- New website files should go under "web_new/" (not "web/").
- New tools under "tools/".
- New brain modules under "brain/".
- Reuse existing folders; do not invent new top-level ones.

{vision_short}

{context}

Produce the plan as JSON only."""

    resp = brain.ask(
        prompt=user_prompt,
        content_class="standard",
        system=PLANNER_SYSTEM,
        temperature=temperature,
    )

    if not resp.success:
        return {"success": False, "error": resp.error or "LLM failed"}

    raw = resp.text or ""
    parsed = _extract_json(raw)
    if not parsed:
        return {
            "success": False,
            "error": "could not parse JSON from LLM output",
            "raw": raw[:800],
        }

    validated = _validate_plan(parsed)
    validated["task"] = task
    validated["provider"] = resp.provider
    validated["model"] = resp.model
    validated["latency_ms"] = resp.latency_ms
    return validated


# ═══════════════════════════════════════════════
# Self-test (no API call)
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print("Planner module loaded.")
    print()
    # Test JSON extraction
    samples = [
        '{"summary":"x","steps":[{"n":1,"action":"create","path":"a.py","description":"d"}],"reasoning":"r"}',
        '```json\n{"summary":"x","steps":[{"n":1,"action":"create","path":"a.py","description":"d"}],"reasoning":"r"}\n```',
        'Some text\n{"summary":"x","steps":[{"n":1,"action":"create","path":"a.py","description":"d"}],"reasoning":"r"}\nmore',
    ]
    for i, s in enumerate(samples, 1):
        r = _extract_json(s)
        print(f"  Sample {i}: {'✅' if r else '❌'}")
        if r:
            v = _validate_plan(r)
            print(f"    → valid={v.get('success')}, steps={len(v.get('steps', []))}")
