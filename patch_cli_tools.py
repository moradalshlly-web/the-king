path = "cli.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# 1. Import tools
if "from tools.file_ops import FileOps" not in c:
    c = c.replace(
        "from tools.reddit import search_reddit",
        "from tools.reddit import search_reddit\nfrom tools.file_ops import FileOps\nfrom tools.shell import ShellOps",
        1,
    )

# 2. Init tools after brain
if "file_ops = FileOps()" not in c:
    c = c.replace(
        "    reflector = Reflector(brain)",
        "    reflector = Reflector(brain)\n    file_ops = FileOps()\n    shell_ops = ShellOps()",
        1,
    )

# 3. Add commands
old = '''            elif cmd == "/memory":'''
new = '''            elif cmd == "/ls":
                r = file_ops.list_dir(args or ".", recursive=False)
                if not r["success"]:
                    print(c(f"Error: {r['error']}", RED))
                else:
                    for item in r["items"]:
                        print(f"  {item}")
            elif cmd == "/cat":
                if not args:
                    print(c("Usage: /cat <file>", YELLOW))
                else:
                    r = file_ops.read_file(args)
                    if r["success"]:
                        print(r["content"])
                    else:
                        print(c(f"Error: {r['error']}", RED))
            elif cmd == "/run":
                if not args:
                    print(c("Usage: /run <command>", YELLOW))
                else:
                    print(c(f"$ {args}", DIM))
                    r = shell_ops.run(args)
                    if r["blocked"]:
                        print(c(f"⛔ Blocked: {r['error']}", RED))
                    elif r["success"]:
                        print(r["stdout"])
                        if r["stderr"]:
                            print(c(r["stderr"], YELLOW))
                    else:
                        if r["stdout"]:
                            print(r["stdout"])
                        print(c(f"Exit {r['exit_code']}: {r['stderr'] or r['error']}", RED))
            elif cmd == "/memory":'''

if old not in c:
    print("NOT FOUND")
else:
    c = c.replace(old, new, 1)
    print("ADDED")

with open(path, "w", encoding="utf-8") as f:
    f.write(c)
print("DONE")
