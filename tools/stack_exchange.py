"""
tools/stack_exchange.py
=======================

Stack Exchange search tool for MOROAI.

Public API v2.3 (no key needed for 300 req/day).
Optional key from stackapps.com raises to 10,000/day.

Note: API always returns gzip-compressed JSON.
"""

import os
import json
import gzip
import re
import urllib.request
import urllib.parse
import urllib.error
from typing import List, Dict, Optional


API_BASE = "https://api.stackexchange.com/2.3"
USER_AGENT = "MOROAI/0.1"

SITES = {
    "stackoverflow": "stackoverflow",
    "serverfault": "serverfault",
    "askubuntu": "askubuntu",
    "superuser": "superuser",
    "math": "math",
    "physics": "physics",
    "security": "security",
    "unix": "unix",
}


def _fetch(url: str, timeout: int = 20) -> Optional[dict]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            # Stack Exchange returns gzip by default
            try:
                raw = gzip.decompress(raw)
            except (OSError, gzip.BadGzipFile):
                pass
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def search_stackexchange(
    query: str,
    site: str = "stackoverflow",
    limit: int = 5,
    sort: str = "relevance",
) -> List[Dict]:
    """Search Stack Exchange for questions."""
    if not query.strip():
        return []

    limit = max(1, min(int(limit), 30))

    params = {
        "q": query,
        "site": SITES.get(site, site),
        "pagesize": str(limit),
        "sort": sort,
        "order": "desc",
        "filter": "withbody",
    }
    api_key = os.getenv("STACKEXCHANGE_KEY", "").strip()
    if api_key:
        params["key"] = api_key

    url = f"{API_BASE}/search/advanced?{urllib.parse.urlencode(params)}"

    data = _fetch(url)
    if not data or "_error" in data:
        err = data.get("_error", "unknown") if data else "no response"
        return [{"error": err}]

    results = []
    for item in data.get("items", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "score": item.get("score", 0),
            "answer_count": item.get("answer_count", 0),
            "is_answered": item.get("is_answered", False),
            "tags": item.get("tags", []),
            "body_preview": _strip_html(item.get("body", ""))[:300],
        })
    return results


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "parse json python"
    print(f"Searching Stack Overflow: {q}\n")
    results = search_stackexchange(q, limit=5)
    for i, r in enumerate(results, 1):
        if "error" in r:
            print(f"[{i}] ERROR: {r['error']}")
            continue
        print(f"[{i}] {r['title']}")
        print(f"    Score: {r['score']}  Answers: {r['answer_count']}")
        print(f"    Tags: {', '.join(r['tags'][:5])}")
        print(f"    {r['url']}")
        print()
    print(f"Found {len(results)} questions")
