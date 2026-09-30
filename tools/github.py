"""
tools/github.py
===============

GitHub search tool for MOROAI.

Uses GitHub's public REST API (no key needed for basic search).
Rate limit: 60 requests/hour unauthenticated, 10/min for search.

Optional: set GITHUB_TOKEN env var for 5000 req/hour.

Endpoints:
    GET /search/repositories?q=...
    GET /repos/{owner}/{repo}
"""

import json
import os
import urllib.request
import urllib.parse
import urllib.error
from typing import List, Dict, Optional


USER_AGENT = "MOROAI/0.1"
API_BASE = "https://api.github.com"


def _fetch(url: str, timeout: int = 20) -> Optional[dict]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    }
    token = os.getenv("GITHUB_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def search_repos(query: str, limit: int = 5,
                 sort: str = "stars") -> List[Dict]:
    """
    Search GitHub repositories.

    Args:
        query: search terms
        limit: max results (1-30)
        sort : stars | forks | updated

    Returns list of:
        {name, full_name, description, url, stars, forks,
         language, license, updated_at, topics}
    """
    if not query.strip():
        return []

    limit = max(1, min(int(limit), 30))

    params = {
        "q": query,
        "sort": sort,
        "order": "desc",
        "per_page": str(limit),
    }
    url = f"{API_BASE}/search/repositories?{urllib.parse.urlencode(params)}"

    data = _fetch(url)
    if not data or "_error" in data:
        return [{"error": data.get("_error", "unknown") if data else "no response"}]

    results = []
    for repo in data.get("items", []):
        license_info = repo.get("license") or {}
        results.append({
            "name": repo.get("name", ""),
            "full_name": repo.get("full_name", ""),
            "description": (repo.get("description") or "")[:300],
            "url": repo.get("html_url", ""),
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "language": repo.get("language") or "?",
            "license": license_info.get("spdx_id", "?") or "?",
            "updated_at": (repo.get("updated_at") or "")[:10],
            "topics": repo.get("topics", [])[:5],
        })

    return results


def repo_details(full_name: str) -> Dict:
    """
    Get detailed info about one repository.

    Args:
        full_name: "owner/repo"

    Returns dict with repo details, or {"error": "..."}.
    """
    if "/" not in full_name:
        return {"error": "Use format 'owner/repo'"}

    url = f"{API_BASE}/repos/{full_name}"
    data = _fetch(url)

    if not data or "_error" in data:
        return {"error": data.get("_error", "not found") if data else "no response"}

    license_info = data.get("license") or {}
    return {
        "name": data.get("name", ""),
        "full_name": data.get("full_name", ""),
        "description": data.get("description") or "",
        "url": data.get("html_url", ""),
        "stars": data.get("stargazers_count", 0),
        "forks": data.get("forks_count", 0),
        "open_issues": data.get("open_issues_count", 0),
        "language": data.get("language") or "?",
        "license": license_info.get("spdx_id", "?") or "?",
        "license_name": license_info.get("name", "?") or "?",
        "created_at": (data.get("created_at") or "")[:10],
        "updated_at": (data.get("updated_at") or "")[:10],
        "default_branch": data.get("default_branch", "main"),
        "topics": data.get("topics", [])[:10],
        "homepage": data.get("homepage") or "",
    }


def top_alternatives(full_name: str, limit: int = 5) -> List[Dict]:
    """
    Find similar repositories by topic + language.
    """
    details = repo_details(full_name)
    if "error" in details:
        return [{"error": details["error"]}]

    topics = details.get("topics", [])
    language = details.get("language", "")

    if topics:
        query = " ".join(topics[:2])
    elif language and language != "?":
        query = f"language:{language}"
    else:
        query = details.get("name", "")

    results = search_repos(query, limit=limit + 5)
    # Remove the original repo from results
    filtered = [r for r in results if r.get("full_name") != full_name]
    return filtered[:limit]


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "image generation"
    print(f"Searching GitHub for: {q}\n")

    results = search_repos(q, limit=5)
    for i, r in enumerate(results, 1):
        if "error" in r:
            print(f"[{i}] ERROR: {r['error']}")
            continue
        print(f"[{i}] {r['full_name']} ({r['stars']} ⭐)")
        print(f"    {r['description'][:100]}")
        print(f"    Language: {r['language']}  License: {r['license']}")
        print(f"    {r['url']}")
        print()

    print(f"Found {len(results)} repos")
