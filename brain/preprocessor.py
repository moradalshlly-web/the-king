"""
brain/preprocessor.py
=====================

Pre-processor that FORCES tool usage before sending to the LLM.

Problem:
    Free LLMs often ignore tool-usage instructions and answer from memory.

Solution:
    Detect keywords in the user's message BEFORE the LLM sees it.
    Execute the right tool automatically.
    Inject the results into the prompt.

This guarantees tool usage regardless of LLM behavior.
"""

import re
from brain import search_cache
from brain import search_history
from typing import Optional, Dict, Any, List


# ============================================================
# Keyword patterns (Arabic + English)
# ============================================================

PATTERNS = {
    "web_search": [
        r"ابحث\s+في\s+الويب",
        r"ابحث\s+لي\s+في\s+الويب",
        r"ابحث\s+في\s+الإنترنت",
        r"ابحث\s+لي\s+عن",
        r"ابحث\s+عن",
        r"\bsearch\s+(the\s+)?web\b",
        r"\bgoogle\s+",
        r"\blook\s+up\b",
        r"^search\s+",
    ],
    "youtube_search": [
        r"ابحث\s+في\s+يوتيوب",
        r"فيديو\s+على\s+يوتيوب",
        r"شرح\s+فيديو",
        r"\byoutube\s+",
        r"\bsearch\s+youtube\b",
        r"فيديو\s+يشرح",
    ],
    "wikipedia_search": [
        r"ابحث\s+في\s+ويكيبيديا",
        r"ابحث\s+في\s+wikipedia",
        r"\bwikipedia\s+search\b",
        r"ويكيبيديا\s+عن",
    ],
    "stackoverflow_search": [
        r"ابحث\s+في\s+stackoverflow",
        r"ابحث\s+في\s+ستاك",
        r"ابحث\s+في\s+stack\s+overflow",
        r"\bstackoverflow\s+search\b",
        r"سؤال\s+برمجي",
        r"حل\s+برمجي",
    ],
    "github_search": [
        r"ابحث\s+في\s+github",
        r"ابحث\s+في\s+جيتهاب",
        r"\bgithub\s+search\b",
        r"مشاريع\s+مفتوحة",
        r"مشروع\s+مفتوح\s+المصدر",
    ],
    "search_reddit": [
        r"ابحث\s+في\s+ريديت",
        r"ابحث\s+في\s+reddit",
        r"\bsearch\s+reddit\b",
        r"مناقشات\s+ريديت",
    ],
    "read_file": [
        r"^اقرأ\s+(لي\s+)?ملف\s+",
        r"^اقرأ\s+(لي\s+)?",
        r"\bread\s+file\b",
        r"\bshow\s+file\b",
    ],
    "list_dir": [
        r"^اعرض\s+(لي\s+)?(قائمة\s+)?ملفات\s+",
        r"^اعرض\s+(لي\s+)?مجلد\s+",
        r"^ls\s+",
        r"\blist\s+dir\b",
        r"\blist\s+files\b",
    ],
}


# ============================================================
# Argument extractors
# ============================================================

def _extract_after_verb(text: str, verbs: List[str]) -> str:
    """Extract the argument after a verb like 'ابحث عن X'."""
    for v in verbs:
        if v in text:
            parts = text.split(v, 1)
            if len(parts) > 1:
                return parts[1].strip()
    return text


def _extract_query(msg: str) -> str:
    """Extract the search query from a message."""
    # Remove common prefixes
    prefixes = [
        "ابحث لي في الويب عن ",
        "ابحث لي في الويب عن",
        "ابحث في الويب عن ",
        "ابحث في الويب عن",
        "ابحث لي في الإنترنت عن ",
        "ابحث لي في الإنترنت عن",
        "ابحث لي في يوتيوب عن ",
        "ابحث في يوتيوب عن ",
        "ابحث في ريديت عن ",
        "ابحث في reddit عن ",
        "ابحث لي عن ",
        "ابحث عن ",
        "search the web for ",
        "search youtube for ",
        "search reddit for ",
        "ابحث في github عن ",
        "ابحث في جيتهاب عن ",
        "ابحث في جيت هاب عن ",
        "ابحث في stackoverflow عن ",
        "ابحث في ستاك عن ",
        "ابحث في ويكيبيديا عن ",
        "ابحث في wikipedia عن ",
        "search wikipedia for ",
        "search stackoverflow for ",
        "search github for ",
        "search web for ",
        "google ",
        "youtube ",
        "look up ",
        "search ",
        # read_file
        "اقرأ لي ملف ",
        "اقرأ ملف ",
        "اقرأ لي ",
        "اقرأ ",
        "read file ",
        "read ",
        "show file ",
        # list_dir
        "اعرض لي ملفات مجلد ",
        "اعرض ملفات مجلد ",
        "اعرض لي ملفات ",
        "اعرض ملفات ",
        "اعرض لي مجلد ",
        "اعرض مجلد ",
        "اعرض لي ",
        "اعرض ",
        "list dir ",
        "list files ",
        "ls ",
    ]
    q = msg.strip()
    for p in prefixes:
        if q.lower().startswith(p.lower()):
            q = q[len(p):].strip()
            break

    # Strip surrounding quotes
    q = q.strip('"').strip("'").strip()

    # Strip trailing punctuation
    q = re.sub(r"[؟?!.]+$", "", q).strip()

    return q


# ============================================================
# Core: detect + route
# ============================================================

def detect_tool(message: str) -> Optional[Dict[str, Any]]:
    """
    Detect which tool (if any) should be used for this message.

    Returns:
        {"tool": "<name>", "args": {...}}  OR  None
    """
    if not message or not message.strip():
        return None

    msg = message.strip()
    msg_lower = msg.lower()

    # Priority checks (specific phrases before generic "ابحث عن")
    github_phrases = ["مشاريع مفتوحة", "مشروع مفتوح", "open source project", "github.com"]
    for kw in github_phrases:
        if kw in msg_lower:
            query = _extract_query(msg)
            if not query or len(query) < 3:
                query = msg
            return {"tool": "github_search", "args": {"query": query, "limit": 5}}

    for tool_name, patterns in PATTERNS.items():
        for pat in patterns:
            if re.search(pat, msg_lower, re.IGNORECASE):
                query = _extract_query(msg)
                if not query:
                    return None

                if tool_name == "web_search":
                    return {"tool": "web_search", "args": {"query": query, "limit": 5}}
                if tool_name == "youtube_search":
                    return {"tool": "youtube_search", "args": {"query": query, "limit": 3}}
                if tool_name == "search_reddit":
                    return {"tool": "search_reddit", "args": {"query": query, "limit": 3}}
                if tool_name == "github_search":
                    return {"tool": "github_search", "args": {"query": query, "limit": 5}}
                if tool_name == "stackoverflow_search":
                    return {"tool": "stackoverflow_search", "args": {"query": query, "limit": 5}}
                if tool_name == "wikipedia_search":
                    return {"tool": "wikipedia_search", "args": {"query": query, "limit": 5}}
                if tool_name == "read_file":
                    return {"tool": "read_file", "args": {"path": query}}
                if tool_name == "list_dir":
                    return {"tool": "list_dir", "args": {"path": query or "."}}

    return None


# ============================================================
# Execute + format
# ============================================================

def execute_preempt(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the detected tool. Never raises. Uses cache when possible."""
    tool = tool_call.get("tool")
    args = tool_call.get("args", {})

    # Check cache first
    try:
        cached = search_cache.get(tool, args)
        if cached is not None:
            cached["_from_cache"] = True
            # ALSO update history for cached results
            try:
                search_history.add_or_update(tool, args, cached)
            except Exception:
                pass
            return cached
    except Exception:
        pass

    # Execute the tool
    result = _execute_preempt_uncached(tool_call)

    # Save to cache if successful
    try:
        if result.get("success"):
            search_cache.put(tool, args, result)
    except Exception:
        pass

    # Save to permanent history if successful
    try:
        if result.get("success"):
            search_history.add_or_update(tool, args, result)
    except Exception:
        pass

    return result


def _execute_preempt_uncached(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    """Execute without cache. Never raises."""
    tool = tool_call.get("tool")
    args = tool_call.get("args", {})

    try:
        if tool == "web_search":
            from tools.web_search import search_web
            results = search_web(args["query"], limit=args.get("limit", 5))
            return {"success": True, "results": results, "kind": "web"}

        if tool == "youtube_search":
            from tools.youtube import search_youtube
            results = search_youtube(args["query"], limit=args.get("limit", 3))
            return {"success": True, "results": results, "kind": "youtube"}

        if tool == "search_reddit":
            from tools.reddit import search_reddit
            results = search_reddit(args["query"], limit=args.get("limit", 3))
            return {"success": True, "results": results, "kind": "reddit"}

        if tool == "github_search":
            from tools.github import search_repos
            results = search_repos(args["query"], limit=args.get("limit", 5))
            return {"success": True, "results": results, "kind": "github"}

        if tool == "stackoverflow_search":
            from tools.stack_exchange import search_stackexchange
            results = search_stackexchange(args["query"], limit=args.get("limit", 5))
            return {"success": True, "results": results, "kind": "stack"}

        if tool == "wikipedia_search":
            from tools.wikipedia import search_wikipedia
            results = search_wikipedia(args["query"], limit=args.get("limit", 5))
            return {"success": True, "results": results, "kind": "wiki"}

        if tool == "read_file":
            from tools.file_ops import FileOps
            fops = FileOps()
            r = fops.read_file(args["path"])
            return {"success": r.get("success", False), "content": r.get("content", ""), "kind": "file"}

        if tool == "list_dir":
            from tools.file_ops import FileOps
            fops = FileOps()
            r = fops.list_dir(args.get("path", "."))
            return {"success": r.get("success", False), "items": r.get("items", []), "kind": "dir"}

    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    return {"success": False, "error": "unknown tool"}


def format_results(result: Dict[str, Any]) -> str:
    """Format the tool results as text to inject into the prompt."""
    if not result.get("success"):
        return f"(preprocessor: tool failed — {result.get('error','unknown')})"

    kind = result.get("kind")

    if kind == "web":
        lines = ["[نتائج البحث في الويب]"]
        for i, r in enumerate(result.get("results", [])[:5], 1):
            lines.append(f"{i}. {r.get('title','')}")
            lines.append(f"   {r.get('url','')}")
            if r.get("snippet"):
                lines.append(f"   {r['snippet'][:150]}")
        return "\n".join(lines)

    if kind == "youtube":
        lines = ["[نتائج البحث في يوتيوب]"]
        for i, r in enumerate(result.get("results", [])[:3], 1):
            lines.append(f"{i}. {r.get('title','')}")
            lines.append(f"   {r.get('url','')}")
            lines.append(f"   القناة: {r.get('channel','?')}  المدة: {r.get('duration','?')}s")
        return "\n".join(lines)

    if kind == "wiki":
        lines = ["[نتائج ويكيبيديا]"]
        for i, r in enumerate(result.get("results", [])[:5], 1):
            if "error" in r:
                continue
            lines.append(f"{i}. {r.get('title','')}")
            if r.get('snippet'):
                lines.append(f"   {r['snippet'][:150]}")
            lines.append(f"   {r.get('url','')}")
        return "\n".join(lines)

    if kind == "stack":
        lines = ["[نتائج Stack Overflow]"]
        for i, r in enumerate(result.get("results", [])[:5], 1):
            if "error" in r:
                continue
            lines.append(f"{i}. {r.get('title','')}")
            lines.append(f"   Score: {r.get('score',0)}  Answers: {r.get('answer_count',0)}")
            lines.append(f"   Tags: {', '.join(r.get('tags',[])[:5])}")
            lines.append(f"   {r.get('url','')}")
        return "\n".join(lines)

    if kind == "github":
        lines = ["[نتائج البحث في GitHub]"]
        for i, r in enumerate(result.get("results", [])[:5], 1):
            if "error" in r:
                continue
            lines.append(f"{i}. {r.get('full_name','')} ({r.get('stars',0)} stars)")
            lines.append(f"   {r.get('description','')[:150]}")
            lines.append(f"   Language: {r.get('language','?')}  License: {r.get('license','?')}")
            lines.append(f"   {r.get('url','')}")
        return "\n".join(lines)

    if kind == "reddit":
        lines = ["[نتائج البحث في Reddit]"]
        for i, r in enumerate(result.get("results", [])[:3], 1):
            lines.append(f"{i}. r/{r.get('subreddit','')}: {r.get('title','')}")
            lines.append(f"   {r.get('url','')}")
        return "\n".join(lines)

    if kind == "file":
        return f"[محتوى الملف]\n{result.get('content','')[:2000]}"

    if kind == "dir":
        items = result.get("items", [])
        return "[محتويات المجلد]\n" + "\n".join(f"  {i}" for i in items[:50])

    return "(unknown result kind)"


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    tests = [
        "ابحث لي في الويب عن Python 3.14",
        "ابحث في يوتيوب عن python asyncio",
        "ابحث في ريديت عن asyncio",
        "search the web for latest Python",
        "اقرأ لي ملف brain/core.py",
        "اعرض لي ملفات مجلد tools",
        "مرحبا كيف حالك",  # should NOT detect anything
    ]
    for t in tests:
        result = detect_tool(t)
        print(f"Input : {t}")
        print(f"Output: {result}")
        print()
