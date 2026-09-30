"""
brain/search_history.py
=======================

Persistent search history for MOROAI.

Stores every search permanently (until user deletes).
Each entry contains:
    - id              : unique identifier
    - tool            : which tool (web_search, github_search, ...)
    - args            : the search arguments (query, limit)
    - results         : the results snapshot
    - created_at      : when first searched
    - updated_at      : last refresh
    - refresh_count   : how many times refreshed

Local-first design (JSON files), easy to migrate to cloud later.

Storage:
    ~/moroai/.moroai/search_history/index.json       — list of entries
    ~/moroai/.moroai/search_history/items/<id>.json  — full entry data
"""

import os
import json
import time
import uuid
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any


# ============================================================
# Paths
# ============================================================

try:
    from .core_paths import PROJECT_ROOT
except ImportError:
    from core_paths import PROJECT_ROOT


HISTORY_DIR = os.path.join(PROJECT_ROOT, ".moroai", "search_history")
ITEMS_DIR = os.path.join(HISTORY_DIR, "items")
INDEX_FILE = os.path.join(HISTORY_DIR, "index.json")

REFRESH_INTERVAL = 12 * 3600  # 12 hours
MAX_ENTRIES = 500  # auto-prune oldest when exceeded


# ============================================================
# Helpers
# ============================================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_id(tool: str, args: Dict[str, Any]) -> str:
    """Deterministic ID from tool + args (same search = same ID)."""
    raw = f"{tool}|{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{tool}-{digest}"


def _ensure_dirs() -> None:
    os.makedirs(HISTORY_DIR, exist_ok=True)
    os.makedirs(ITEMS_DIR, exist_ok=True)


def _read_index() -> Dict[str, Any]:
    if not os.path.exists(INDEX_FILE):
        return {"entries": []}
    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"entries": []}


def _write_index(data: Dict[str, Any]) -> None:
    _ensure_dirs()
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _item_path(entry_id: str) -> str:
    return os.path.join(ITEMS_DIR, f"{entry_id}.json")


def _read_item(entry_id: str) -> Optional[Dict[str, Any]]:
    path = _item_path(entry_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_item(entry_id: str, data: Dict[str, Any]) -> None:
    _ensure_dirs()
    with open(_item_path(entry_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# Public API
# ============================================================

def add_or_update(
    tool: str,
    args: Dict[str, Any],
    results: Dict[str, Any],
) -> str:
    """
    Add a new search or update an existing one.
    Returns the entry ID.
    """
    _ensure_dirs()
    entry_id = _make_id(tool, args)
    now = _now_iso()

    existing = _read_item(entry_id)

    if existing:
        # Update existing
        existing["results"] = results
        existing["updated_at"] = now
        existing["refresh_count"] = existing.get("refresh_count", 0) + 1
        _write_item(entry_id, existing)
    else:
        # Create new
        item = {
            "id": entry_id,
            "tool": tool,
            "args": args,
            "results": results,
            "created_at": now,
            "updated_at": now,
            "refresh_count": 0,
        }
        _write_item(entry_id, item)

        # Add to index
        idx = _read_index()
        idx["entries"].append({
            "id": entry_id,
            "tool": tool,
            "query": args.get("query", args.get("path", "?")),
            "created_at": now,
            "updated_at": now,
        })
        _write_index(idx)

    # Auto-prune if we exceeded MAX_ENTRIES
    try:
        _prune_if_needed()
    except Exception:
        pass

    return entry_id


def list_entries(limit: int = 100) -> List[Dict[str, Any]]:
    """Return the index entries, most recent first."""
    idx = _read_index()
    entries = idx.get("entries", [])
    entries.sort(key=lambda e: e.get("updated_at", ""), reverse=True)
    return entries[:limit]


def get_entry(entry_id: str) -> Optional[Dict[str, Any]]:
    """Get full entry by ID."""
    return _read_item(entry_id)


def delete_entry(entry_id: str) -> bool:
    """Delete one entry. Returns True on success."""
    path = _item_path(entry_id)
    if not os.path.exists(path):
        return False
    try:
        os.remove(path)
        idx = _read_index()
        idx["entries"] = [e for e in idx.get("entries", []) if e.get("id") != entry_id]
        _write_index(idx)
        return True
    except Exception:
        return False


def clear_all() -> int:
    """Delete all entries. Returns count removed."""
    idx = _read_index()
    count = len(idx.get("entries", []))
    for entry in idx.get("entries", []):
        try:
            os.remove(_item_path(entry["id"]))
        except Exception:
            pass
    _write_index({"entries": []})
    return count


def needs_refresh(entry_id: str) -> bool:
    """Check if an entry needs a refresh (older than 12h)."""
    item = _read_item(entry_id)
    if not item:
        return False
    updated = item.get("updated_at", "")
    if not updated:
        return True
    try:
        dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        return age > REFRESH_INTERVAL
    except Exception:
        return True


def entries_to_refresh(limit: int = 3) -> List[str]:
    """Return IDs of entries older than 12h, oldest first."""
    idx = _read_index()
    entries = sorted(idx.get("entries", []), key=lambda e: e.get("updated_at", ""))
    stale = [e["id"] for e in entries if needs_refresh(e["id"])]
    return stale[:limit]


def _prune_if_needed() -> int:
    """
    If total entries exceed MAX_ENTRIES, delete oldest ones.
    Returns number pruned.
    """
    idx = _read_index()
    entries = idx.get("entries", [])
    if len(entries) <= MAX_ENTRIES:
        return 0

    # Sort by updated_at ascending (oldest first)
    entries_sorted = sorted(entries, key=lambda e: e.get("updated_at", ""))
    to_remove = entries_sorted[:len(entries) - MAX_ENTRIES]

    for e in to_remove:
        try:
            os.remove(_item_path(e["id"]))
        except Exception:
            pass

    keep_ids = {e["id"] for e in entries_sorted[len(entries) - MAX_ENTRIES:]}
    idx["entries"] = [e for e in entries if e["id"] in keep_ids]
    _write_index(idx)
    return len(to_remove)


def stats() -> Dict[str, int]:
    """Return basic stats."""
    idx = _read_index()
    return {
        "total": len(idx.get("entries", [])),
        "stale": sum(1 for e in idx.get("entries", []) if needs_refresh(e["id"])),
        "max": MAX_ENTRIES,
    }


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    print(f"History dir: {HISTORY_DIR}")
    print(f"Items dir  : {ITEMS_DIR}")
    print(f"Index file : {INDEX_FILE}")
    print()

    # Add test entry
    eid = add_or_update(
        "github_search",
        {"query": "test", "limit": 5},
        {"success": True, "results": [{"name": "test/repo"}], "kind": "github"},
    )
    print(f"Added entry: {eid}")

    # List
    entries = list_entries()
    print(f"Total entries: {len(entries)}")
    for e in entries:
        print(f"  {e['id']} : {e['query']}")

    # Stats
    print(f"Stats: {stats()}")

    # Delete
    ok = delete_entry(eid)
    print(f"Deleted: {ok}")
    print(f"After delete: {len(list_entries())} entries")
