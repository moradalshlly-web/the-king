path = "cli.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

if "search_history.list_entries" in c:
    print("ALREADY DONE")
    raise SystemExit(0)

# 1. Import
if "from brain import search_history" not in c:
    c = c.replace(
        "from brain.vision import vision_summary",
        "from brain.vision import vision_summary\nfrom brain import search_history",
        1,
    )

# 2. Replace the old /history command
old = '''            # History
            elif cmd == "/history":
                print()
                print(c("─── LAST 20 MESSAGES ───", BOLD))
                for i, m in enumerate(messages_log[-20:], 1):
                    role = c(m.get("role", "?").upper(), CYAN if m.get("role")=="user" else GREEN)
                    txt = m.get("text", "")[:100]
                    print(f"  {i}. [{role}] {txt}")
                print()'''

new = '''            # History (search history, with subcommands)
            elif cmd == "/history":
                parts = args.split(maxsplit=1)
                sub = parts[0].lower() if parts else ""
                subargs = parts[1] if len(parts) > 1 else ""

                if sub == "show":
                    if not subargs:
                        print(c("Usage: /history show <id>", YELLOW))
                    else:
                        item = search_history.get_entry(subargs)
                        if not item:
                            print(c(f"Not found: {subargs}", RED))
                        else:
                            print()
                            print(c(f"─── ENTRY: {item['id']} ───", BOLD))
                            print(f"Tool        : {item['tool']}")
                            print(f"Query       : {item['args'].get('query', '?')}")
                            print(f"Created     : {item['created_at'][:19]}")
                            print(f"Updated     : {item['updated_at'][:19]}")
                            print(f"Refresh cnt : {item['refresh_count']}")
                            print()

                elif sub == "delete":
                    if not subargs:
                        print(c("Usage: /history delete <id>", YELLOW))
                    else:
                        item = search_history.get_entry(subargs)
                        if not item:
                            print(c(f"Not found: {subargs}", RED))
                        else:
                            print()
                            print(c("─── CONFIRM DELETE ───", YELLOW))
                            print(f"Entry : {item['id']}")
                            print(f"Query : {item['args'].get('query', '?')}")
                            try:
                                ans = input(c("Delete this entry? [y/N]: ", YELLOW)).strip().lower()
                            except (EOFError, KeyboardInterrupt):
                                ans = "n"
                            if ans == "y":
                                if search_history.delete_entry(subargs):
                                    print(c("✅ Deleted.", GREEN))
                                else:
                                    print(c("❌ Failed.", RED))
                            else:
                                print(c("Cancelled.", DIM))

                elif sub == "clear":
                    st = search_history.stats()
                    print()
                    print(c("─── CONFIRM CLEAR ALL ───", YELLOW))
                    print(f"Entries to delete: {st['total']}")
                    try:
                        ans = input(c("Delete ALL history? [y/N]: ", YELLOW)).strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        ans = "n"
                    if ans == "y":
                        n = search_history.clear_all()
                        print(c(f"✅ Cleared {n} entries.", GREEN))
                    else:
                        print(c("Cancelled.", DIM))

                elif sub == "update":
                    if not subargs:
                        print(c("Usage: /history update <id>", YELLOW))
                    else:
                        item = search_history.get_entry(subargs)
                        if not item:
                            print(c(f"Not found: {subargs}", RED))
                        else:
                            from brain.preprocessor import execute_preempt
                            from brain import search_cache
                            print(c(f"Refreshing: {item['args'].get('query','?')}", DIM))
                            search_cache.clear()
                            call = {"tool": item["tool"], "args": item["args"]}
                            execute_preempt(call)
                            print(c("✅ Refreshed.", GREEN))

                else:
                    entries = search_history.list_entries(limit=50)
                    st = search_history.stats()
                    print()
                    print(c(f"─── SEARCH HISTORY ({st['total']} entries, {st['stale']} stale) ───", BOLD))
                    if not entries:
                        print(c("  (no entries yet)", DIM))
                    else:
                        for e in entries:
                            mark = c("⟳", YELLOW) if search_history.needs_refresh(e["id"]) else " "
                            print(f"  {mark} {c(e['id'], CYAN)}  {e['tool']:15s}  {e['query'][:40]}")
                    print()
                    print(c("  Commands: /history show <id> | delete <id> | update <id> | clear", DIM))
                    print()'''

if old in c:
    c = c.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("PATCHED")
else:
    print("ANCHOR NOT FOUND")
