"""
memory/learning.py
==================

Dual-memory learning system for MOROAI.

Episodic Memory: raw interaction records (what happened)
Semantic Memory: distilled lessons and rules (what was learned)

Storage: SQLite + FTS5 (built-in, no external deps)
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any


DB_FILE = os.path.join(os.path.dirname(__file__), "data", "learning.db")


class LearningMemory:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DB_FILE
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    response TEXT,
                    success INTEGER,
                    provider TEXT,
                    model TEXT,
                    latency_ms REAL,
                    tokens_used INTEGER,
                    content_class TEXT,
                    error TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    rule TEXT NOT NULL,
                    category TEXT,
                    confidence REAL DEFAULT 1.0,
                    source_episode_id INTEGER,
                    times_used INTEGER DEFAULT 0,
                    times_succeeded INTEGER DEFAULT 0,
                    last_used TEXT
                )
            """)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts
                USING fts5(prompt, response, content='episodes', content_rowid='id')
            """)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS lessons_fts
                USING fts5(rule, category, content='lessons', content_rowid='id')
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS verifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_ref TEXT,
                    verifier TEXT NOT NULL,
                    passed INTEGER,
                    score REAL,
                    findings TEXT,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    pattern_type TEXT NOT NULL,
                    pattern_key TEXT NOT NULL,
                    occurrences INTEGER DEFAULT 1,
                    last_seen TEXT,
                    severity TEXT DEFAULT 'info',
                    notes TEXT,
                    UNIQUE(pattern_type, pattern_key)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_verif_target
                ON verifications(target_type, target_ref)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pattern_key
                ON patterns(pattern_type, pattern_key)
            """)
            conn.commit()

    def save_episode(self, **kwargs) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("""
                INSERT INTO episodes
                (timestamp, prompt, response, success, provider, model,
                 latency_ms, tokens_used, content_class, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                kwargs.get("prompt", ""),
                kwargs.get("response", ""),
                1 if kwargs.get("success") else 0,
                kwargs.get("provider", ""),
                kwargs.get("model", ""),
                kwargs.get("latency_ms"),
                kwargs.get("tokens_used"),
                kwargs.get("content_class", "standard"),
                kwargs.get("error", ""),
            ))
            eid = cur.lastrowid
            conn.execute("""
                INSERT INTO episodes_fts(rowid, prompt, response)
                VALUES (?, ?, ?)
            """, (eid, kwargs.get("prompt", ""), kwargs.get("response", "")))
            conn.commit()
            return eid

    def save_lesson(self, rule: str, category: str = "general",
                    source_episode_id: Optional[int] = None,
                    confidence: float = 1.0) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("""
                INSERT INTO lessons
                (timestamp, rule, category, confidence, source_episode_id)
                VALUES (?, ?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                rule,
                category,
                confidence,
                source_episode_id,
            ))
            lid = cur.lastrowid
            conn.execute("""
                INSERT INTO lessons_fts(rowid, rule, category)
                VALUES (?, ?, ?)
            """, (lid, rule, category))
            conn.commit()
            return lid

    def search_lessons(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not query.strip():
            return []
        safe = " ".join(w for w in query.split() if w.isalnum() or w.isalpha())
        if not safe:
            return []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute("""
                    SELECT l.* FROM lessons l
                    JOIN lessons_fts f ON f.rowid = l.id
                    WHERE lessons_fts MATCH ?
                    ORDER BY l.confidence DESC, l.times_succeeded DESC
                    LIMIT ?
                """, (safe, limit))
                return [dict(r) for r in cur.fetchall()]
        except sqlite3.OperationalError:
            return []

    def mark_lesson_used(self, lesson_id: int, succeeded: bool) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE lessons
                SET times_used = times_used + 1,
                    times_succeeded = times_succeeded + ?,
                    last_used = ?
                WHERE id = ?
            """, (
                1 if succeeded else 0,
                datetime.now(timezone.utc).isoformat(),
                lesson_id,
            ))
            conn.commit()

    # -------- Verifications (دورية الانضباط) --------

    def save_verification(self, target_type: str, verifier: str,
                          passed: bool, score: float = None,
                          findings: str = "", target_ref: str = "",
                          metadata: str = "") -> int:
        """Save a verification result from a verifier (inspector)."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("""
                INSERT INTO verifications
                (timestamp, target_type, target_ref, verifier, passed,
                 score, findings, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                target_type, target_ref, verifier,
                1 if passed else 0,
                score, findings[:2000] if findings else "",
                metadata[:1000] if metadata else "",
            ))
            conn.commit()
            return cur.lastrowid

    def recent_verifications(self, target_type: str = None,
                             limit: int = 20) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if target_type:
                cur = conn.execute("""
                    SELECT * FROM verifications
                    WHERE target_type = ?
                    ORDER BY id DESC LIMIT ?
                """, (target_type, limit))
            else:
                cur = conn.execute("""
                    SELECT * FROM verifications
                    ORDER BY id DESC LIMIT ?
                """, (limit,))
            return [dict(r) for r in cur.fetchall()]

    def verification_stats(self, target_type: str = None) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            if target_type:
                row = conn.execute("""
                    SELECT
                      COUNT(*) as total,
                      SUM(CASE WHEN passed=1 THEN 1 ELSE 0 END) as passed,
                      AVG(score) as avg_score
                    FROM verifications WHERE target_type = ?
                """, (target_type,)).fetchone()
            else:
                row = conn.execute("""
                    SELECT
                      COUNT(*) as total,
                      SUM(CASE WHEN passed=1 THEN 1 ELSE 0 END) as passed,
                      AVG(score) as avg_score
                    FROM verifications
                """).fetchone()
            return {
                "total": row[0] or 0,
                "passed": row[1] or 0,
                "failed": (row[0] or 0) - (row[1] or 0),
                "avg_score": round(row[2], 2) if row[2] else 0.0,
            }

    # -------- Patterns (الأنماط المتكررة) --------

    def record_pattern(self, pattern_type: str, pattern_key: str,
                       severity: str = "info", notes: str = "") -> None:
        """Increment occurrence counter for a pattern."""
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("""
                SELECT id, occurrences FROM patterns
                WHERE pattern_type = ? AND pattern_key = ?
            """, (pattern_type, pattern_key)).fetchone()
            if row:
                conn.execute("""
                    UPDATE patterns
                    SET occurrences = occurrences + 1,
                        last_seen = ?,
                        severity = ?,
                        notes = ?
                    WHERE id = ?
                """, (now, severity, notes[:500], row[0]))
            else:
                conn.execute("""
                    INSERT INTO patterns
                    (timestamp, pattern_type, pattern_key, occurrences,
                     last_seen, severity, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (now, pattern_type, pattern_key, 1,
                      now, severity, notes[:500]))
            conn.commit()

    def top_patterns(self, pattern_type: str = None,
                     limit: int = 10) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if pattern_type:
                cur = conn.execute("""
                    SELECT * FROM patterns
                    WHERE pattern_type = ?
                    ORDER BY occurrences DESC LIMIT ?
                """, (pattern_type, limit))
            else:
                cur = conn.execute("""
                    SELECT * FROM patterns
                    ORDER BY occurrences DESC LIMIT ?
                """, (limit,))
            return [dict(r) for r in cur.fetchall()]

    def get_pattern(self, pattern_type: str,
                    pattern_key: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("""
                SELECT * FROM patterns
                WHERE pattern_type = ? AND pattern_key = ?
            """, (pattern_type, pattern_key))
            row = cur.fetchone()
            return dict(row) if row else None

    def count(self) -> Dict[str, int]:
        with sqlite3.connect(self.db_path) as conn:
            e = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
            l = conn.execute("SELECT COUNT(*) FROM lessons").fetchone()[0]
            try:
                v = conn.execute("SELECT COUNT(*) FROM verifications").fetchone()[0]
            except sqlite3.OperationalError:
                v = 0
            try:
                p = conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0]
            except sqlite3.OperationalError:
                p = 0
            return {
                "episodes": e,
                "lessons": l,
                "verifications": v,
                "patterns": p,
            }


if __name__ == "__main__":
    m = LearningMemory()
    print(f"DB: {m.db_path}")
    print(f"Counts: {m.count()}")
    eid = m.save_episode(
        prompt="كيف حالك؟",
        response="بخير",
        success=True,
        provider="groq",
        model="qwen",
    )
    print(f"Episode: {eid}")
    lid = m.save_lesson(
        rule="Use short replies for greetings.",
        category="style",
        source_episode_id=eid,
    )
    print(f"Lesson: {lid}")
    results = m.search_lessons("greetings")
    print(f"Search: {len(results)} result(s)")
    print("DONE")
