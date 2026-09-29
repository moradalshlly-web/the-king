"""
tools/reddit.py
===============

Reddit search tool for MOROAI.

IMPORTANT: Reddit shut down unauthenticated .json access in May 2026
(returns 403). The .rss endpoints still work (200).

So we use RSS/Atom feeds instead of JSON.

Trade-offs:
    - Available: title, permalink, author, timestamp, selftext
    - NOT available: score, num_comments, upvote ratio

Inspiration (no code copied):
    - dev.to/listwright: measurement article on .json 403 vs .rss 200
    - mcp-reddit (namanxajmera): RSS pivot after May 2026
    - reddit-rss-mcp (ninjackster): dependency-free RSS approach
"""

import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional


USER_AGENT = "MOROAI/0.1 (private research tool by /u/moradalshlly)"

ATOM_NS = "{http://www.w3.org/2005/Atom}"

BASE_SEARCH_RSS = "https://www.reddit.com/search.rss"
BASE_SUB_RSS = "https://www.reddit.com/r/{sub}/.rss"


def _fetch(url: str, timeout: int = 20) -> Optional[str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        # Return None silently; caller can check
        return None
    except (urllib.error.URLError, TimeoutError):
        return None


def _parse_atom(xml_text: str) -> List[Dict]:
    """Parse Reddit's Atom RSS into a list of posts."""
    posts = []
    if not xml_text:
        return posts
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return posts

    for entry in root.findall(f"{ATOM_NS}entry"):
        title = entry.findtext(f"{ATOM_NS}title", default="").strip()
        link_el = entry.find(f"{ATOM_NS}link")
        url = link_el.get("href") if link_el is not None else ""
        author_el = entry.find(f"{ATOM_NS}author/{ATOM_NS}name")
        author = author_el.text if author_el is not None else ""
        updated = entry.findtext(f"{ATOM_NS}updated", default="")
        content_el = entry.find(f"{ATOM_NS}content")
        content = content_el.text if content_el is not None else ""
        if content:
            content = content[:500]

        # Extract subreddit from the URL
        subreddit = ""
        if "/r/" in url:
            try:
                subreddit = url.split("/r/")[1].split("/")[0]
            except IndexError:
                subreddit = ""

        posts.append({
            "title": title,
            "url": url,
            "author": author,
            "subreddit": subreddit,
            "updated": updated,
            "selftext": content,
        })
    return posts


def search_reddit(
    query: str,
    limit: int = 5,
    subreddit: Optional[str] = None,
    sort: str = "relevance",
    time_filter: str = "all",
) -> List[Dict]:
    """
    Search Reddit via RSS. Returns list of posts.

    Note: RSS does NOT expose score or num_comments.
    """
    limit = max(1, min(int(limit), 25))
    params = {
        "q": query,
        "limit": str(limit),
        "sort": sort,
        "t": time_filter,
    }

    if subreddit:
        url = BASE_SUB_RSS.format(sub=subreddit)
        # For subreddit RSS, no search; returns newest
        url += "?" + urllib.parse.urlencode({"limit": str(limit)})
    else:
        url = BASE_SEARCH_RSS + "?" + urllib.parse.urlencode(params)

    xml_text = _fetch(url)
    return _parse_atom(xml_text) if xml_text else []


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    import time

    print("Testing Reddit RSS search...\n")
    results = search_reddit("python asyncio", limit=3)
    print(f"Found {len(results)} posts\n")
    for i, r in enumerate(results, 1):
        print(f"[{i}] r/{r['subreddit']}")
        print(f"    {r['title'][:80]}")
        print(f"    {r['url']}")
        print(f"    by {r['author']} on {r['updated'][:10]}")
        print()

    if not results:
        print("⚠️  No results. Possible reasons:")
        print("   - Reddit rate-limited your IP (429)")
        print("   - Network issue")
        print("   - Try again in 30 seconds")
    else:
        print("✅ RSS search works.")

    # Wait to avoid rate limit
    time.sleep(3)
