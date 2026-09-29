#!/usr/bin/env python3
"""MOROAI interactive CLI."""
import os
import sys

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from brain.core import MOROAI, CONTENT_CLASSES
from brain.session import SessionLifecycle
from brain.reflection import Reflector
from tools.reddit import search_reddit


def c(t, code):
    return f"\033[{code}m{t}\033[0m"


DIM, BOLD = "2", "1"
RED, GREEN, YELLOW, CYAN, MAGENTA = "31", "32", "33", "36", "35"


def show_help():
    print()
    print(c("Commands:", BOLD))
    print("  /help              this help")
    print("  /status            brain + providers")
    print("  /content <class>   switch content class")
    print(f"                     classes: {sorted(CONTENT_CLASSES)}")
    print("  /checkpoint [msg]  create checkpoint")
    print("  /checkpoints       list checkpoints")
    print("  /sessions          list workspace sessions")
    print("  /accept <id>       accept session")
    print("  /reject <id>       reject session")
    print("  /memory            memory stats")
    print("  /search <query>    search Reddit via RSS")
    print("  /reflect [N]       extract lessons from last N episodes")
    print("  /lessons [query]   search lessons learned")
    print("  /clear             clear screen")
    print("  /exit              close")
    print()


def show_status(brain, cc):
    print()
    print(c("── BRAIN ──", BOLD))
    print(f"  Owner        : {brain.owner.age_mode if brain.owner else 'NONE'}")
    print(f"  Banned       : {brain.banned}")
    print(f"  Content class: {cc}")
    print()
    print(c("── PROVIDERS ──", BOLD))
    for name, info in brain.available_providers().items():
        ok = c("OK", GREEN) if info["is_available"] else c("NO", RED)
        print(f"  {name:<10} [{ok}]  priority={info['priority']}")
        print(f"             models: {', '.join(info['models'][:2])}")
    print()


def main():
    print()
    print(c("╔════════════════════════════════════╗", CYAN))
    print(c("║        MOROAI  ·  v0.1.0           ║", CYAN))
    print(c("║   Free-First  ·  Arabic-First      ║", CYAN))
    print(c("╚════════════════════════════════════╝", CYAN))

    try:
        brain = MOROAI()
    except KeyboardInterrupt:
        print(c("Aborted.", YELLOW))
        return 1

    if brain.banned:
        days = brain.ban_seconds // 86400
        hours = (brain.ban_seconds % 86400) // 3600
        print(c(f"BANNED {days}d {hours}h", RED))
        return 1

    if brain.owner is None:
        print(c("No valid owner profile.", RED))
        return 1

    print(c(f"Owner mode : {brain.owner.age_mode}", GREEN))
    print(c("Type /help for commands.", DIM))

    reflector = Reflector(brain)
    session = SessionLifecycle()
    try:
        info = session.on_session_start()
        pending = info.get("pending_reviews", [])
        if pending:
            print(c(f"Pending sessions: {len(pending)} (use /sessions)", YELLOW))
    except Exception:
        pass

    cc = "standard"

    while True:
        try:
            raw = input(f"\n{c('MOROAI', MAGENTA)} [{cc}]> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            raw = "/exit"

        if not raw:
            continue

        if raw.startswith("/"):
            cmd, _, args = raw.partition(" ")
            cmd = cmd.lower()
            args = args.strip()

            if cmd in ("/exit", "/quit"):
                try:
                    s = session.on_session_end(note="Closed from CLI")
                    if s.get("checkpoint_hash"):
                        print(c(f"Checkpoint: {s['checkpoint_hash'][:8]}", GREEN))
                    if s.get("session_id"):
                        print(c(f"Session: {s['session_id']}", GREEN))
                except Exception as e:
                    print(c(f"Error: {e}", YELLOW))
                print(c("Goodbye.", CYAN))
                return 0

            elif cmd == "/help":
                show_help()
            elif cmd == "/status":
                show_status(brain, cc)
            elif cmd == "/content":
                if args in CONTENT_CLASSES:
                    cc = args
                    print(c(f"Content: {cc}", GREEN))
                else:
                    print(c(f"Choose: {sorted(CONTENT_CLASSES)}", RED))
            elif cmd == "/checkpoint":
                h = brain.checkpoints.create(args or "Manual")
                print(c(f"OK: {h[:8]}", GREEN) if h else c("Nothing", DIM))
            elif cmd == "/checkpoints":
                for cp in brain.checkpoints.list(10):
                    print(f"  {c(cp['hash'][:8], CYAN)}  {cp['message'][:50]}")
            elif cmd == "/sessions":
                ss = brain.workspace.list_sessions(limit=10)
                if not ss:
                    print(c("None.", DIM))
                for s in ss:
                    print(f"  {c(s['id'], CYAN)}  [{s.get('status','?')}]")
            elif cmd == "/accept":
                print(c("Accepted.", GREEN) if brain.workspace.accept(args) else c("Failed.", RED))
            elif cmd == "/reject":
                print(c("Rejected.", GREEN) if brain.workspace.reject(args) else c("Failed.", RED))
            elif cmd == "/search":
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
            elif cmd == "/memory":
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
                              f"{c(r['category'], MAGENTA)}  {r['rule']}")
            elif cmd == "/clear":
                os.system("clear")
            else:
                print(c(f"Unknown: {cmd}", RED))
            continue

        resp = brain.ask(prompt=raw, content_class=cc)
        if resp.success:
            print()
            print(c(resp.text, CYAN))
            if resp.latency_ms:
                print(c(f"  [{resp.provider} · {resp.model} · {resp.latency_ms:.0f}ms]", DIM))
        else:
            print()
            print(c(f"Error: {resp.error}", RED))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(130)
