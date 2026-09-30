"""
brain/search_cache.py
=====================

Simple JSON cache for search results.
Avoids re-fetching the same query within TTL.
"""

import os
import json
import time
import hashlib
from typing import Optional, Dict, Any

try:
    from .core_paths import PROJECT_ROOT
except ImportError:
    from core_paths import PROJECT_ROOT


CACHE_DIR = os.path.join(PROJECT_ROOT, ".moroai", "search_cache")
DEFAULT_TTL = 3600  # 1 hour


def _key(tool: str, args: Dict[str, Any]) -> str:
    raw = f"{tool}|{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def get(tool: str, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Read cached result if valid (not expired)."""
    path = os.path.join(CACHE_DIR, _key(tool, args) + ".json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("ts", 0) > DEFAULT_TTL:
            return None
        return data.get("result")
    except Exception:
        return None


def put(tool: str, args: Dict[str, Any], result: Dict[str, Any]) -> None:
    """Save result in cache."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = os.path.join(CACHE_DIR, _key(tool, args) + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "result": result}, f, ensure_ascii=False)
    except Exception:
        pass


def clear() -> int:
    """Delete all cached entries. Returns count removed."""
    if not os.path.exists(CACHE_DIR):
        return 0
    count = 0
    for fname in os.listdir(CACHE_DIR):
        try:
            os.remove(os.path.join(CACHE_DIR, fname))
            count += 1
        except Exception:
            pass
    return count


if __name__ == "__main__":
    print("Testing search cache...")
    put("test", {"q": "hello"}, {"ok": True, "data": [1, 2, 3]})
    r = get("test", {"q": "hello"})
    print(f"Read: {r}")
    assert r and r.get("ok") is True
    print("✅ Cache works")
