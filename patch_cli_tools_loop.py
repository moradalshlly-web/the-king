path = "cli.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# 1. Import run_with_tools
if "from brain.tool_loop import run_with_tools" not in c:
    c = c.replace(
        "from brain.reflection import Reflector",
        "from brain.reflection import Reflector\nfrom brain.tool_loop import run_with_tools",
        1,
    )

# 2. Add tool toggle variable (after cc = "standard")
if 'tools_enabled = True' not in c:
    c = c.replace(
        '    cc = "standard"',
        '    cc = "standard"\n    tools_enabled = True',
        1,
    )

# 3. Add /tools command + modify the ask call
old_ask = '''        resp = brain.ask(prompt=raw, content_class=cc)'''
new_ask = '''        if tools_enabled:
            resp = run_with_tools(brain, raw, content_class=cc)
        else:
            resp = brain.ask(prompt=raw, content_class=cc)'''

if old_ask not in c:
    print("ASK BLOCK NOT FOUND")
else:
    c = c.replace(old_ask, new_ask, 1)
    print("ASK UPDATED")

# 4. Add /tools command
old_memory = '''            elif cmd == "/memory":'''
new_tools = '''            elif cmd == "/tools":
                if args.strip().lower() in ("on", "off"):
                    tools_enabled = (args.strip().lower() == "on")
                    state = "ON" if tools_enabled else "OFF"
                    print(c(f"Tools: {state}", GREEN if tools_enabled else YELLOW))
                else:
                    state = "ON" if tools_enabled else "OFF"
                    print(f"Tools: {c(state, GREEN if tools_enabled else YELLOW)}")
                    print("Usage: /tools on|off")
            elif cmd == "/memory":'''

if old_memory not in c:
    print("MEMORY BLOCK NOT FOUND")
else:
    c = c.replace(old_memory, new_tools, 1)
    print("TOOLS COMMAND ADDED")

# 5. Update /help
old_help = '''    print("  /search <query>    search Reddit via RSS")'''
new_help = '''    print("  /search <query>    search Reddit via RSS")
    print("  /tools [on|off]    enable/disable automatic tool use")'''

if old_help in c:
    c = c.replace(old_help, new_help, 1)
    print("HELP UPDATED")

# 6. Show tools state in banner area
old_banner = '''    print(c("Type /help for commands.", DIM))'''
new_banner = '''    print(c("Type /help for commands.", DIM))
    print(c(f"Tools: ON (MOROAI can read files, run safe commands, search Reddit)", DIM))'''

if old_banner in c:
    c = c.replace(old_banner, new_banner, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("DONE")
