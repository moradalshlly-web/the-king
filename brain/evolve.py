"""
brain/evolve.py
===============

Self-evolution engine for MOROAI.

Reads the vision, analyzes the current state, proposes the next
evolution step, executes it in an isolated workspace, and presents
the result for owner approval.

Flow:
    1. READ    : load vision files
    2. ANALYZE : compare vision vs capabilities
    3. PROPOSE : ask LLM for the next concrete step
    4. EXECUTE : generate the artifact in a workspace
    5. TEST    : verify
    6. PRESENT : show to owner for approval
    7. MERGE   : apply if approved
"""

import os
from typing import Dict, Optional, Any

from brain.vision import vision_prompt, load_vision
from brain.project_scanner import manifest_prompt
from tools.file_ops import FileOps


# Core files that /evolve must NOT overwrite unless action == "modify"
PROTECTED_FILES = {
    "brain/evolve.py",
    "brain/core.py",
    "brain/prime_directives.py",
    "brain/identity.py",
    "brain/owner_profile.py",
    "brain/vision.py",
    "cli.py",
    "web/server.py",
}


EVOLVE_SYSTEM = """You are MOROAI's evolution engine.

PROJECT STRUCTURE (Python project, NOT web):
- brain/        : core logic (core.py, evolve.py, reflection.py, vision.py)
- providers/    : AI provider adapters
- tools/        : tools for the LLM
- memory/       : persistence
- web/          : Flask API
- config/       : settings
- cli.py        : terminal interface

ABSOLUTE RULES:
1. NEVER propose files under src/, commands/, or any path not listed above.
2. New files MUST go into: brain/, tools/, providers/, memory/, or web/.
3. Prefer small files (under 200 lines).
4. Do not duplicate existing functionality.


You read MOROAI's vision and current capabilities, then propose ONE
concrete, small, achievable step toward the vision.

Rules:
- The step must be small enough to complete in one workspace session.
- It must add a real capability, not just documentation.
- It must respect all prime directives (D1-D7).
- Output the step in this EXACT format:

STEP_TITLE: <short title>
TARGET_FILE: <relative path inside project>
ACTION: <one of: create | modify>
DESCRIPTION: <2-3 sentence explanation of what to build>

Do NOT write code yet. Only the plan.
If nothing should be built, respond with: NONE
"""

GENERATOR_SYSTEM = """You are MOROAI's code generator.

You receive a plan for a single file and produce its COMPLETE content.

Strict rules:
- Output ONLY the raw file content.
- Do NOT wrap in markdown fences.
- Do NOT add explanations.
- The file must be complete, working, and self-contained.
- Follow the existing code style of MOROAI.
"""


def _read_latest_reports(limit: int = 3) -> str:
    """
    Read the latest reports from project_analyzer.
    Priority: local files first. If none found, read from cloud.
    """
    import os
    try:
        from brain.core_paths import PROJECT_ROOT
    except ImportError:
        PROJECT_ROOT = os.path.expanduser("~/moroai")

    reports_dir = os.path.join(PROJECT_ROOT, "memory", "workspace", "analyzer")

    # ─── Try local first ───
    parts = []
    if os.path.isdir(reports_dir):
        try:
            files = [
                os.path.join(reports_dir, f)
                for f in os.listdir(reports_dir)
                if f.endswith(".md")
            ]
            files.sort(key=os.path.getmtime, reverse=True)
            files = files[:limit]

            for fp in files:
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        parts.append(f.read()[:3000])
                except Exception:
                    pass
        except Exception:
            pass

    # ─── If local is empty, try cloud ───
    if not parts:
        try:
            from tools.cloud_memory import list_reports, download_report
            listing = list_reports()
            if listing.get("success") and listing.get("files"):
                # get the latest (they are already sorted by HF)
                cloud_files = sorted(listing["files"], reverse=True)[:limit]
                for remote_path in cloud_files:
                    try:
                        r = download_report(remote_path)
                        if r.get("success"):
                            with open(r["local_path"], "r", encoding="utf-8") as f:
                                parts.append(f.read()[:3000])
                    except Exception:
                        pass
        except Exception:
            pass

    return "\n\n---\n\n".join(parts)


class EvolveEngine:
    def __init__(self, brain):
        self.brain = brain
        self.file_ops = FileOps()

    # -------- Propose --------

    def propose(self) -> Optional[Dict[str, str]]:
        """Ask the LLM for the next evolution step."""
        vision = vision_prompt()
        manifest = manifest_prompt()
        reports = _read_latest_reports(limit=3)

        prompt = (
            "=== MOROAI VISION (all 7 files) ===\n"
            + vision
            + "\n\n=== CURRENT PROJECT FILES (what already exists) ===\n"
            + manifest
        )

        if reports:
            prompt += (
                "\n\n=== RECENT OPEN-SOURCE ANALYSIS REPORTS ===\n"
                + reports
                + "\n\nUse these reports to ground your proposal in real projects.\n"
            )

        prompt += (
            "\n\nBased on the above:\n"
            + "1. Identify the SINGLE most important next step toward the vision.\n"
            + "2. BEFORE proposing to CREATE a file, check the manifest above.\n"
            + "3. If the target file already exists, use action=modify.\n"
            + "4. If it does not exist, use action=create.\n"
            + "5. If a recent analysis report is relevant, mention the project by name.\n"
            + "\nOutput in the required format."
        )

        resp = self.brain.ask(
            prompt=prompt,
            content_class="standard",
            system=EVOLVE_SYSTEM,
            temperature=0.4,
        )
        if not resp.success:
            return None

        return self._parse_plan(resp.text)

    # -------- Generate --------

    def generate(self, plan: Dict[str, str]) -> Optional[str]:
        """Generate the content of the target file."""
        target = plan.get("target_file", "")
        desc = plan.get("description", "")
        action = plan.get("action", "create").lower()
        if not target or not desc:
            return None

        # Refuse to overwrite protected files unless action == "modify"
        if target in PROTECTED_FILES and action != "modify":
            print(f"[evolve] BLOCKED: '{target}' is protected. Use action=modify.")
            return None

        prompt = f"""Target file: {target}
Purpose: {desc}

Generate the complete content of this file now."""

        resp = self.brain.ask(
            prompt=prompt,
            content_class="standard",
            system=GENERATOR_SYSTEM,
            temperature=0.4,
        )
        if not resp.success:
            return None

        return self._strip_fences(resp.text)

    # -------- Parser --------

    def _parse_plan(self, text: str) -> Optional[Dict[str, str]]:
        if not text or "NONE" in text.upper()[:30]:
            return None
        plan = {}
        for line in text.splitlines():
            line = line.strip()
            for key in ("STEP_TITLE", "TARGET_FILE", "ACTION", "DESCRIPTION"):
                if line.upper().startswith(key + ":"):
                    plan[key.lower()] = line.split(":", 1)[1].strip()
        if "target_file" not in plan:
            return None
        return plan

    def _strip_fences(self, text: str) -> str:
        if not text:
            return text
        t = text.strip()
        if t.startswith("```"):
            # remove first line
            lines = t.split("\n")
            if len(lines) > 1:
                t = "\n".join(lines[1:])
            # remove closing fence
            if t.rstrip().endswith("```"):
                t = t.rstrip()[:-3].rstrip()
        return t + "\n" if not t.endswith("\n") else t


if __name__ == "__main__":
    print("EvolveEngine module loaded.")
    print("Classes:", EvolveEngine)
