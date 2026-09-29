path = "cli.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# 1. Import reddit tool
if "from tools.reddit import search_reddit" not in c:
    c = c.replace(
        "from brain.reflection import Reflector",
        "from brain.reflection import Reflector\nfrom tools.reddit import search_reddit",
        1,
    )

# 2. Add /search command
old = '''            elif cmd == "/memory":'''
new = '''            elif cmd == "/search":
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
                            print(c(f"    by {r['author']} on {r['updated'][:10]}", DIM))
            elif cmd == "/memory":'''

if old not in c:
    print("CMDS BLOCK NOT FOUND")
else:
    c = c.replace(old, new, 1)
    print("CMDS ADDED")

# 3. Update /help
old_help = '''    print("  /memory            memory stats")'''
new_help = '''    print("  /memory            memory stats")
    print("  /search <query>    search Reddit via RSS")'''

if old_help in c:
    c = c.replace(old_help, new_help, 1)
    print("HELP UPDATED")

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("DONE")
