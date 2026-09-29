path = "cli.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# 1. Import Reflector
if "from brain.reflection import Reflector" not in c:
    c = c.replace(
        "from brain.session import SessionLifecycle",
        "from brain.session import SessionLifecycle\nfrom brain.reflection import Reflector",
        1,
    )

# 2. Init reflector after brain
if "reflector = Reflector(brain)" not in c:
    c = c.replace(
        "    session = SessionLifecycle()",
        "    reflector = Reflector(brain)\n    session = SessionLifecycle()",
        1,
    )

# 3. Add /reflect and /lessons commands
old_cmds = """            elif cmd == "/memory":
                print(f"Interactions: {c(str(brain.memory.count()), CYAN)}")"""

new_cmds = """            elif cmd == "/memory":
                print(f"Interactions: {c(str(brain.memory.count()), CYAN)}")
                stats = brain.learning.count()
                print(f"Episodes    : {c(str(stats['episodes']), CYAN)}")
                print(f"Lessons     : {c(str(stats['lessons']), CYAN)}")
            elif cmd == "/reflect":
                n = 5
                if args.strip().isdigit():
                    n = int(args.strip())
                print(c(f"Reflecting on last {n} episode(s)...", YELLOW))
                lessons = reflector.reflect_last(n)
                if not lessons:
                    print(c("No lessons extracted.", DIM))
                else:
                    for l in lessons:
                        print(c(f"  [{l['category']}] {l['rule']}", GREEN))
            elif cmd == "/lessons":
                rows = brain.learning.search_lessons(args or "the", limit=10)
                if not rows:
                    print(c("No lessons yet. Use /reflect.", DIM))
                else:
                    for r in rows:
                        print(f"  {c('[' + str(r['id']) + ']', CYAN)} "
                              f"{c(r['category'], MAGENTA)}  {r['rule']}")"""

if old_cmds not in c:
    print("CMDS BLOCK NOT FOUND")
else:
    c = c.replace(old_cmds, new_cmds, 1)

# 4. Update /help
old_help = '''    print("  /memory            memory stats")'''
new_help = '''    print("  /memory            memory stats")
    print("  /reflect [N]       extract lessons from last N episodes")
    print("  /lessons [query]   search lessons learned")'''

if old_help in c:
    c = c.replace(old_help, new_help, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("CLI PATCH DONE")
