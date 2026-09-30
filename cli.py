#!/usr/bin/env python3
"""
MOROAI CLI v0.5
================

Features:
    - Status banner on startup
    - Session save/restore
    - Commands: /help, /status, /clear, /export, /history, /provider, /model, /time
    - All existing commands preserved
    - Tool calling automatic
"""

import os
import sys
import json
from datetime import datetime

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
from brain.tool_loop import run_with_tools
from brain.builder import Builder
from brain.evolve import EvolveEngine
from brain.vision import vision_summary
from brain import search_history
from brain import history_updater
from tools.reddit import search_reddit
from tools.web_search import search_web
from tools.youtube import search_youtube


# ============================================================
# ANSI Colors
# ============================================================

def c(text, code):
    return f"\033[{code}m{text}\033[0m"

DIM, BOLD = "2", "1"
RED, GREEN, YELLOW, CYAN, MAGENTA = "31", "32", "33", "36", "35"
BLUE, PURPLE = "34", "35"


# ============================================================
# Session State
# ============================================================

SESSION_DIR = os.path.expanduser("~/moroai/.moroai/sessions")


def save_session(messages, meta):
    """Save current session to JSON."""
    os.makedirs(SESSION_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(SESSION_DIR, f"{ts}.json")
    data = {
        "created": datetime.now().isoformat(),
        "meta": meta,
        "messages": messages,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def list_sessions():
    """List recent sessions."""
    if not os.path.exists(SESSION_DIR):
        return []
    files = sorted(
        [f for f in os.listdir(SESSION_DIR) if f.endswith(".json")],
        reverse=True
    )
    return files[:10]


def load_session(path):
    """Load a session file."""
    if not os.path.isabs(path):
        path = os.path.join(SESSION_DIR, path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ============================================================
# Banner & Info Panels
# ============================================================

def show_banner(brain, content_class, tools_on):
    """Show startup banner with system status."""
    print()
    print(c("╔══════════════════════════════════════════════════╗", PURPLE))
    print(c("║         MOROAI  ·  v0.5  ·  Command Center       ║", PURPLE))
    print(c("╚══════════════════════════════════════════════════╝", PURPLE))

    # Owner + content
    owner = brain.owner.age_mode if brain.owner else "NONE"
    tools_str = c("ON", GREEN) if tools_on else c("OFF", RED)
    print(f"  👤 Owner: {c(owner, CYAN)}   🎯 Class: {c(content_class, CYAN)}   🛠 Tools: {tools_str}")

    # Providers
    provs = brain.available_providers()
    prov_line = "  🔌 "
    for name, info in provs.items():
        if info["is_available"]:
            prov_line += c(f"{name} ", GREEN)
        else:
            prov_line += c(f"{name} ", DIM)
    print(prov_line)

    # Memory
    try:
        stats = brain.learning.count()
        eps = stats.get("episodes", 0)
        lessons = stats.get("lessons", 0)
        print(f"  💾 Memory: {c(str(eps), CYAN)} episodes · {c(str(lessons), CYAN)} lessons")
    except Exception:
        pass

    print(c("  Type /help for commands · /exit to quit", DIM))
    print()


def show_help():
    print()
    print(c("─── CHAT ───", BOLD))
    print("  (اكتب بالعربية مباشرة للدردشة)")

    print()
    print(c("─── COMMANDS ───", BOLD))
    print("  /help              هذا الدليل")
    print("  /status            حالة النظام + المزودين")
    print("  /clear             مسح الشاشة")
    print("  /history           آخر 20 رسالة")
    print("  /export            حفظ المحادثة في ملف")
    print("  /time              وقت الجلسة")
    print("  /provider [name]   عرض/إجبار مزود")
    print("  /model [name]      عرض/إجبار نموذج")
    print("  /content [class]   تغيير فئة المحتوى")

    print()
    print(c("─── TOOLS ───", BOLD))
    print("  /tools [on|off]    تفعيل/إيقاف الأدوات التلقائية")
    print("  /search <query>    بحث في الويب + يوتيوب + Reddit")
    print("  /ls [path]         عرض ملفات")
    print("  /cat <file>        قراءة ملف")
    print("  /run <cmd>         تنفيذ أمر shell آمن")

    print()
    print(c("─── BUILD & EVOLVE ───", BOLD))
    print("  /build <path> <desc>   توليد ملف كامل")
    print("  /vision                ملخص الرؤية")
    print("  /evolve                اقتراح خطوة تطور")

    print()
    print(c("─── SESSION ───", BOLD))
    print("  /sessions          عرض الجلسات المحفوظة")
    print("  /resume <file>     استئناف جلسة سابقة")
    print("  /checkpoint [msg]  إنشاء checkpoint")
    print("  /checkpoints       عرض Checkpoints")
    print("  /accept <id>       قبول Workspace session")
    print("  /reject <id>       رفض Workspace session")
    print("  /memory            إحصاءات الذاكرة")
    print("  /reflect [N]       استخلاص دروس من آخر N")
    print("  /lessons [query]   البحث في الدروس")
    print("  /exit              خروج + حفظ الجلسة")
    print()


def show_status(brain, content_class, tools_on):
    print()
    print(c("─── BRAIN ───", BOLD))
    print(f"  Owner        : {brain.owner.age_mode if brain.owner else 'NONE'}")
    print(f"  Banned       : {brain.banned}")
    print(f"  Content      : {content_class}")
    print(f"  Tools        : {'ON' if tools_on else 'OFF'}")

    print()
    print(c("─── PROVIDERS ───", BOLD))
    for name, info in brain.available_providers().items():
        ok = c("OK", GREEN) if info["is_available"] else c("NO", RED)
        cd = c(" (cooldown)", YELLOW) if info["in_cooldown"] else ""
        print(f"  {name:<12} [{ok}]{cd}  priority={info['priority']}")
        print(f"    models: {', '.join(info['models'][:2])}")

    print()
    print(c("─── MEMORY ───", BOLD))
    try:
        stats = brain.learning.count()
        print(f"  Episodes : {stats.get('episodes', 0)}")
        print(f"  Lessons  : {stats.get('lessons', 0)}")
        print(f"  History  : {brain.memory.count()}")
    except Exception:
        pass
    print()


# ============================================================
# Main Loop
# ============================================================

def main():
    # Boot brain
    try:
        brain = MOROAI()
    except KeyboardInterrupt:
        print(c("\nAborted.", YELLOW))
        return 1

    if brain.banned:
        days = brain.ban_seconds // 86400
        hours = (brain.ban_seconds % 86400) // 3600
        print(c(f"⛔ BANNED for {days}d {hours}h.", RED))
        return 1

    if brain.owner is None:
        print(c("⛔ No owner profile.", RED))
        return 1

    # Initialize subsystems
    reflector = Reflector(brain)
    builder = Builder(brain)
    evolve_engine = EvolveEngine(brain)
    session_lifecycle = SessionLifecycle()

    # State
    content_class = "standard"
    tools_enabled = True
    forced_provider = None
    forced_model = None
    messages_log = []
    started_at = datetime.now()

    # Session start check
    try:
        info = session_lifecycle.on_session_start()
        pending = info.get("pending_reviews", [])
    except Exception:
        pending = []

    # Show banner
    show_banner(brain, content_class, tools_enabled)

    # Notify about stale searches (do NOT refresh automatically)
    try:
        st = history_updater.status()
        if st.get("stale", 0) > 0:
            n = st['stale']
            print(c(f"🔄 {n} search(es) need refresh (older than 12h)", YELLOW))
            print(c(f"   Run /history refresh-all to update them", DIM))
            print()
    except Exception:
        pass
    if pending:
        print(c(f"📦 You have {len(pending)} pending session(s). Use /sessions.", YELLOW))
        print()

    while True:
        try:
            prompt_str = f"\n{c('MOROAI', MAGENTA)} [{content_class}]> "
            raw = input(prompt_str).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            raw = "/exit"

        if not raw:
            continue

        # Add to log
        messages_log.append({"role": "user", "text": raw, "time": datetime.now().isoformat()})

        # ------- COMMANDS -------
        if raw.startswith("/"):
            cmd, _, args = raw.partition(" ")
            cmd = cmd.lower()
            args = args.strip()

            # Exit
            if cmd in ("/exit", "/quit"):
                try:
                    path = save_session(messages_log, {
                        "content_class": content_class,
                        "tools": tools_enabled,
                        "providers": list(brain.available_providers().keys()),
                    })
                    print(c(f"💾 Session saved: {os.path.basename(path)}", GREEN))
                except Exception as e:
                    print(c(f"⚠️ Could not save session: {e}", YELLOW))
                try:
                    s = session_lifecycle.on_session_end(note="Closed from CLI")
                    if s.get("checkpoint_hash"):
                        print(c(f"✅ Checkpoint: {s['checkpoint_hash'][:8]}", GREEN))
                except Exception:
                    pass
                elapsed = datetime.now() - started_at
                mins = int(elapsed.total_seconds() // 60)
                print(c(f"⏱️ Session duration: {mins} min", DIM))
                print(c("Goodbye. 👋", CYAN))
                return 0

            # Help
            elif cmd == "/help":
                show_help()

            # Status
            elif cmd == "/status":
                show_status(brain, content_class, tools_enabled)

            # Clear
            elif cmd == "/clear":
                os.system("clear")
                show_banner(brain, content_class, tools_enabled)

            # History (search history, with subcommands)
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

                elif sub == "refresh-all":
                    st = history_updater.status()
                    if st["stale"] == 0:
                        print(c("Nothing to refresh. All searches are fresh.", GREEN))
                    else:
                        print()
                        print(c(f"REFRESHING {min(st['stale'], 3)} STALE SEARCH(ES)", BOLD))
                        print(c(f"Total stale: {st['stale']} (max 3 per run)", DIM))
                        print()
                        result = history_updater.refresh_stale(verbose=True)
                        print()
                        print(c(f"Refreshed: {result['refreshed']}", GREEN))
                        if result["failed"]:
                            print(c(f"Failed: {result['failed']}", RED))

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
                    print()

            # Export
            elif cmd == "/export":
                try:
                    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    path = os.path.expanduser(f"~/moroai/output/chat_{ts}.md")
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(f"# MOROAI Chat Session\n")
                        f.write(f"**Date:** {started_at.isoformat()}\n\n---\n\n")
                        for m in messages_log:
                            role = "👤 You" if m["role"] == "user" else "🤖 MOROAI"
                            f.write(f"### {role}\n\n{m['text']}\n\n")
                    print(c(f"✅ Exported: {path}", GREEN))
                except Exception as e:
                    print(c(f"❌ Export failed: {e}", RED))

            # Time
            elif cmd == "/time":
                elapsed = datetime.now() - started_at
                mins = int(elapsed.total_seconds() // 60)
                secs = int(elapsed.total_seconds() % 60)
                print(f"⏱️ Session: {mins}m {secs}s")

            # Provider
            elif cmd == "/provider":
                if not args:
                    cur = forced_provider or "auto"
                    print(f"Current provider: {c(cur, CYAN)}")
                    print(f"Available: {', '.join(brain.available_providers().keys())}")
                else:
                    if args.lower() == "auto":
                        forced_provider = None
                        print(c("Provider: auto", GREEN))
                    elif args.lower() in brain.available_providers():
                        forced_provider = args.lower()
                        print(c(f"Provider forced: {args}", GREEN))
                    else:
                        print(c(f"Unknown: {args}", RED))

            # Model
            elif cmd == "/model":
                if not args:
                    print(f"Current model: {c(forced_model or 'auto', CYAN)}")
                else:
                    if args.lower() == "auto":
                        forced_model = None
                        print(c("Model: auto", GREEN))
                    else:
                        forced_model = args
                        print(c(f"Model forced: {args}", GREEN))

            # Content class
            elif cmd == "/content":
                if args in CONTENT_CLASSES:
                    content_class = args
                    print(c(f"Content class: {content_class}", GREEN))
                else:
                    print(c(f"Choose: {sorted(CONTENT_CLASSES)}", RED))

            # Tools on/off
            elif cmd == "/tools":
                if args.strip().lower() in ("on", "off"):
                    tools_enabled = (args.strip().lower() == "on")
                    state = "ON" if tools_enabled else "OFF"
                    col = GREEN if tools_enabled else YELLOW
                    print(c(f"Tools: {state}", col))
                else:
                    state = "ON" if tools_enabled else "OFF"
                    print(f"Tools: {c(state, GREEN if tools_enabled else YELLOW)}")
                    print("Usage: /tools on|off")

            # Search (3 sources)
            elif cmd == "/search":
                if not args:
                    print(c("Usage: /search <query>", YELLOW))
                else:
                    print(c(f"Searching: {args}", YELLOW))
                    # Web
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
                    # YouTube
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
                    # Reddit
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
                        print(c(f"  (error: {e})", DIM))

            # List files
            elif cmd == "/ls":
                r = brain.file_ops.list_dir(args or ".", recursive=False) if hasattr(brain, "file_ops") else {"success": False, "error": "no file_ops"}
                from tools.file_ops import FileOps
                fops = FileOps()
                r = fops.list_dir(args or ".", recursive=False)
                if not r["success"]:
                    print(c(f"Error: {r['error']}", RED))
                else:
                    for item in r["items"]:
                        print(f"  {item}")

            # Read file
            elif cmd == "/cat":
                from tools.file_ops import FileOps
                fops = FileOps()
                if not args:
                    print(c("Usage: /cat <file>", YELLOW))
                else:
                    r = fops.read_file(args)
                    if r["success"]:
                        print(r["content"])
                    else:
                        print(c(f"Error: {r['error']}", RED))

            # Run shell
            elif cmd == "/run":
                from tools.shell import ShellOps
                sops = ShellOps()
                if not args:
                    print(c("Usage: /run <command>", YELLOW))
                else:
                    print(c(f"$ {args}", DIM))
                    r = sops.run(args)
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

            # Build
            elif cmd == "/build":
                parts = args.split(maxsplit=2)
                auto_yes = False
                if parts and parts[0] == "--yes":
                    auto_yes = True
                    parts = parts[1:]
                if len(parts) < 2:
                    print(c("Usage: /build [--yes] <path> <description>", YELLOW))
                else:
                    target = parts[0]
                    desc = parts[1] + ((" " + parts[2]) if len(parts) > 2 else "")
                    print(c(f"Building: {target}", YELLOW))
                    print(c("Generating (this may take 5-20s)...", DIM))
                    res = builder.generate(target, desc)
                    if not res["success"]:
                        print(c(f"❌ Failed: {res['error']}", RED))
                    else:
                        content = res["content"]
                        print()
                        print(c("── PREVIEW (first 800 chars) ──", BOLD))
                        print(content[:800])
                        print(f"Total: {len(content)} chars")
                        print()
                        confirm = "y" if auto_yes else input(c("Write this file? [y/N]: ", YELLOW)).strip().lower()
                        if confirm == "y":
                            h = brain.checkpoints.create(f"Before building {target}")
                            if h:
                                print(c(f"Checkpoint: {h[:8]}", GREEN))
                            r = builder.write(target, content)
                            if r["success"]:
                                print(c(f"✅ Written: {r['path']} ({r['bytes_written']} bytes)", GREEN))
                            else:
                                print(c(f"❌ Write failed: {r['error']}", RED))

            # Vision
            elif cmd == "/vision":
                print(c("── MOROAI VISION ──", BOLD))
                print(vision_summary())

            # Evolve
            elif cmd == "/evolve":
                print(c("Reading vision...", DIM))
                plan = evolve_engine.propose()
                if not plan:
                    print(c("❌ Could not propose a step.", RED))
                else:
                    print()
                    print(c("── PROPOSED STEP ──", BOLD))
                    print(f"  Title      : {c(plan.get('step_title','?'), CYAN)}")
                    print(f"  Target     : {c(plan.get('target_file','?'), CYAN)}")
                    print(f"  Action     : {plan.get('action','?')}")
                    print(f"  Description: {plan.get('description','')}")
                    print()
                    ans = input(c("Build this? [y/N]: ", YELLOW)).strip().lower()
                    if ans == "y":
                        content = evolve_engine.generate(plan)
                        if not content:
                            print(c("❌ Generation failed.", RED))
                        else:
                            print(c("── PREVIEW ──", BOLD))
                            print(content[:600])
                            print()
                            ans2 = input(c("Write this file? [y/N]: ", YELLOW)).strip().lower()
                            if ans2 == "y":
                                h = brain.checkpoints.create(f"Before evolve: {plan['target_file']}")
                                r = evolve_engine.file_ops.write_file(plan["target_file"], content)
                                if r.get("success"):
                                    print(c(f"✅ Written: {r['path']}", GREEN))
                                else:
                                    print(c(f"❌ {r.get('error')}", RED))

            # Sessions
            elif cmd == "/sessions":
                files = list_sessions()
                if not files:
                    print(c("No saved sessions.", DIM))
                else:
                    for f in files:
                        print(f"  {f}")

            # Resume
            elif cmd == "/resume":
                if not args:
                    print(c("Usage: /resume <file>", YELLOW))
                else:
                    data = load_session(args)
                    if not data:
                        print(c(f"❌ Not found: {args}", RED))
                    else:
                        msgs = data.get("messages", [])
                        messages_log = msgs
                        print(c(f"✅ Loaded {len(msgs)} messages", GREEN))

            # Checkpoints
            elif cmd == "/checkpoint":
                h = brain.checkpoints.create(args or "Manual")
                print(c(f"OK: {h[:8]}", GREEN) if h else c("Nothing to checkpoint.", DIM))
            elif cmd == "/checkpoints":
                for cp in brain.checkpoints.list(10):
                    print(f"  {c(cp['hash'][:8], CYAN)}  {cp['message'][:60]}")

            # Accept/Reject sessions
            elif cmd == "/accept":
                print(c("Accepted.", GREEN) if brain.workspace.accept(args) else c("Failed.", RED))
            elif cmd == "/reject":
                print(c("Rejected.", GREEN) if brain.workspace.reject(args) else c("Failed.", RED))

            # Memory
            elif cmd == "/memory":
                print(f"Interactions: {c(str(brain.memory.count()), CYAN)}")
                stats = brain.learning.count()
                print(f"Episodes    : {c(str(stats['episodes']), CYAN)}")
                print(f"Lessons     : {c(str(stats['lessons']), CYAN)}")

            # Reflect
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

            # Lessons
            elif cmd == "/lessons":
                rows = brain.learning.search_lessons(args or "the", limit=10)
                if not rows:
                    print(c("No lessons yet. Use /reflect.", DIM))
                else:
                    for r in rows:
                        print(f"  {c('['+str(r['id'])+']', CYAN)} {c(r['category'], MAGENTA)}  {r['rule']}")

            else:
                print(c(f"Unknown command: {cmd}", RED))
            continue

        # ------- ASK MOROAI -------
        # Apply forced provider/model
        kwargs = {"content_class": content_class}
        if forced_model:
            kwargs["model"] = forced_model

        if tools_enabled:
            resp = run_with_tools(brain, raw, content_class=content_class)
        else:
            resp = brain.ask(prompt=raw, **kwargs)

        if resp.success:
            print()
            print(c(resp.text, CYAN))
            meta = f"  [{resp.provider} · {resp.model} · {resp.latency_ms:.0f}ms]"
            print(c(meta, DIM))
            messages_log.append({
                "role": "ai",
                "text": resp.text,
                "provider": resp.provider,
                "model": resp.model,
                "time": datetime.now().isoformat(),
            })
        else:
            print()
            print(c(f"❌ {resp.error}", RED))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(130)
