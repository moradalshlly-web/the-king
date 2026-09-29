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

    def count(self) -> Dict[str, int]:
        with sqlite3.connect(self.db_path) as conn:
            e = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
            l = conn.execute("SELECT COUNT(*) FROM lessons").fetchone()[0]
            return {"episodes": e, "lessons": l}


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
