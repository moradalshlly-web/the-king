"""
memory/entity_graph.py
======================
Entity-relation graph memory for MOROAI.

Instead of flat memories, we build a GRAPH:
    - Entities: people, places, tools, projects, concepts
    - Relations: works_on, located_in, uses, created, related_to

Storage: SQLite (same learning.db file).
No external dependencies (no networkx, no graph-db).
"""

import os
import json
import sqlite3
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

try:
    from brain.core_paths import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = os.path.expanduser("~/moroai")


DB_FILE = os.path.join(os.path.dirname(__file__), "data", "learning.db")


# ───────────────────────────────────────────────
# Schema
# ───────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    mentions INTEGER DEFAULT 1,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    metadata TEXT,
    UNIQUE(name, type)
);

CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    relation TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    metadata TEXT,
    FOREIGN KEY(source_id) REFERENCES entities(id),
    FOREIGN KEY(target_id) REFERENCES entities(id),
    UNIQUE(source_id, target_id, relation)
);

CREATE INDEX IF NOT EXISTS idx_entity_name ON entities(name);
CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_relation_src ON relations(source_id);
CREATE INDEX IF NOT EXISTS idx_relation_tgt ON relations(target_id);
CREATE INDEX IF NOT EXISTS idx_relation_name ON relations(relation);
"""


# ───────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(name: str) -> str:
    """
    Normalize entity name for matching.
    - strip + lowercase
    - remove Arabic diacritics (tashkeel)
    - unify alef / hamza / ta-marbuta variants
    """
    if not name:
        return ""
    s = name.strip().lower()

    # Remove Arabic diacritics (U+064B to U+0652) and tatweel
    diacritics = "\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652\u0670\u0640"
    s = "".join(ch for ch in s if ch not in diacritics)

    # Unify alef variants: أ إ آ ٱ → ا
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا")
    # Unify hamza: ؤ → و, ئ → ي
    s = s.replace("ؤ", "و").replace("ئ", "ي")
    # Unify ta-marbuta: ة → ه
    s = s.replace("ة", "ه")

    return s


# ───────────────────────────────────────────────
# Core class
# ───────────────────────────────────────────────

class EntityGraph:

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DB_FILE
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    # -------- Entities --------

    def add_entity(self, name: str,
                   etype: str = "concept",
                   metadata: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """Add or bump an entity. Returns its id."""
        n = _norm(name)
        if not n:
            return None
        t = (etype or "concept").strip().lower()[:30]
        now = _now()
        meta_str = json.dumps(metadata, ensure_ascii=False) if metadata else ""

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, mentions FROM entities WHERE name=? AND type=?",
                (n, t),
            ).fetchone()

            if row:
                eid, mentions = row
                conn.execute(
                    "UPDATE entities SET mentions=?, last_seen=?, metadata=? WHERE id=?",
                    (mentions + 1, now, meta_str or "", eid),
                )
                conn.commit()
                return eid
            else:
                cur = conn.execute(
                    """INSERT INTO entities
                       (name, type, mentions, first_seen, last_seen, metadata)
                       VALUES (?, ?, 1, ?, ?, ?)""",
                    (n, t, now, now, meta_str),
                )
                conn.commit()
                return cur.lastrowid

    def get_entity(self, name: str,
                   etype: Optional[str] = None) -> Optional[Dict[str, Any]]:
        n = _norm(name)
        if not n:
            return None
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if etype:
                cur = conn.execute(
                    "SELECT * FROM entities WHERE name=? AND type=?",
                    (n, etype.lower()),
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM entities WHERE name=? ORDER BY mentions DESC LIMIT 1",
                    (n,),
                )
            row = cur.fetchone()
            return dict(row) if row else None

    # -------- Relations --------

    def add_relation(self, source: str, target: str, relation: str,
                     source_type: str = "concept",
                     target_type: str = "concept",
                     weight: float = 1.0,
                     metadata: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """Add or bump a relation between two entities."""
        sid = self.add_entity(source, source_type)
        tid = self.add_entity(target, target_type)
        if sid is None or tid is None:
            return None
        rel = (relation or "related_to").strip().lower()[:40]
        now = _now()
        meta_str = json.dumps(metadata, ensure_ascii=False) if metadata else ""

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, weight FROM relations WHERE source_id=? AND target_id=? AND relation=?",
                (sid, tid, rel),
            ).fetchone()
            if row:
                rid, w = row
                conn.execute(
                    "UPDATE relations SET weight=?, last_seen=?, metadata=? WHERE id=?",
                    (float(w) + weight, now, meta_str or "", rid),
                )
                conn.commit()
                return rid
            cur = conn.execute(
                """INSERT INTO relations
                   (source_id, target_id, relation, weight, first_seen, last_seen, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (sid, tid, rel, weight, now, now, meta_str),
            )
            conn.commit()
            return cur.lastrowid

    # -------- Query --------

    def neighbors(self, name: str, depth: int = 1) -> Dict[str, Any]:
        """
        Return the subgraph around an entity up to `depth` hops.
        """
        root = self.get_entity(name)
        if not root:
            return {"center": name, "found": False, "nodes": [], "edges": []}

        visited = {root["id"]: root}
        edges = []
        frontier = {root["id"]}

        for _ in range(max(1, depth)):
            next_frontier = set()
            for nid in frontier:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.execute(
                        """SELECT r.*, 
                                  e1.name AS src_name, e1.type AS src_type,
                                  e2.name AS tgt_name, e2.type AS tgt_type
                           FROM relations r
                           JOIN entities e1 ON e1.id = r.source_id
                           JOIN entities e2 ON e2.id = r.target_id
                           WHERE r.source_id=? OR r.target_id=?""",
                        (nid, nid),
                    )
                    for row in cur.fetchall():
                        d = dict(row)
                        edges.append(d)
                        other_id = d["target_id"] if d["source_id"] == nid else d["source_id"]
                        if other_id not in visited:
                            with sqlite3.connect(self.db_path) as conn2:
                                conn2.row_factory = sqlite3.Row
                                e = conn2.execute(
                                    "SELECT * FROM entities WHERE id=?",
                                    (other_id,),
                                ).fetchone()
                                if e:
                                    visited[other_id] = dict(e)
                                    next_frontier.add(other_id)
            frontier = next_frontier
            if not frontier:
                break

        # Dedup edges
        seen = set()
        uniq_edges = []
        for e in edges:
            key = (e["source_id"], e["target_id"], e["relation"])
            if key in seen:
                continue
            seen.add(key)
            uniq_edges.append({
                "source": e["src_name"],
                "source_type": e["src_type"],
                "target": e["tgt_name"],
                "target_type": e["tgt_type"],
                "relation": e["relation"],
                "weight": e["weight"],
            })

        return {
            "center": name,
            "found": True,
            "node_count": len(visited),
            "edge_count": len(uniq_edges),
            "nodes": list(visited.values()),
            "edges": uniq_edges,
        }

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Find entities by substring match."""
        if not query:
            return []
        q = f"%{_norm(query)}%"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                """SELECT * FROM entities
                   WHERE name LIKE ?
                   ORDER BY mentions DESC LIMIT ?""",
                (q, limit),
            )
            return [dict(r) for r in cur.fetchall()]

    def stats(self) -> Dict[str, int]:
        with sqlite3.connect(self.db_path) as conn:
            e = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            r = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
            types = conn.execute(
                "SELECT type, COUNT(*) FROM entities GROUP BY type ORDER BY 2 DESC LIMIT 8"
            ).fetchall()
        return {
            "entities": e,
            "relations": r,
            "by_type": [{"type": t, "count": c} for t, c in types],
        }

    # -------- LLM-assisted extraction --------

    def extract_from_text(self, brain, text: str,
                          max_entities: int = 8) -> Dict[str, Any]:
        """
        Use the LLM to extract entities and relations from a piece of text.
        Stores them in the graph.
        """
        if not text or len(text.strip()) < 20:
            return {"ok": False, "reason": "text too short"}

        system = """You extract entities and relations.

Output ONLY valid JSON:
{
  "entities": [
    {"name": "<entity name>", "type": "person|place|tool|project|concept|org"}
  ],
  "relations": [
    {"source": "<name>", "target": "<name>", "relation": "<verb_phrase>"}
  ]
}

Rules:
- Names should be in original language (Arabic or English as used in text).
- Max 8 entities, max 10 relations.
- Relations must connect two entities that both appear in the entities list.
- Use short verb phrases for relations: works_on, located_in, uses, created, related_to.
- Output JSON only. No markdown fences. No explanation."""

        resp = brain.ask(
            prompt=text[:4000],
            content_class="standard",
            system=system,
            temperature=0.2,
        )
        if not resp.success:
            return {"ok": False, "reason": resp.error}

        parsed = _extract_json(resp.text or "")
        if not parsed:
            return {"ok": False, "reason": "could not parse JSON"}

        ents = parsed.get("entities") or []
        rels = parsed.get("relations") or []

        added_e = 0
        added_r = 0
        for e in ents[:max_entities]:
            if isinstance(e, dict) and e.get("name"):
                if self.add_entity(e["name"], e.get("type", "concept")):
                    added_e += 1
        for r in rels[:20]:
            if not isinstance(r, dict):
                continue
            s, t, rel = r.get("source"), r.get("target"), r.get("relation")
            if s and t and rel:
                if self.add_relation(s, t, rel):
                    added_r += 1

        return {
            "ok": True,
            "entities_added": added_e,
            "relations_added": added_r,
            "provider": resp.provider,
        }

    # -------- Context building --------

    def context_for(self, query: str, depth: int = 1,
                    top_k: int = 3) -> str:
        """
        Build a short text describing the subgraph(s) relevant to a query.
        Used to enrich prompts.
        """
        hits = self.search(query, limit=top_k)
        if not hits:
            return ""

        parts = []
        for h in hits:
            sub = self.neighbors(h["name"], depth=depth)
            if not sub.get("found"):
                continue
            lines = [f"• {h['name']} ({h['type']}, mentions={h['mentions']})"]
            for edge in sub.get("edges", [])[:8]:
                lines.append(
                    f"    - {edge['source']} --[{edge['relation']}]--> {edge['target']}"
                )
            parts.append("\n".join(lines))
        return "\n\n".join(parts)


# ───────────────────────────────────────────────
# JSON helper
# ───────────────────────────────────────────────

def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if len(lines) > 1:
            t = "\n".join(lines[1:])
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3].rstrip()
    try:
        return json.loads(t)
    except Exception:
        pass
    s, e = t.find("{"), t.rfind("}")
    if s != -1 and e > s:
        try:
            return json.loads(t[s:e+1])
        except Exception:
            pass
    return None


# ───────────────────────────────────────────────
# Self-test
# ───────────────────────────────────────────────

if __name__ == "__main__":
    g = EntityGraph()
    print("Entity Graph — self-test")
    print("=" * 55)

    # Seed a small graph
    g.add_relation("مراد", "MOROAI", "works_on",
                   source_type="person", target_type="project")
    g.add_relation("MOROAI", "ليبيا", "located_in",
                   source_type="project", target_type="place")
    g.add_relation("MOROAI", "Groq", "uses",
                   source_type="project", target_type="tool")
    g.add_relation("MOROAI", "Hugging Face", "uses",
                   source_type="project", target_type="tool")

    print("Stats:")
    s = g.stats()
    print(f"  entities={s['entities']}  relations={s['relations']}")
    for t in s["by_type"]:
        print(f"    {t['type']}: {t['count']}")

    print()
    print("Neighbors of MOROAI:")
    n = g.neighbors("MOROAI", depth=1)
    print(f"  nodes={n['node_count']}  edges={n['edge_count']}")
    for e in n["edges"]:
        print(f"    {e['source']} --[{e['relation']}]--> {e['target']}")

    print()
    print("Context for 'MOROAI':")
    print(g.context_for("MOROAI"))
