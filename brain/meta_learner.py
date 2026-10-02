"""
brain/meta_learner.py
=====================
Meta-Learner for MOROAI — deep self-analysis.

Features:
    1. Observations     (Hindsight-style auto-consolidation)
    2. Blindspots       (Johari Window) + Awareness Score
    3. Curiosity Drive  (PUMA-style self-motivated learning)
    4. Dead Ends        (Negative Knowledge from emergent-judgment)
    5. Fast Adaptation  (MetaClaw-style learning from failure)

No LLM required for basic analysis. Optional LLM for smart summarization.
"""

import os
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional


try:
    from brain.core_paths import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = os.path.expanduser("~/moroai")


LEARNING_DB      = os.path.join(PROJECT_ROOT, "memory", "data", "learning.db")
PROVIDER_METRICS = os.path.join(PROJECT_ROOT, "memory", "data", "provider_metrics.json")
INSIGHTS_FILE    = os.path.join(PROJECT_ROOT, "memory", "data", "meta_insights.json")


# ═══════════════════════════════════════════════
# Schema extensions (new tables)
# ═══════════════════════════════════════════════

EXTENSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    domain TEXT NOT NULL,
    content TEXT NOT NULL,
    evidence_count INTEGER DEFAULT 1,
    confidence REAL DEFAULT 0.5,
    importance REAL DEFAULT 0.5,
    last_reinforced TEXT,
    keywords TEXT
);
CREATE INDEX IF NOT EXISTS idx_obs_domain ON observations(domain);

CREATE TABLE IF NOT EXISTS blindspots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    domain TEXT NOT NULL,
    question TEXT NOT NULL,
    evidence TEXT,
    acknowledged INTEGER DEFAULT 0,
    resolved INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_blind_domain ON blindspots(domain);

CREATE TABLE IF NOT EXISTS curiosity_gaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    domain TEXT NOT NULL,
    title TEXT NOT NULL,
    reason TEXT,
    priority INTEGER DEFAULT 5,
    resolved INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_curio_pri ON curiosity_gaps(priority);

CREATE TABLE IF NOT EXISTS dead_ends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    path TEXT NOT NULL,
    reason TEXT,
    reopen_condition TEXT,
    tries INTEGER DEFAULT 1,
    last_tried TEXT,
    reopen INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_dead_path ON dead_ends(path);
"""


# ═══════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _init_db() -> None:
    if not os.path.isfile(LEARNING_DB):
        return
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            conn.executescript(EXTENSION_SCHEMA)
            conn.commit()
    except Exception:
        pass


def _load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _extract_keywords(text: str, max_k: int = 6) -> str:
    if not text:
        return ""
    # simple: longest unique words
    words = [w.strip() for w in text.split() if len(w) > 3]
    seen = []
    for w in words:
        if w not in seen:
            seen.append(w)
        if len(seen) >= max_k:
            break
    return " ".join(seen)


# ═══════════════════════════════════════════════
# Readers (existing tables)
# ═══════════════════════════════════════════════

def _read_patterns(limit: int = 40) -> List[Dict[str, Any]]:
    if not os.path.isfile(LEARNING_DB):
        return []
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("""
                SELECT pattern_type, pattern_key, occurrences,
                       last_seen, severity, notes
                FROM patterns
                ORDER BY occurrences DESC, last_seen DESC
                LIMIT ?
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def _read_skills(limit: int = 30) -> List[Dict[str, Any]]:
    if not os.path.isfile(LEARNING_DB):
        return []
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("""
                SELECT name, domain, level, times_used, times_succeeded,
                       avg_quality, last_used_at
                FROM skills
                ORDER BY last_used_at DESC
                LIMIT ?
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def _read_verifications_stats() -> Dict[str, Any]:
    if not os.path.isfile(LEARNING_DB):
        return {}
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN passed=1 THEN 1 ELSE 0 END) AS passed,
                    AVG(score) AS avg_score
                FROM verifications
            """).fetchone()
            by_type = conn.execute("""
                SELECT target_type,
                       COUNT(*) AS total,
                       SUM(CASE WHEN passed=1 THEN 1 ELSE 0 END) AS passed,
                       AVG(score) AS avg_score
                FROM verifications
                GROUP BY target_type
            """).fetchall()
        return {
            "total": row[0] or 0,
            "passed": row[1] or 0,
            "avg_score": round(row[2], 2) if row[2] else 0.0,
            "by_type": [
                {"type": t, "total": tot, "passed": p,
                 "avg_score": round(a, 2) if a else 0.0}
                for t, tot, p, a in by_type
            ],
        }
    except Exception:
        return {}


def _read_provider_metrics() -> Dict[str, Any]:
    return _load_json(PROVIDER_METRICS, {})


def _read_episodes_count() -> int:
    if not os.path.isfile(LEARNING_DB):
        return 0
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            return conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
    except Exception:
        return 0


def _read_recent_episodes(limit: int = 30) -> List[Dict[str, Any]]:
    if not os.path.isfile(LEARNING_DB):
        return []
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("""
                SELECT id, timestamp, prompt, response, success,
                       provider, model, error
                FROM episodes
                ORDER BY id DESC LIMIT ?
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


# ═══════════════════════════════════════════════
# 1) OBSERVATIONS (Hindsight-style)
# ═══════════════════════════════════════════════

def add_observation(domain: str, content: str,
                    confidence: float = 0.5,
                    importance: float = 0.5,
                    evidence: Optional[List[str]] = None) -> Optional[int]:
    """
    Add or merge an observation.
    If similar observation exists in same domain, reinforce it.
    """
    if not content or not content.strip():
        return None
    _init_db()
    domain = (domain or "general").lower()[:40]
    content = content.strip()[:500]
    kws = _extract_keywords(content)

    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            # Merge: find existing with strong keyword overlap
            cur = conn.execute("""
                SELECT id, evidence_count, confidence, keywords
                FROM observations
                WHERE domain = ?
                ORDER BY last_reinforced DESC LIMIT 20
            """, (domain,))
            for row in cur.fetchall():
                oid, evc, conf, kk = row
                if not kk:
                    continue
                # Simple keyword overlap check
                existing_kws = set(kk.split())
                new_kws = set(kws.split())
                if not existing_kws or not new_kws:
                    continue
                overlap = len(existing_kws & new_kws) / max(len(new_kws), 1)
                if overlap >= 0.6:
                    new_conf = min(1.0, (conf or 0.5) + 0.1)
                    conn.execute("""
                        UPDATE observations
                        SET evidence_count = evidence_count + 1,
                            confidence = ?,
                            last_reinforced = ?,
                            content = ?
                        WHERE id = ?
                    """, (new_conf, _now(), content, oid))
                    conn.commit()
                    return oid

            # Insert new
            cur = conn.execute("""
                INSERT INTO observations
                (timestamp, domain, content, evidence_count,
                 confidence, importance, last_reinforced, keywords)
                VALUES (?, ?, ?, 1, ?, ?, ?, ?)
            """, (_now(), domain, content, confidence, importance, _now(), kws))
            conn.commit()
            return cur.lastrowid
    except Exception:
        return None


def list_observations(domain: Optional[str] = None,
                      limit: int = 20) -> List[Dict[str, Any]]:
    _init_db()
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            conn.row_factory = sqlite3.Row
            if domain:
                cur = conn.execute("""
                    SELECT * FROM observations
                    WHERE domain = ?
                    ORDER BY importance DESC, last_reinforced DESC
                    LIMIT ?
                """, (domain.lower(), limit))
            else:
                cur = conn.execute("""
                    SELECT * FROM observations
                    ORDER BY importance DESC, last_reinforced DESC
                    LIMIT ?
                """, (limit,))
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def consolidate_from_episodes() -> int:
    """
    Auto-consolidate: read recent successful episodes, extract observations.
    Returns number of new observations added.
    """
    eps = _read_recent_episodes(limit=40)
    added = 0
    for ep in eps:
        if not ep.get("success"):
            continue
        prompt = (ep.get("prompt") or "").strip()
        if len(prompt) < 20:
            continue
        # Use a compact summary as an observation
        obs_text = prompt[:200]
        if add_observation(
            domain="conversation",
            content=obs_text,
            confidence=0.6,
            importance=0.4,
        ):
            added += 1
    return added


# ═══════════════════════════════════════════════
# 2) BLINDSPOTS (Johari Window)
# ═══════════════════════════════════════════════

def add_blindspot(domain: str, question: str,
                  evidence: str = "") -> Optional[int]:
    """
    Record a known-unknown: something we know we don't know.
    """
    if not question or not question.strip():
        return None
    _init_db()
    domain = (domain or "general").lower()[:40]
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            # Dedup by question substring
            cur = conn.execute("""
                SELECT id FROM blindspots
                WHERE domain = ? AND question LIKE ?
                LIMIT 1
            """, (domain, f"%{question[:40]}%"))
            row = cur.fetchone()
            if row:
                return row[0]
            cur = conn.execute("""
                INSERT INTO blindspots
                (timestamp, domain, question, evidence, acknowledged, resolved)
                VALUES (?, ?, ?, ?, 0, 0)
            """, (_now(), domain, question[:300], (evidence or "")[:500]))
            conn.commit()
            return cur.lastrowid
    except Exception:
        return None


def acknowledge_blindspot(bid: int) -> bool:
    _init_db()
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            conn.execute("UPDATE blindspots SET acknowledged = 1 WHERE id = ?",
                         (bid,))
            conn.commit()
            return True
    except Exception:
        return False


def resolve_blindspot(bid: int) -> bool:
    _init_db()
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            conn.execute("UPDATE blindspots SET resolved = 1 WHERE id = ?",
                         (bid,))
            conn.commit()
            return True
    except Exception:
        return False


def list_blindspots(open_only: bool = True,
                    limit: int = 30) -> List[Dict[str, Any]]:
    _init_db()
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            conn.row_factory = sqlite3.Row
            if open_only:
                cur = conn.execute("""
                    SELECT * FROM blindspots
                    WHERE resolved = 0
                    ORDER BY acknowledged DESC, id DESC
                    LIMIT ?
                """, (limit,))
            else:
                cur = conn.execute("""
                    SELECT * FROM blindspots
                    ORDER BY id DESC LIMIT ?
                """, (limit,))
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def awareness_score() -> Dict[str, Any]:
    """
    Compute awareness score (0-100) from Johari window state:
    - Known-knowns   : skills (level != beginner)
    - Known-unknowns : acknowledged blindspots
    - Unknown-unknowns: measured by "false confidence" (low quality but high use)
    - Openness       : willingness to admit blindspots
    """
    _init_db()
    score = 50.0
    notes: List[str] = []

    # Known-knowns
    skills = _read_skills(limit=50)
    skilled = [s for s in skills if s.get("level") in ("advanced", "expert")]
    if len(skilled) >= 3:
        score += 10
        notes.append(f"{len(skilled)} مهارات متقدمة")
    elif len(skilled) >= 1:
        score += 5
        notes.append(f"{len(skilled)} مهارة متقدمة")

    # Known-unknowns (blindspots)
    blinds = list_blindspots(open_only=True)
    ack = [b for b in blinds if b.get("acknowledged")]
    if len(ack) >= 3:
        score += 15
        notes.append(f"{len(ack)} نقطة عمياء معترف بها")
    elif len(ack) >= 1:
        score += 8
        notes.append(f"{len(ack)} نقطة عمياء")
    # Unexamined blindspots reduce score
    unack = len(blinds) - len(ack)
    if unack >= 3:
        score -= 5
        notes.append(f"{unack} نقطة عمياء لم تُدرس")

    # False confidence: skills used a lot but low quality
    overconfident = [
        s for s in skills
        if s.get("times_used", 0) >= 5 and s.get("avg_quality", 0) < 2.5
    ]
    if overconfident:
        score -= 3 * len(overconfident)
        notes.append(f"{len(overconfident)} مهارات واثقة كاذبة")

    score = max(0.0, min(100.0, score))
    return {
        "score": round(score, 1),
        "notes": notes,
    }


# ═══════════════════════════════════════════════
# 3) CURIOSITY DRIVE (PUMA-style)
# ═══════════════════════════════════════════════

def add_curiosity_gap(domain: str, title: str, reason: str,
                      priority: int = 5) -> Optional[int]:
    """
    Record a self-motivated learning gap.
    Priority 1 (highest) .. 10 (lowest).
    """
    if not title or not title.strip():
        return None
    _init_db()
    domain = (domain or "general").lower()[:40]
    priority = max(1, min(10, int(priority)))
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            cur = conn.execute("""
                SELECT id FROM curiosity_gaps
                WHERE domain = ? AND title LIKE ? AND resolved = 0
                LIMIT 1
            """, (domain, f"%{title[:40]}%"))
            row = cur.fetchone()
            if row:
                return row[0]
            cur = conn.execute("""
                INSERT INTO curiosity_gaps
                (timestamp, domain, title, reason, priority, resolved)
                VALUES (?, ?, ?, ?, ?, 0)
            """, (_now(), domain, title[:200], (reason or "")[:400], priority))
            conn.commit()
            return cur.lastrowid
    except Exception:
        return None


def list_curiosity_gaps(open_only: bool = True,
                        limit: int = 20) -> List[Dict[str, Any]]:
    _init_db()
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            conn.row_factory = sqlite3.Row
            if open_only:
                cur = conn.execute("""
                    SELECT * FROM curiosity_gaps
                    WHERE resolved = 0
                    ORDER BY priority ASC, id DESC
                    LIMIT ?
                """, (limit,))
            else:
                cur = conn.execute("""
                    SELECT * FROM curiosity_gaps
                    ORDER BY id DESC LIMIT ?
                """, (limit,))
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def resolve_curiosity_gap(cid: int) -> bool:
    _init_db()
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            conn.execute("UPDATE curiosity_gaps SET resolved = 1 WHERE id = ?",
                         (cid,))
            conn.commit()
            return True
    except Exception:
        return False


def detect_curiosity_gaps() -> int:
    """
    Auto-detect gaps from patterns + skills + failed episodes.
    Returns number of NEW gaps added.
    """
    added = 0

    # From recurring patterns (medium/high severity, occ >= 3)
    for p in _read_patterns(limit=40):
        occ = p.get("occurrences", 0)
        sev = p.get("severity", "info")
        if occ >= 3 and sev in ("medium", "high"):
            title = f"معالجة متكررة: {p.get('pattern_key', '?')[:80]}"
            if add_curiosity_gap(
                "quality",
                title,
                f"ظهر {occ} مرات (النوع: {p.get('pattern_type')})",
                priority=3 if sev == "high" else 5,
            ):
                added += 1

    # From weak skills
    for s in _read_skills(limit=30):
        if s.get("times_used", 0) >= 5 and s.get("avg_quality", 0) < 3.0:
            title = f"تحسين: {s['name']}"
            if add_curiosity_gap(
                "skill",
                title,
                f"جودة منخفضة ({s.get('avg_quality')}/5)",
                priority=4,
            ):
                added += 1

    # From failed episodes (last 20)
    for ep in _read_recent_episodes(limit=20):
        if ep.get("success"):
            continue
        err = (ep.get("error") or "").strip()[:80]
        if err:
            title = f"حل خطأ: {err}"
            if add_curiosity_gap("error", title, "من محادثة فاشلة", priority=4):
                added += 1

    return added


def propose_goals(limit: int = 3) -> List[Dict[str, Any]]:
    """
    Turn top curiosity gaps into proposed learning goals.
    """
    gaps = list_curiosity_gaps(open_only=True, limit=limit)
    goals = []
    for g in gaps:
        goals.append({
            "title": f"تعلّم: {g['title']}",
            "reason": g.get("reason", ""),
            "priority": g.get("priority", 5),
            "domain": g.get("domain", "general"),
        })
    return goals


# ═══════════════════════════════════════════════
# 4) DEAD ENDS (Negative Knowledge)
# ═══════════════════════════════════════════════

def record_dead_end(path: str, reason: str,
                    reopen_condition: str = "") -> Optional[int]:
    """
    Record a confirmed dead end. If exists, bump tries.
    """
    if not path:
        return None
    _init_db()
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            cur = conn.execute("""
                SELECT id, tries FROM dead_ends
                WHERE path = ? AND reopen = 0
                LIMIT 1
            """, (path[:300],))
            row = cur.fetchone()
            if row:
                conn.execute("""
                    UPDATE dead_ends
                    SET tries = tries + 1, last_tried = ?, reason = ?
                    WHERE id = ?
                """, (_now(), (reason or "")[:400], row[0]))
                conn.commit()
                return row[0]
            cur = conn.execute("""
                INSERT INTO dead_ends
                (timestamp, path, reason, reopen_condition, tries,
                 last_tried, reopen)
                VALUES (?, ?, ?, ?, 1, ?, 0)
            """, (_now(), path[:300], (reason or "")[:400],
                  (reopen_condition or "")[:300], _now()))
            conn.commit()
            return cur.lastrowid
    except Exception:
        return None


def is_dead_end(path: str) -> bool:
    _init_db()
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            cur = conn.execute("""
                SELECT 1 FROM dead_ends
                WHERE path = ? AND reopen = 0
                LIMIT 1
            """, (path[:300],))
            return cur.fetchone() is not None
    except Exception:
        return False


def list_dead_ends(limit: int = 30) -> List[Dict[str, Any]]:
    _init_db()
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("""
                SELECT * FROM dead_ends
                WHERE reopen = 0
                ORDER BY tries DESC, last_tried DESC
                LIMIT ?
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def reopen_dead_end(did: int) -> bool:
    _init_db()
    try:
        with sqlite3.connect(LEARNING_DB) as conn:
            conn.execute("UPDATE dead_ends SET reopen = 1 WHERE id = ?", (did,))
            conn.commit()
            return True
    except Exception:
        return False


# ═══════════════════════════════════════════════
# 5) FAST ADAPTATION (MetaClaw-style)
# ═══════════════════════════════════════════════

def extract_skill_from_failure(episode: Dict[str, Any]) -> Optional[str]:
    """
    Analyze a failed episode and record a corrective observation.
    Returns the skill name if a new one is proposed.
    """
    if not episode or episode.get("success"):
        return None
    err = (episode.get("error") or "").strip()
    prompt = (episode.get("prompt") or "").strip()
    if not err:
        return None

    # Record as observation
    add_observation(
        domain="failure_pattern",
        content=f"عند '{prompt[:80]}' فشل بـ '{err[:80]}'",
        confidence=0.7,
        importance=0.8,
    )

    # Suggest a skill
    skill_name = f"تجنّب: {err[:60]}"
    try:
        from memory.skills import SkillRegistry
        sr = SkillRegistry()
        sr.add(
            name=skill_name,
            domain="quality",
            description=f"درس من فشل: {err[:100]}",
            examples=[prompt[:150]],
            source="meta_learner",
        )
        return skill_name
    except Exception:
        return None


def adapt_from_recent_failures(limit: int = 10) -> List[str]:
    """
    Scan recent failures and extract skills/observations.
    Returns names of skills proposed.
    """
    proposed = []
    count = 0
    for ep in _read_recent_episodes(limit=40):
        if count >= limit:
            break
        if ep.get("success"):
            continue
        skill = extract_skill_from_failure(ep)
        if skill:
            proposed.append(skill)
            count += 1
    return proposed


# ═══════════════════════════════════════════════
# Insight builders
# ═══════════════════════════════════════════════

def _analyze_patterns(patterns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for p in patterns:
        occ = p.get("occurrences", 0)
        sev = p.get("severity", "info")
        key = p.get("pattern_key", "?")
        if occ >= 4 and sev in ("high", "medium"):
            out.append({
                "type": "recurring_problem",
                "severity": "high" if sev == "high" else "medium",
                "title": f"خطأ متكرر: {key}",
                "detail": f"ظهر {occ} مرات",
                "action": f"اقتراح: فحص تلقائي لهذا النمط",
            })
        elif occ >= 6:
            out.append({
                "type": "recurring_problem",
                "severity": "medium",
                "title": f"نمط شائع: {key}",
                "detail": f"ظهر {occ} مرات",
                "action": f"اقتراح: مراجعة الأسباب الجذرية",
            })
    return out


def _analyze_skills(skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for s in skills:
        used = s.get("times_used", 0)
        ok = s.get("times_succeeded", 0)
        q = s.get("avg_quality", 0)
        level = s.get("level", "beginner")

        if used >= 5 and q < 3.0:
            out.append({
                "type": "stagnant_skill",
                "severity": "medium",
                "title": f"مهارة ضعيفة: {s['name']}",
                "detail": f"استُخدمت {used} مرة، جودة {q}/5",
                "action": f"اقتراح: مراجعة الاستراتيجية",
            })
        elif used >= 5 and ok < used * 0.5:
            out.append({
                "type": "weak_area",
                "severity": "high",
                "title": f"منطقة فاشلة: {s['name']}",
                "detail": f"{used - ok} فشل من {used}",
                "action": f"اقتراح: تجنب أو إعادة تدريب",
            })
        elif level == "expert" and q >= 4.5:
            out.append({
                "type": "positive_trend",
                "severity": "low",
                "title": f"مهارة متقنة: {s['name']}",
                "detail": f"خبير ({ok} نجاح، جودة {q}/5)",
                "action": "يمكن استخدامها كمثال",
            })
    return out


def _analyze_providers(metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    by_task: Dict[str, List[tuple]] = {}
    for key, v in metrics.items():
        if "::" not in key:
            continue
        provider, task = key.split("::", 1)
        used = v.get("success", 0) + v.get("fail", 0)
        if used < 2:
            continue
        avg_latency = v.get("total_latency_ms", 0) / max(v.get("success", 1), 1)
        by_task.setdefault(task, []).append(
            (provider, v.get("success", 0), v.get("fail", 0), avg_latency)
        )

    for task, items in by_task.items():
        items.sort(key=lambda x: (-x[1], x[3]))
        best = items[0]
        out.append({
            "type": "provider_tip",
            "severity": "low",
            "title": f"أفضل مزود لـ '{task}': {best[0]}",
            "detail": f"نجح {best[1]} مرة، متوسط {best[3]:.0f}ms",
            "action": f"اقتراح: رفع أولوية {best[0]}",
        })
    return out


def _analyze_verifications(stats: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    if stats.get("total", 0) < 5:
        return out
    for t in stats.get("by_type", []):
        if t["total"] < 3:
            continue
        pass_rate = t["passed"] / t["total"]
        if pass_rate < 0.5:
            out.append({
                "type": "weak_area",
                "severity": "high",
                "title": f"مجال ضعيف: {t['type']}",
                "detail": f"نجاح {pass_rate*100:.0f}% ({t['passed']}/{t['total']})",
                "action": f"اقتراح: تعزيز الفحص أو التدريب",
            })
    return out


def _analyze_blindspots() -> List[Dict[str, Any]]:
    out = []
    unack = [b for b in list_blindspots(open_only=True) if not b.get("acknowledged")]
    if len(unack) >= 3:
        out.append({
            "type": "blindspot_alert",
            "severity": "high",
            "title": f"{len(unack)} نقاط عمياء لم تُدرس",
            "detail": "MOROAI يعرف أنه لا يعرف، لكنه لم يتعامل بعد",
            "action": "اقتراح: مراجعة Blindspots المفتوحة",
        })
    return out


def _analyze_curiosity() -> List[Dict[str, Any]]:
    out = []
    gaps = list_curiosity_gaps(open_only=True, limit=10)
    high_pri = [g for g in gaps if g.get("priority", 5) <= 3]
    if high_pri:
        out.append({
            "type": "curiosity_alert",
            "severity": "medium",
            "title": f"{len(high_pri)} فجوات تعلّم عالية الأولوية",
            "detail": "MOROAI حدد ما يحتاج تعلمه",
            "action": "اقتراح: راجع Goals المقترحة",
        })
    return out


def _analyze_dead_ends() -> List[Dict[str, Any]]:
    out = []
    des = list_dead_ends(limit=30)
    if len(des) >= 5:
        out.append({
            "type": "dead_end_alert",
            "severity": "low",
            "title": f"{len(des)} مسارات مسدودة موثقة",
            "detail": "MOROAI يعرف ما لا يجب تجربته",
            "action": "معلومات قيمة لتجنب التكرار",
        })
    return out


# ═══════════════════════════════════════════════
# Full analysis
# ═══════════════════════════════════════════════

def analyze(consolidate: bool = True,
            detect_gaps: bool = True,
            adapt_failures: bool = False) -> Dict[str, Any]:
    """
    Full self-analysis.

    consolidate    : extract observations from recent episodes
    detect_gaps    : auto-detect curiosity gaps
    adapt_failures : extract skills from failed episodes
    """
    _init_db()

    if consolidate:
        try:
            consolidate_from_episodes()
        except Exception:
            pass
    if detect_gaps:
        try:
            detect_curiosity_gaps()
        except Exception:
            pass
    if adapt_failures:
        try:
            adapt_from_recent_failures()
        except Exception:
            pass

    patterns = _read_patterns()
    skills = _read_skills()
    vstats = _read_verifications_stats()
    pmetrics = _read_provider_metrics()
    episodes = _read_episodes_count()
    obs = list_observations(limit=50)
    blinds = list_blindspots(open_only=True)
    gaps = list_curiosity_gaps(open_only=True)
    des = list_dead_ends()

    insights: List[Dict[str, Any]] = []
    insights += _analyze_patterns(patterns)
    insights += _analyze_skills(skills)
    insights += _analyze_providers(pmetrics)
    insights += _analyze_verifications(vstats)
    insights += _analyze_blindspots()
    insights += _analyze_curiosity()
    insights += _analyze_dead_ends()

    order = {"high": 0, "medium": 1, "low": 2}
    insights.sort(key=lambda x: order.get(x.get("severity", "low"), 3))

    aw = awareness_score()
    goals = propose_goals(limit=3)

    report = {
        "ok": True,
        "generated_at": _now(),
        "awareness": aw,
        "counts": {
            "patterns": len(patterns),
            "skills": len(skills),
            "observations": len(obs),
            "blindspots_open": len(blinds),
            "curiosity_gaps": len(gaps),
            "dead_ends": len(des),
            "episodes": episodes,
            "verifications": vstats.get("total", 0),
            "insights": len(insights),
        },
        "insights": insights,
        "proposed_goals": goals,
        "summary_ar": _build_summary(insights, aw, goals),
    }

    _save_json(INSIGHTS_FILE, report)
    return report


def _build_summary(insights: List[Dict[str, Any]],
                   awareness: Dict[str, Any],
                   goals: List[Dict[str, Any]]) -> str:
    high = sum(1 for i in insights if i["severity"] == "high")
    med = sum(1 for i in insights if i["severity"] == "medium")
    low = sum(1 for i in insights if i["severity"] == "low")

    lines = [
        f"🧠 الوعي الذاتي: {awareness.get('score')}/100",
    ]
    if awareness.get("notes"):
        for n in awareness["notes"][:3]:
            lines.append(f"   • {n}")
    lines.append("")
    lines.append(f"🎯 استنتاجات: {len(insights)} (🔴{high} 🟡{med} 🟢{low})")

    if goals:
        lines.append("")
        lines.append("📚 أهداف مقترحة:")
        for g in goals[:3]:
            lines.append(f"   {g['priority']}. {g['title']}")

    return "\n".join(lines)


def top_actions(limit: int = 3) -> List[Dict[str, Any]]:
    r = analyze(consolidate=False, detect_gaps=False)
    return [i for i in r["insights"]
            if i["severity"] in ("high", "medium")][:limit]


def last_report() -> Optional[Dict[str, Any]]:
    return _load_json(INSIGHTS_FILE, None)


# ═══════════════════════════════════════════════
# Self-test
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print("Meta-Learner v2 — deep self-analysis")
    print("=" * 60)
    r = analyze(consolidate=True, detect_gaps=True, adapt_failures=False)
    print(r["summary_ar"])
    print()
    print("─" * 60)
    print(f"📊 Counts: {r['counts']}")
    print()
    print("🎯 أعلى 5 استنتاجات:")
    for i in r["insights"][:5]:
        icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
            i["severity"], "•")
        print(f"\n{icon} [{i['type']}] {i['title']}")
        print(f"   {i['detail']}")
        print(f"   → {i['action']}")
