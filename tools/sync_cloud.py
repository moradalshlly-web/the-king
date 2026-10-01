"""
tools/sync_cloud.py
===================
Automatic cloud sync for MOROAI.

Behavior:
    - sync_now(path)      : uploads one file to Hugging Face immediately
    - push_github()       : batches text files into one GitHub commit
    - retry_pending()     : flushes the pending queue
    - sync_all()          : scans project and syncs everything
    - status()            : shows sync state

Routing:
    - Text (code, vision, reports)   -> HF + GitHub
    - Large files (images, JS, etc.) -> HF only
    - Private (.env, memory/data/)   -> nowhere

State files:
    - memory/cloud/sync_state.json  : what has been synced
    - memory/cloud/pending.json     : failed uploads (retry queue)
"""

import os
import json
import hashlib
import subprocess
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

try:
    from ..brain.core_paths import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = os.path.expanduser("~/moroai")


# ───────────────────────────────────────────────────────────
# Constants
# ───────────────────────────────────────────────────────────

STATE_FILE   = os.path.join(PROJECT_ROOT, "memory", "cloud", "sync_state.json")
PENDING_FILE = os.path.join(PROJECT_ROOT, "memory", "cloud", "pending.json")
SKILLS_FILE  = os.path.join(PROJECT_ROOT, "memory", "cloud", "skills.json")
ENV_FILE     = os.path.join(PROJECT_ROOT, ".env")
HF_REPO_NAME = "moroai-memory"

GITHUB_MAX_SIZE = 100_000       # 100 KB
TEXT_EXTS = {
    ".py", ".md", ".txt", ".json", ".yaml", ".yml",
    ".html", ".css", ".js", ".ts", ".sh", ".toml", ".ini",
}

PRIVATE_PREFIXES = (
    ".env", ".moroai/", "memory/data/", "node_modules/",
    "__pycache__/", ".git/", "output/", "memory/cloud/pending.json",
    "memory/cloud/sync_state.json",
)


# ───────────────────────────────────────────────────────────
# Helpers — token / paths
# ───────────────────────────────────────────────────────────

def _read_env(key: str) -> Optional[str]:
    if not os.path.exists(ENV_FILE):
        return None
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        return None
    return None


def _relative(path: str) -> str:
    """Convert absolute path to project-relative (POSIX slashes)."""
    if os.path.isabs(path):
        try:
            path = os.path.relpath(path, PROJECT_ROOT)
        except Exception:
            pass
    return path.replace("\\", "/")


def _full(path: str) -> str:
    """Absolute path from project-relative."""
    if os.path.isabs(path):
        return path
    return os.path.join(PROJECT_ROOT, path)


def _is_private(rel_path: str) -> bool:
    for prefix in PRIVATE_PREFIXES:
        if rel_path.startswith(prefix):
            return True
    return False


def _is_text(rel_path: str) -> bool:
    _, ext = os.path.splitext(rel_path)
    return ext.lower() in TEXT_EXTS


# ───────────────────────────────────────────────────────────
# State management
# ───────────────────────────────────────────────────────────

def _load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass


def _load_state() -> Dict[str, Any]:
    return _load_json(STATE_FILE, {"version": 1, "files": {}, "last_sync": None})


def _save_state(state: Dict[str, Any]) -> None:
    state["last_sync"] = datetime.now().isoformat()
    _save_json(STATE_FILE, state)


def _load_pending() -> Dict[str, Any]:
    return _load_json(PENDING_FILE, {"version": 1, "queue": []})


def _save_pending(pending: Dict[str, Any]) -> None:
    _save_json(PENDING_FILE, pending)


# ───────────────────────────────────────────────────────────
# Hashing
# ───────────────────────────────────────────────────────────

def _hash_file(path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _file_info(rel_path: str) -> Optional[Dict[str, Any]]:
    full = _full(rel_path)
    if not os.path.isfile(full):
        return None
    try:
        size = os.path.getsize(full)
        mtime = os.path.getmtime(full)
    except Exception:
        return None
    return {"path": rel_path, "size": size, "mtime": mtime}


# ───────────────────────────────────────────────────────────
# Hugging Face
# ───────────────────────────────────────────────────────────

def _hf_api():
    try:
        from huggingface_hub import HfApi
    except ImportError:
        return None, None
    token = _read_env("HUGGINGFACE_TOKEN")
    if not token:
        return None, None
    try:
        api = HfApi(token=token)
        user = api.whoami()
        return api, f"{user['name']}/{HF_REPO_NAME}"
    except Exception:
        return None, None


def _hf_upload(rel_path: str, remote_path: str) -> bool:
    """Upload one file to HF. Returns True on success."""
    api, repo_id = _hf_api()
    if not api:
        return False
    full = _full(rel_path)
    if not os.path.isfile(full):
        return False
    try:
        api.upload_file(
            path_or_fileobj=full,
            path_in_repo=remote_path,
            repo_id=repo_id,
            repo_type="dataset",
            token=api.token,
        )
        return True
    except Exception:
        return False


# ───────────────────────────────────────────────────────────
# GitHub (batched git operations)
# ───────────────────────────────────────────────────────────

def _gh_run(args: List[str]) -> bool:
    try:
        r = subprocess.run(
            ["git"] + args,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return r.returncode == 0
    except Exception:
        return False


def _gh_has_changes() -> bool:
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return bool(r.stdout.strip())
    except Exception:
        return False


def push_github(message: Optional[str] = None) -> Dict[str, Any]:
    """
    Stage all text files (respecting .gitignore), commit, and push.
    Safe to call anytime. Does nothing if no changes.
    """
    if not _gh_has_changes():
        return {"success": True, "committed": False, "reason": "no changes"}

    if message is None:
        message = f"Auto-sync: {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    if not _gh_run(["add", "-A"]):
        return {"success": False, "error": "git add failed"}

    if not _gh_run(["commit", "-m", message]):
        return {"success": True, "committed": False, "reason": "nothing to commit"}

    if not _gh_run(["push", "origin", "main"]):
        return {"success": False, "error": "git push failed"}

    return {"success": True, "committed": True}


# ───────────────────────────────────────────────────────────
# Pending queue
# ───────────────────────────────────────────────────────────

def _enqueue_pending(rel_path: str, dest: str) -> None:
    p = _load_pending()
    for item in p["queue"]:
        if item["path"] == rel_path and item["dest"] == dest:
            return
    p["queue"].append({
        "path": rel_path,
        "dest": dest,
        "added_at": datetime.now().isoformat(),
    })
    _save_pending(p)


def retry_pending() -> Dict[str, Any]:
    """Try to flush the pending queue. Returns summary."""
    p = _load_pending()
    if not p["queue"]:
        return {"success": True, "retried": 0, "cleared": 0}

    api, repo_id = _hf_api()
    if not api:
        return {"success": False, "error": "HF not configured"}

    still_pending = []
    cleared = 0
    for item in p["queue"]:
        rel = item["path"]
        if not os.path.isfile(_full(rel)):
            cleared += 1
            continue

        remote = "files/" + rel if not rel.startswith("web_new/") \
                 else "web/" + rel.replace("web_new/", "", 1)

        if item["dest"] == "hf" and _hf_upload(rel, remote):
            cleared += 1
        else:
            still_pending.append(item)

    p["queue"] = still_pending
    _save_pending(p)
    return {"success": True, "retried": len(still_pending), "cleared": cleared}


# ───────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────

def _remote_path_for(rel_path: str) -> str:
    """Decide where the file goes inside HF repo."""
    if rel_path.startswith("web_new/"):
        return "web/" + rel_path.replace("web_new/", "", 1)
    if rel_path.startswith("memory/workspace/analyzer/"):
        return "analyzer/" + os.path.basename(rel_path)
    if rel_path.startswith("memory/workspace/isolation/"):
        return "isolation/" + os.path.basename(rel_path)
    if rel_path.startswith("memory/cloud/"):
        return "cloud/" + os.path.basename(rel_path)
    return "files/" + rel_path


def sync_now(path: str) -> Dict[str, Any]:
    """
    Sync a single file to Hugging Face immediately.
    Fast. Best-effort. Adds to pending on failure.

    Call this after any write.
    """
    rel = _relative(path)
    if _is_private(rel):
        return {"success": True, "skipped": "private"}

    info = _file_info(rel)
    if not info:
        return {"success": False, "error": "file not found"}

    # Load state and check if changed
    state = _load_state()
    old = state["files"].get(rel, {})
    if old.get("size") == info["size"] and old.get("mtime") == info["mtime"]:
        return {"success": True, "skipped": "unchanged"}

    # Compute hash
    new_hash = _hash_file(_full(rel))

    # Upload to HF
    remote = _remote_path_for(rel)
    ok_hf = _hf_upload(rel, remote)

    # Update state
    state["files"][rel] = {
        "hash": new_hash,
        "size": info["size"],
        "mtime": info["mtime"],
        "synced_hf": ok_hf,
        "synced_at": datetime.now().isoformat(),
    }
    _save_state(state)

    if not ok_hf:
        _enqueue_pending(rel, "hf")

    return {"success": True, "synced_hf": ok_hf, "remote": remote}


def sync_all(text_only: bool = False) -> Dict[str, Any]:
    """
    Scan the project and sync every changed file.
    Use at end of session, or after big operations.
    """
    dirs = ["brain", "tools", "providers", "memory", "web_new", "config"]
    total = 0
    ok = 0
    failed = 0

    for d in dirs:
        base = os.path.join(PROJECT_ROOT, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [
                x for x in dirnames
                if x not in ("__pycache__", "node_modules", ".git", "output")
            ]
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = _relative(full)
                if _is_private(rel):
                    continue
                if text_only and not _is_text(rel):
                    continue
                total += 1
                r = sync_now(rel)
                if r.get("success"):
                    ok += 1
                else:
                    failed += 1

    return {"success": True, "total": total, "ok": ok, "failed": failed}


def push_all() -> Dict[str, Any]:
    """Full push: HF for everything + one GitHub commit for text."""
    hf = sync_all()
    gh = push_github()
    retry = retry_pending()
    return {
        "success": True,
        "hf": hf,
        "github": gh,
        "pending": retry,
    }


def status() -> Dict[str, Any]:
    """Return sync status summary."""
    state = _load_state()
    pending = _load_pending()
    return {
        "tracked_files": len(state.get("files", {})),
        "last_sync": state.get("last_sync"),
        "pending": len(pending.get("queue", [])),
    }


# ───────────────────────────────────────────────────────────
# Hooks for MOROAI
# ───────────────────────────────────────────────────────────

def notify_skill_learned(skill: Dict[str, Any]) -> Dict[str, Any]:
    """
    Called by MOROAI when it learns a new skill.
    Appends to skills.json and syncs.
    """
    skills = _load_json(SKILLS_FILE, [])
    if not isinstance(skills, list):
        skills = []
    if "learned_at" not in skill:
        skill["learned_at"] = datetime.now().isoformat()
    skills.append(skill)
    _save_json(SKILLS_FILE, skills)
    return sync_now(SKILLS_FILE)


# ───────────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────────

def _print_banner():
    print("=" * 50)
    print("  MOROAI — Sync Cloud")
    print("=" * 50)
    print()


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    _print_banner()

    if cmd == "status":
        s = status()
        print("📊 الحالة:")
        print(f"   ملفات مُتابَعة : {s['tracked_files']}")
        print(f"   آخر مزامنة    : {s['last_sync'] or '(لم تحدث بعد)'}")
        print(f"   في الانتظار   : {s['pending']}")

    elif cmd == "push":
        print("⏳ جاري المزامنة الكاملة...")
        r = push_all()
        print(f"   HF   : {r['hf']['ok']}/{r['hf']['total']} نجح")
        print(f"   GH   : {r['github'].get('committed')}")
        print(f"   معلّق: {r['pending']['retried']}")

    elif cmd == "retry":
        r = retry_pending()
        print(f"✅ أُعيد المحاولة: {r['retried']} — تم رفع: {r['cleared']}")

    elif cmd == "pull":
        print("(pull غير مُنفَّذ بعد — سيُبنى لاحقاً)")

    else:
        print(f"أمر غير معروف: {cmd}")
        print("الأوامر: status | push | retry | pull")
