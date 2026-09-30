path = "brain/tool_loop.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

changes = 0

# 1. Add youtube import if missing
if "from tools.youtube import search_youtube" not in c:
    c = c.replace(
        "    from tools.web_search import search_web",
        "    from tools.web_search import search_web\n    from tools.youtube import search_youtube",
        1,
    )
    changes += 1

# 2. Add TR.register blocks before "_registered = True"
marker = "    _registered = True"
if marker in c and 'name="web_search"' not in c:
    new_block = '''    # web_search
    TR.register(
        name="web_search",
        description="Search the web via DuckDuckGo for information.",
        params='query="<text>" limit=5',
        func=lambda query, limit=5: {
            "success": True,
            "result": _format_web(search_web(query, int(limit))),
        },
    )

    # youtube_search
    TR.register(
        name="youtube_search",
        description="Search YouTube for videos.",
        params='query="<text>" limit=3',
        func=lambda query, limit=3: {
            "success": True,
            "result": _format_youtube(search_youtube(query, int(limit))),
        },
    )

    _registered = True'''
    c = c.replace(marker, new_block, 1)
    changes += 1

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print(f"FIXED ({changes} changes)")
