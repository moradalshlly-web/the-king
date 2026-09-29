path = "cli.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# 1. Import Builder
if "from brain.builder import Builder" not in c:
    c = c.replace(
        "from brain.tool_loop import run_with_tools",
        "from brain.tool_loop import run_with_tools\nfrom brain.builder import Builder",
        1,
    )

# 2. Init builder after reflector
if "builder = Builder(brain)" not in c:
    c = c.replace(
        "    reflector = Reflector(brain)",
        "    reflector = Reflector(brain)\n    builder = Builder(brain)",
        1,
    )

# 3. Add /build command
old = '''            elif cmd == "/tools":'''
new = '''            elif cmd == "/build":
                # Format: /build [--yes] <path> <description>
                parts = args.split(maxsplit=2)
                auto_yes = False
                if parts and parts[0] == "--yes":
                    auto_yes = True
                    parts = parts[1:]
                if len(parts) < 2:
                    print(c("Usage: /build [--yes] <path> <description>", YELLOW))
                    print(c("Example: /build output/login.html صفحة تسجيل دخول فاخرة", DIM))
                else:
                    target = parts[0]
                    desc = parts[1] + ((" " + parts[2]) if len(parts) > 2 else "")
                    print(c(f"Building: {target}", YELLOW))
                    print(c(f"Description: {desc}", DIM))
                    print(c("Generating (this may take 5-20s)...", DIM))
                    res = builder.generate(target, desc)
                    if not res["success"]:
                        print(c(f"❌ Failed: {res['error']}", RED))
                    else:
                        content = res["content"]
                        print()
                        print(c("─" * 50, DIM))
                        print(c("PREVIEW (first 800 chars):", BOLD))
                        print(content[:800])
                        if len(content) > 800:
                            print(c(f"... ({len(content) - 800} more chars)", DIM))
                        print(c("─" * 50, DIM))
                        print(f"Size: {res['bytes']} bytes  |  "
                              f"{res['provider']} · {res['model']} · "
                              f"{res['latency_ms']:.0f}ms")
                        # Confirmation
                        if auto_yes:
                            confirm = "y"
                        else:
                            try:
                                confirm = input("Write this file? [y/N]: ").strip().lower()
                            except (EOFError, KeyboardInterrupt):
                                confirm = "n"
                        if confirm == "y":
                            # Checkpoint first
                            h = brain.checkpoints.create(f"Before building {target}")
                            if h:
                                print(c(f"Checkpoint: {h[:8]}", GREEN))
                            r = builder.write(target, content)
                            if r["success"]:
                                print(c(f"✅ Written: {r['path']} ({r['bytes_written']} bytes)", GREEN))
                            else:
                                print(c(f"❌ Write failed: {r['error']}", RED))
                        else:
                            print(c("Cancelled (file not written).", DIM))
            elif cmd == "/tools":'''

if old not in c:
    print("NOT FOUND: /tools anchor")
else:
    c = c.replace(old, new, 1)
    print("BUILD COMMAND ADDED")

# 4. Update help
old_help = '''    print("  /tools [on|off]    enable/disable automatic tool use")'''
new_help = '''    print("  /tools [on|off]    enable/disable automatic tool use")
    print("  /build <path> <desc>  generate a full file from description")'''

if old_help in c:
    c = c.replace(old_help, new_help, 1)
    print("HELP UPDATED")

with open(path, "w", encoding="utf-8") as f:
    f.write(c)
print("DONE")
