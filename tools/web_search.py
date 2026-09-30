"""
tools/web_search.py
===================

Web search tool for MOROAI.

Uses DuckDuckGo's HTML endpoint (free, no API key).
Aggregates results from Google, Bing, and more.

Inspiration (no code copied):
    - duckduckgo-search pattern (public HTML)
    - Stack Overflow community examples
    - BeautifulSoup official docs
"""

import urllib.request
import urllib.parse
import urllib.error
import time
from typing import List, Dict

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)

DDG_HTML_URL = "https://html.duckduckgo.com/html/"


def _fetch(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ar,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def search_web(query: str, limit: int = 10) -> List[Dict[str, str]]:
    """
    Search the web via DuckDuckGo HTML.

    Returns list of:
        {title, url, snippet}
    """
    if BeautifulSoup is None:
        return [{"title": "ERROR", "url": "", "snippet": "beautifulsoup4 not installed"}]

    if not query.strip():
        return []

    params = urllib.parse.urlencode({"q": query, "kl": "ar-ar"})
    url = f"{DDG_HTML_URL}?{params}"

    try:
        html = _fetch(url)
    except Exception as e:
        return [{"title": "ERROR", "url": "", "snippet": f"Network: {e}"}]

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        return [{"title": "ERROR", "url": "", "snippet": f"Parse: {e}"}]

    results = []
    for div in soup.find_all("div", class_="result"):
        title_el = div.find("a", class_="result__a")
        snippet_el = div.find("a", class_="result__snippet")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        # DDG uses redirect links — extract actual URL
        if href.startswith("//duckduckgo.com/l/?uddg="):
            try:
                href = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
            except Exception:
                pass
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        results.append({"title": title, "url": href, "snippet": snippet})
        if len(results) >= limit:
            break

    return results


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "python asyncio"
    print(f"Searching: {q}\n")
    results = search_web(q, limit=5)
    for i, r in enumerate(results, 1):
        print(f"[{i}] {r['title']}")
        print(f"    {r['url']}")
        print(f"    {r['snippet'][:120]}")
        print()
    print(f"Found {len(results)} results")
