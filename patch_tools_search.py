path = "brain/tool_loop.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# Add imports
old = "    from tools.reddit import search_reddit"
new = """    from tools.reddit import search_reddit
    from tools.web_search import search_web
    from tools.youtube import search_youtube"""

if old in c and "search_web" not in c:
    c = c.replace(old, new, 1)

# Add new tool registrations before "_registered = True"
old2 = "    _registered = True"
new2 = """    # web_search
    TR.register(
        name="web_search",
        description="Search the web (Google/Bing via DuckDuckGo) for information, docs, or answers.",
        params='query="<text>" limit=5',
        func=lambda query, limit=5: {
            "success": True,
            "result": _format_web(search_web(query, int(limit))),
        },
    )

    # youtube_search
    TR.register(
        name="youtube_search",
        description="Search YouTube for videos on any topic (tutorials, music, courses).",
        params='query="<text>" limit=3',
        func=lambda query, limit=3: {
            "success": True,
            "result": _format_youtube(search_youtube(query, int(limit))),
        },
    )

    _registered = True"""

if old2 in c and "web_search" not in c:
    c = c.replace(old2, new2, 1)

# Add formatters before "def run_with_tools"
old3 = "def run_with_tools("
new3 = '''def _format_web(results) -> str:
    if not results:
        return "(no results)"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   {r['url']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet'][:150]}")
    return "\\n".join(lines)


def _format_youtube(results) -> str:
    if not results:
        return "(no videos)"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   {r['url']}")
        lines.append(f"   by {r.get('channel','?')}  ({r.get('duration','?')}s)")
    return "\\n".join(lines)


def run_with_tools('''

if old3 in c and "_format_web" not in c:
    c = c.replace(old3, new3, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("PATCHED" if "web_search" in c else "FAILED")
