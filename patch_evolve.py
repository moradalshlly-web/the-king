path = "cli.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

old = '            elif cmd == "/tools":'
new = '''            elif cmd == "/vision":
                print(c("── MOROAI VISION ──", BOLD))
                print(vision_summary())
            elif cmd == "/evolve":
                print(c("Reading vision...", DIM))
                plan = evolve_engine.propose()
                if not plan:
                    print(c("Could not propose a step.", RED))
                else:
                    print()
                    print(c("── PROPOSED STEP ──", BOLD))
                    print(f"  Title      : {c(plan.get('step_title','?'), CYAN)}")
                    print(f"  Target     : {c(plan.get('target_file','?'), CYAN)}")
                    print(f"  Action     : {plan.get('action','?')}")
                    print(f"  Description: {plan.get('description','')}")
                    print()
                    try:
                        ans = input(c("Build this? [y/N]: ", YELLOW)).strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        ans = "n"
                    if ans != "y":
                        print(c("Cancelled.", DIM))
                    else:
                        print(c("Generating...", DIM))
                        content = evolve_engine.generate(plan)
                        if not content:
                            print(c("Generation failed.", RED))
                        else:
                            target = plan["target_file"]
                            print()
                            print(c("── PREVIEW (first 800 chars) ──", BOLD))
                            print(content[:800])
                            if len(content) > 800:
                                print(c(f"... ({len(content) - 800} more chars)", DIM))
                            print(f"Total: {len(content)} chars")
                            print()
                            try:
                                ans2 = input(c("Write this file? [y/N]: ", YELLOW)).strip().lower()
                            except (EOFError, KeyboardInterrupt):
                                ans2 = "n"
                            if ans2 == "y":
                                h = brain.checkpoints.create(f"Before evolve: {target}")
                                if h:
                                    print(c(f"Checkpoint: {h[:8]}", GREEN))
                                r = brain.file_ops.write_file(target, content)
                                if r.get("success"):
                                    print(c(f"Written: {r['path']} ({r['bytes_written']} bytes)", GREEN))
                                else:
                                    print(c(f"Write failed: {r.get('error')}", RED))
                            else:
                                print(c("File not written.", DIM))
            elif cmd == "/tools":'''

if old in c and "/evolve" not in c:
    c = c.replace(old, new, 1)
    c = c.replace(
        '    print("  /build <path> <desc>  generate a full file from description")',
        '    print("  /build <path> <desc>  generate a full file from description")\n    print("  /vision            show vision summary")\n    print("  /evolve            propose & build next evolution step")',
        1,
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("ADDED")
else:
    print("SKIP")
