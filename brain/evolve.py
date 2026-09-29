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
from tools.file_ops import FileOps


EVOLVE_SYSTEM = """You are MOROAI's evolution engine.

PROJECT STRUCTURE (Python project, not web):
- brain/        : core logic
- providers/    : AI provider adapters
- tools/        : tools for the LLM
- memory/       : persistence
- web/          : Flask API
- config/       : settings
- cli.py        : terminal interface

NEVER create files in src/ or commands/.
New files MUST go into: brain/, providers/, tools/, memory/, or web/.

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


class EvolveEngine:
    def __init__(self, brain):
        self.brain = brain
        self.file_ops = FileOps()

    # -------- Propose --------

    def propose(self) -> Optional[Dict[str, str]]:
        """Ask the LLM for the next evolution step."""
        v = load_vision()
        caps = v.get("capabilities", "")
        gaps = v.get("gaps", "")
        roadmap = v.get("roadmap", "")

        prompt = f"""Current capabilities:
{caps}

Known gaps:
{gaps}

Roadmap:
{roadmap}

Based on the above, propose the SINGLE most important next step.
Output in the required format."""

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
        if not target or not desc:
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
