"""
brain/reflection.py
===================

Reflection loop for MOROAI.

After interactions, MOROAI analyzes what happened and extracts
a short lesson (a rule) saved to semantic memory. Before each new
request, MOROAI searches for similar lessons and injects them into
the system prompt.

To save quota, reflection is OFF by default. It runs when:
    - Owner types "/reflect" in CLI
    - Owner types "/reflect N" to reflect on last N episodes
    - Or automatically every 20 successful episodes (configurable)

Inspiration (no code copied):
    - Reflexion-Agent: Actor → Evaluator → Reflector loop
    - iLearn-Memory: dual memory + reflection
    - EvolveR (ICML 2026): abstract principle extraction
    - GenericAgent: crystallize each task into reusable skill
"""

import os
from typing import Optional, List, Dict, Any

from memory.learning import LearningMemory
from brain.identity import load_identity


REFLECTION_SYSTEM = """You are MOROAI's reflection module.

You analyze one interaction between the owner and MOROAI and extract
exactly ONE short, generalizable lesson (a rule) that MOROAI should
follow in similar future situations.

Rules for the lesson:
- Maximum 25 words.
- Must be a general rule, not a description of the specific request.
- Must be actionable (a "do X" or "avoid Y" style).
- Language: English for the rule (for indexing), even if interaction is Arabic.
- If nothing useful can be learned, respond with exactly: NONE

Output format (strict):
CATEGORY: <one of: style | code | research | safety | performance | general>
RULE: <the 25-word rule>
"""


class Reflector:
    def __init__(self, brain, memory: Optional[LearningMemory] = None):
        """
        brain: a MOROAI instance (used to call providers).
        memory: LearningMemory (shared instance preferred).
        """
        self.brain = brain
        self.memory = memory or LearningMemory()

    # -------- Public --------

    def reflect_on_episode(self, episode: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Analyze one episode and store a lesson. Returns the lesson dict or None."""
        prompt = episode.get("prompt", "")
        response = episode.get("response", "")
        success = bool(episode.get("success", 0))
        error = episode.get("error", "") or ""

        if not prompt or not response:
            return None

        # Build the reflection request
        user_text = f"""Owner asked:
{prompt}

MOROAI answered:
{response[:800]}

Outcome: {"SUCCESS" if success else "FAILURE"}
{"Error: " + error[:200] if error else ""}

Extract one generalizable lesson now.
"""

        # Call the model (small, cheap)
        resp = self.brain.ask(
            prompt=user_text,
            content_class="standard",
            system=REFLECTION_SYSTEM,
            temperature=0.2,
        )

        if not resp.success:
            return None

        lesson = self._parse(resp.text)
        if lesson is None:
            return None

        lid = self.memory.save_lesson(
            rule=lesson["rule"],
            category=lesson["category"],
            source_episode_id=episode.get("id"),
        )
        lesson["id"] = lid
        return lesson

    def reflect_last(self, n: int = 5) -> List[Dict[str, str]]:
        """Reflect on the last N episodes."""
        episodes = self._last_episodes(n)
        lessons = []
        for ep in episodes:
            lesson = self.reflect_on_episode(ep)
            if lesson:
                lessons.append(lesson)
        return lessons

    # -------- Internal --------

    def _last_episodes(self, n: int) -> List[Dict[str, Any]]:
        import sqlite3
        with sqlite3.connect(self.memory.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("""
                SELECT * FROM episodes
                ORDER BY id DESC
                LIMIT ?
            """, (n,))
            return [dict(r) for r in cur.fetchall()]

    def _parse(self, text: str) -> Optional[Dict[str, str]]:
        """Parse the strict output format."""
        if not text or "NONE" in text.upper()[:20]:
            return None

        category = "general"
        rule = ""

        for line in text.splitlines():
            line = line.strip()
            if line.upper().startswith("CATEGORY:"):
                category = line.split(":", 1)[1].strip().lower()
            elif line.upper().startswith("RULE:"):
                rule = line.split(":", 1)[1].strip()

        if not rule:
            return None

        # Clamp
        rule = rule[:200]
        if category not in {"style", "code", "research", "safety",
                            "performance", "general"}:
            category = "general"

        return {"rule": rule, "category": category}


# ============================================================
# Self-test (dry, no API call — only parser test)
# ============================================================

if __name__ == "__main__":
    class _FakeBrain:
        def ask(self, **kw):
            class R:
                success = True
                text = "CATEGORY: style\nRULE: Keep Arabic replies short and direct."
            return R()

    r = Reflector(_FakeBrain())
    parsed = r._parse("CATEGORY: style\nRULE: Keep Arabic replies short and direct.")
    print("Parsed:", parsed)
    assert parsed is not None
    assert parsed["category"] == "style"
    assert "short" in parsed["rule"]

    none_case = r._parse("NONE")
    print("NONE case:", none_case)
    assert none_case is None

    print("✅ Reflection parser OK.")
