"""
memory/skills.py
================
Skill registry for MOROAI.

A "skill" is a durable capability MOROAI has learned,
distinct from a "pattern" (which is just a repeated observation).

Skill shape:
    - name        : "تحليل الروايات العربية"
    - domain      : arabic | code | media | reasoning | tool | general
    - level       : beginner | intermediate | advanced | expert
    - description : short text
    - examples    : list of concrete examples
    - source      : where it came from
    - stats       : times_used, times_succeeded, avg_quality
"""

import os
import json
import sqlite3
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional


DB_FILE = os.path.join(os.path.dirname(__file__), "data", "learning.db")


SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'beginner',
    description TEXT,
    examples TEXT,
    source TEXT,
    times_used INTEGER DEFAULT 0,
    times_succeeded INTEGER DEFAULT 0,
    avg_quality REAL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_used_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_skill_domain ON skills(domain);
CREATE INDEX IF NOT EXISTS idx_skill_level ON skills(level);
CREATE INDEX IF NOT EXISTS idx_skill_used ON skills(last_used_at);
"""


LEVELS = ["beginner", "intermediate", "advanced", "expert"]
LEVEL_THRESHOLDS = {
    # (min_successes, min_quality) -> level
    "expert":       (30, 4.0),
    "advanced":     (15, 3.5),
    "intermediate": (5,  3.0),
    "beginner":     (0,  0.0),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_level(successes: int, avg_quality: float) -> str:
    for lvl in ("expert", "advanced", "intermediate", "beginner"):
        s, q = LEVEL_THRESHOLDS[lvl]
        if successes >= s and avg_quality >= q:
            return lvl
    return "beginner"


class SkillRegistry:

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DB_FILE
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    # -------- Add / update --------

    def add(self, name: str, domain: str = "general",
            description: str = "",
            examples: Optional[List[str]] = None,
            source: str = "manual") -> Optional[int]:
        """Add a new skill (or return existing id)."""
        if not name or not name.strip():
            return None
        n = name.strip()
        d = (domain or "general").strip().lower()[:40]
        desc = (description or "").strip()[:600]
        ex_json = json.dumps(examples or [], ensure_ascii=False)
        now = _now()

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id FROM skills WHERE name=?", (n,)
            ).fetchone()
            if row:
                conn.execute(
                    """UPDATE skills
                       SET description=?, examples=?, domain=?, last_used_at=?
                       WHERE id=?""",
                    (desc, ex_json, d, now, row[0]),
                )
                conn.commit()
                return row[0]
            cur = conn.execute(
                """INSERT INTO skills
                   (name, domain, level, description, examples, source,
                    created_at, last_used_at)
                   VALUES (?, ?, 'beginner', ?, ?, ?, ?, ?)""",
                (n, d, desc, ex_json, source, now, now),
            )
            conn.commit()
            return cur.lastrowid

    def record_use(self, name: str, success: bool,
                   quality: float = 0.0) -> Optional[int]:
        """Record one use of a skill. Auto-upgrades level."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, times_used, times_succeeded, avg_quality FROM skills WHERE name=?",
                (name,),
            ).fetchone()
            if not row:
                return None
            sid, used, succ, avg_q = row
            new_used = used + 1
            new_succ = succ + (1 if success else 0)

            # Weighted moving average for quality
            try:
                q = max(0.0, min(5.0, float(quality)))
            except (TypeError, ValueError):
                q = 0.0
            if used == 0:
                new_avg_q = q
            else:
                new_avg_q = (avg_q * used + q) / new_used

            new_level = _compute_level(new_succ, new_avg_q)

            conn.execute(
                """UPDATE skills
                   SET times_used=?, times_succeeded=?, avg_quality=?,
                       level=?, last_used_at=?
                   WHERE id=?""",
                (new_used, new_succ, round(new_avg_q, 3),
                 new_level, _now(), sid),
            )
            conn.commit()
            return sid

    # -------- Query --------

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM skills WHERE name=?", (name,)
            ).fetchone()
            return dict(row) if row else None

    def search(self, query: str = "", domain: Optional[str] = None,
               limit: int = 20) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            q = (query or "").strip()
            where = []
            params: List[Any] = []
            if q:
                where.append("(name LIKE ? OR description LIKE ? OR examples LIKE ?)")
                params += [f"%{q}%", f"%{q}%", f"%{q}%"]
            if domain:
                where.append("domain = ?")
                params.append(domain.lower())
            sql = "SELECT * FROM skills"
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY times_succeeded DESC, times_used DESC LIMIT ?"
            params.append(limit)
            cur = conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def top(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Top skills by level then successes."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("""
                SELECT * FROM skills
                ORDER BY
                    CASE level
                        WHEN 'expert' THEN 4
                        WHEN 'advanced' THEN 3
                        WHEN 'intermediate' THEN 2
                        ELSE 1
                    END DESC,
                    times_succeeded DESC
                LIMIT ?
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]

    def stats(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
            by_domain = conn.execute(
                "SELECT domain, COUNT(*) FROM skills GROUP BY domain ORDER BY 2 DESC"
            ).fetchall()
            by_level = conn.execute(
                "SELECT level, COUNT(*) FROM skills GROUP BY level"
            ).fetchall()
        return {
            "total": total,
            "by_domain": [{"domain": d, "count": c} for d, c in by_domain],
            "by_level": {lvl: c for lvl, c in by_level},
        }

    # -------- Context for Planner --------

    def relevant_for(self, task_text: str, limit: int = 5) -> str:
        """
        Build a short Arabic text describing skills relevant to a task.
        Used to enrich the Planner's prompt.
        """
        if not task_text:
            return ""
        # Find by keywords
        hits = self.search(task_text, limit=limit)
        if not hits:
            # Fallback to top skills
            hits = self.top(limit=3)
        if not hits:
            return ""

        lines = ["المهارات ذات الصلة (من تجاربي السابقة):"]
        for h in hits[:limit]:
            lvl_ar = {
                "beginner": "مبتدئ",
                "intermediate": "متوسط",
                "advanced": "متقدم",
                "expert": "خبير",
            }.get(h.get("level", "beginner"), h.get("level"))
            lines.append(
                f"  • {h['name']} [{lvl_ar}] "
                f"(استُخدمت {h.get('times_used', 0)} مرة، "
                f"نجحت {h.get('times_succeeded', 0)})"
            )
        return "\n".join(lines)

    # -------- Auto-extract from execution report --------

    def learn_from_execution(self, plan: Dict[str, Any],
                             report: Dict[str, Any],
                             source: str = "tri-brain") -> List[str]:
        """
        Given a successful plan + report, register/increment skills.
        Returns the list of skill names touched.
        """
        touched: List[str] = []
        if not plan or not report:
            return touched

        steps = plan.get("steps") or []
        results = report.get("results") or []
        task_summary = (plan.get("summary") or "").strip()

        for i, step in enumerate(steps):
            if i >= len(results):
                break
            r = results[i]
            action = step.get("action", "")
            path = step.get("path", "")
            success = bool(r.get("success"))

            # Derive a skill name from path + action
            ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            domain = self._domain_from_path(path)
            skill_name = self._skill_name(action, ext, domain)
            if not skill_name:
                continue

            self.add(
                name=skill_name,
                domain=domain,
                description=f"أداء {action} لملفات {ext or 'عامة'}",
                examples=[task_summary or path] if task_summary else [path],
                source=source,
            )
            self.record_use(skill_name, success, quality=5.0 if success else 1.0)
            touched.append(skill_name)

        return touched

    def _domain_from_path(self, path: str) -> str:
        p = (path or "").lower()
        if p.startswith("web_new/") or any(p.endswith(x) for x in (".html", ".css", ".js")):
            return "media"
        if p.startswith("tools/"):
            return "tool"
        if p.startswith("brain/"):
            return "code"
        if p.endswith(".py"):
            return "code"
        if p.startswith("memory/"):
            return "memory"
        return "general"

    def _skill_name(self, action: str, ext: str, domain: str) -> str:
        if not action or not ext:
            return ""
        action_ar = {
            "create": "إنشاء",
            "modify": "تعديل",
            "delete": "حذف",
        }.get(action, action)
        ext_ar = {
            "py": "Python",
            "html": "HTML",
            "css": "CSS",
            "js": "JavaScript",
            "md": "Markdown",
            "json": "JSON",
        }.get(ext, ext.upper())
        return f"{action_ar} ملفات {ext_ar}"


# ═══════════════════════════════════════════════
# Self-test
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    s = SkillRegistry()
    print("Skill Registry — self-test")
    print("=" * 55)

    # Add sample skills
    s.add("تحليل الروايات العربية", "arabic",
          "استخراج الشخصيات والأماكن من الروايات",
          ["رواية أطلال الياقوت"], "manual")
    s.add("إنشاء ملفات Python", "code",
          "كتابة ملفات Python نظيفة مع shebang",
          ["tools/greeting.py"], "tri-brain")

    # Simulate uses
    for i in range(6):
        s.record_use("تحليل الروايات العربية", True, quality=4.5)
    for i in range(3):
        s.record_use("إنشاء ملفات Python", True, quality=5.0)

    print("Stats:")
    st = s.stats()
    print(f"  total={st['total']}")
    print(f"  by_domain: {st['by_domain']}")
    print(f"  by_level: {st['by_level']}")

    print()
    print("Top skills:")
    for sk in s.top(limit=5):
        print(f"  • {sk['name']} [{sk['level']}] "
              f"(used {sk['times_used']}, ok {sk['times_succeeded']}, "
              f"q={sk['avg_quality']:.1f})")

    print()
    print("Relevant for 'أنشئ ملف Python':")
    print(s.relevant_for("أنشئ ملف Python"))

    # Cleanup test skills (so learning.db isn't polluted)
    try:
        with sqlite3.connect(s.db_path) as conn:
            conn.execute("DELETE FROM skills WHERE source IN ('manual','tri-brain')")
            conn.commit()
        print()
        print("(test data cleaned)")
    except Exception:
        pass
