"""
brain/rendezvous.py
===================

Dynamic URL rendezvous between Colab and MOROAI.
"""

import os
import time
import urllib.request
import urllib.error
from typing import Optional, Dict

try:
    from .core_paths import PROJECT_ROOT
except ImportError:
    from core_paths import PROJECT_ROOT


GIST_ID = os.getenv(
    "MOROAI_GIST_ID",
    "1de508066bd71db40f1c523e56c14083",
)

GIST_OWNER = "moradalshlly-web"
GIST_FILENAME = "moroai_tunnel.txt"

RAW_URL = f"https://gist.githubusercontent.com/{GIST_OWNER}/{GIST_ID}/raw/{GIST_FILENAME}"

CACHE_FILE = os.path.join(PROJECT_ROOT, ".moroai", "ollama_url.txt")
CACHE_TTL_SECONDS = 60

_last_check = 0.0
_last_url = ""
_last_error: Optional[str] = None


def fetch_url_from_gist(timeout: int = 15) -> Optional[str]:
    try:
        req = urllib.request.Request(
            RAW_URL,
            headers={"User-Agent": "MOROAI/0.1"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8").strip()
        if content and content.startswith("http"):
            return content
        return None
    except Exception:
        return None


def _read_cache() -> Optional[str]:
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            url = f.read().strip()
        return url if url.startswith("http") else None
    except Exception:
        return None


def _write_cache(url: str) -> None:
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        f.write(url)


def get_url(force: bool = False) -> str:
    global _last_check, _last_url, _last_error
    now = time.time()
    cache_is_stale = (now - _last_check) > CACHE_TTL_SECONDS

    if force or cache_is_stale or not _last_url:
        _last_check = now
        fetched = fetch_url_from_gist()
        if fetched:
            if fetched != _last_url:
                _last_url = fetched
                _write_cache(fetched)
            _last_error = None
            return _last_url
        else:
            _last_error = "fetch failed"
            cached = _read_cache()
            if cached:
                _last_url = cached
                return cached

    return _last_url


def sync(force: bool = True) -> Dict[str, object]:
    global _last_url, _last_error
    previous = _last_url or _read_cache() or ""
    new_url = get_url(force=force)
    return {
        "url": new_url,
        "previous": previous,
        "changed": (new_url != previous),
        "error": _last_error,
    }


def status() -> Dict[str, object]:
    return {
        "url": _last_url,
        "cache": _read_cache(),
        "last_check": _last_check,
        "error": _last_error,
        "gist_id": GIST_ID,
    }


if __name__ == "__main__":
    print("Gist ID  :", GIST_ID)
    print("Raw URL  :", RAW_URL)
    print("Cache    :", CACHE_FILE)
    print()

    print("Fetching from Gist...")
    result = sync(force=True)
    print(f"  URL     : {result['url']}")
    print(f"  Changed : {result['changed']}")
    print(f"  Error   : {result['error']}")
    print()

    if result["url"]:
        print("Testing reachability...")
        try:
            req = urllib.request.Request(
                f"{result['url']}/api/tags",
                headers={"User-Agent": "MOROAI/0.1"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    print("  OK Ollama is reachable via this URL")
                else:
                    print(f"  WARN HTTP {resp.status}")
        except Exception as e:
            print(f"  FAIL Not reachable: {type(e).__name__}: {e}")
    else:
        print("No URL available")

    print("\nrendezvous self-test done.")
