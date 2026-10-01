"""
tools/wikipedia.py
==================

Wikipedia search tool for MOROAI.

Uses Wikipedia REST API + MediaWiki Action API (no key needed).
Supports 300+ languages including Arabic.

APIs:
    REST v1  : https://{lang}.wikipedia.org/api/rest_v1/
    Action   : https://{lang}.wikipedia.org/w/api.php
"""

import json
import urllib.request
import urllib.parse
import urllib.error
from typing import List, Dict, Optional


USER_AGENT = "MOROAI/0.1 (https://github.com/moradalshlly-web/the-king)"


def _fetch(url: str, timeout: int = 15) -> Optional[dict]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError:
        return None
    except Exception:
        return None


def search_wikipedia(query: str, lang: str = "ar", limit: int = 5) -> List[Dict]:
    """
    Search Wikipedia for pages matching a query.

    Args:
        query : search terms
        lang  : language code (ar, en, fr, ...)
        limit : max results (1-20)

    Returns list of:
        {title, description, url, pageid}
    """
    if not query.strip():
        return []

    limit = max(1, min(int(limit), 20))

    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": str(limit),
        "format": "json",
        "utf8": "1",
    }
    url = f"https://{lang}.wikipedia.org/w/api.php?{urllib.parse.urlencode(params)}"

    data = _fetch(url)
    if not data:
        return [{"error": "fetch failed"}]

    results = []
    for item in data.get("query", {}).get("search", []):
        title = item.get("title", "")
        results.append({
            "title": title,
            "snippet": _strip_html(item.get("snippet", "")),
            "pageid": item.get("pageid"),
            "url": f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
        })
    return results


def get_summary(title: str, lang: str = "ar") -> Optional[Dict]:
    """
    Get the summary of a Wikipedia article.

    Returns:
        {title, extract, url, thumbnail} or None
    """
    if not title.strip():
        return None

    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title.replace(' ', '_'))}"

    data = _fetch(url)
    if not data or data.get("type") == "disambiguation":
        return None

    thumb = data.get("thumbnail", {})
    return {
        "title": data.get("title", ""),
        "extract": data.get("extract", ""),
        "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
        "thumbnail": thumb.get("source", ""),
    }


def _strip_html(text: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "الثورة الفرنسية"

    print(f"Searching Arabic Wikipedia for: {q}\n")
    results = search_wikipedia(q, lang="ar", limit=3)
    for i, r in enumerate(results, 1):
        print(f"[{i}] {r.get('title','')}")
        print(f"    {r.get('snippet','')[:120]}")
        print(f"    {r.get('url','')}")
        print()

    if results and "pageid" in results[0]:
        print("--- Summary of first result ---")
        summary = get_summary(results[0]["title"], lang="ar")
        if summary:
            print(f"Title   : {summary['title']}")
            print(f"Extract : {summary['extract'][:300]}")
            print(f"URL     : {summary['url']}")
