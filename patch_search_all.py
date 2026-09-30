path = "cli.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# Add new imports
if "from tools.web_search import search_web" not in c:
    c = c.replace(
        "from tools.reddit import search_reddit",
        "from tools.reddit import search_reddit\nfrom tools.web_search import search_web\nfrom tools.youtube import search_youtube",
        1,
    )

# Find old /search block and replace it
old_block = '''            elif cmd == "/search":
                if not args:
                    print(c("Usage: /search <query>", YELLOW))
                else:
                    print(c(f"Searching Reddit: {args}", YELLOW))
                    results = search_reddit(args, limit=5)
                    if not results:
                        print(c("No results (rate limit or network).", DIM))
                    else:
                        for i, r in enumerate(results, 1):
                            print()
                            print(c(f"[{i}] r/{r['subreddit']}", BOLD))
                            print(f"    {r['title'][:90]}")
                            print(c(f"    {r['url']}", CYAN))
                            print(c(f"    by {r['author']} on {r['updated'][:10]}", DIM))'''

new_block = '''            elif cmd == "/search":
                if not args:
                    print(c("Usage: /search <query>", YELLOW))
                else:
                    print(c(f"Searching: {args}", YELLOW))

                    # 1. Web search
                    print()
                    print(c("── WEB ──", BOLD))
                    try:
                        wres = search_web(args, limit=5)
                        if not wres or wres[0].get("title") == "ERROR":
                            print(c("  (no web results)", DIM))
                        else:
                            for i, r in enumerate(wres, 1):
                                print(f"  {c(str(i), CYAN)}. {r['title'][:80]}")
                                print(c(f"     {r['url']}", DIM))
                    except Exception as e:
                        print(c(f"  (error: {e})", DIM))

                    # 2. YouTube search
                    print()
                    print(c("── YOUTUBE ──", BOLD))
                    try:
                        yres = search_youtube(args, limit=3)
                        if not yres or yres[0].get("title") == "ERROR":
                            print(c("  (no youtube results)", DIM))
                        else:
                            for i, r in enumerate(yres, 1):
                                print(f"  {c(str(i), CYAN)}. {r['title'][:80]}")
                                print(c(f"     {r['url']}  ({r.get('channel','?')})", DIM))
                    except Exception as e:
                        print(c(f"  (error: {e})", DIM))

                    # 3. Reddit search
                    print()
                    print(c("── REDDIT ──", BOLD))
                    try:
                        rres = search_reddit(args, limit=3)
                        if not rres:
                            print(c("  (no reddit results)", DIM))
                        else:
                            for i, r in enumerate(rres, 1):
                                print(f"  {c(str(i), CYAN)}. r/{r['subreddit']}: {r['title'][:70]}")
                                print(c(f"     {r['url']}", DIM))
                    except Exception as e:
                        print(c(f"  (error: {e})", DIM))'''

if old_block in c:
    c = c.replace(old_block, new_block, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("PATCHED")
else:
    print("OLD BLOCK NOT FOUND")
