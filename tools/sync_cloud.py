"""
tools/sync_cloud.py
===================
Fast, automatic cloud sync for MOROAI.

Design:
    - Watcher thread wakes every 30s
    - Batches queued files into single HF upload_folder calls
    - Writes to a local queue (durable across restarts)
    - On reconnect, sends notification and flushes queue
    - On MOROAI shutdown, flushes and stops

Hooks (call these from MOROAI):
    notify_change(path)      -> called after any write
    on_shutdown()            -> called before exit
    start_watcher()          -> start the background thread
"""

import os
import json
import time
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional

try:
    from ..brain.core_paths import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = os.path.expanduser("~/moroai")


# ═══════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════

QUEUE_FILE       = os.path.join(PROJECT_ROOT, "memory", "cloud", "queue.json")
STATE_FILE       = os.path.join(PROJECT_ROOT, "memory", "cloud", "sync_state.json")
NOTIFICATIONS    = os.path.join(PROJECT_ROOT, "memory", "notifications.jsonl")
ENV_FILE         = os.path.join(PROJECT_ROOT, ".env")
HF_REPO_NAME     = "moroai-memory"

WATCH_INTERVAL   = 30         # seconds between flushes
SMALL_FILE_BYTES = 5_000      # upload immediately if smaller
IMMEDIATE_EXTS   = {".json", ".md"}

TEXT_EXTS = {
    ".py", ".md", ".txt", ".json", ".yaml", ".yml",
    ".html", ".css", ".js", ".ts", ".sh", ".toml", ".ini",
}

PRIVATE_PREFIXES = (
    ".env", ".moroai/", "memory/data/", "node_modules/",
    "__pycache__/", ".git/", "output/",
    "memory/cloud/queue.json",
    "memory/cloud/pending.json",
    "memory/cloud/sync_state.json",
    "memory/cloud/test_",
    "memory/vision/_backups/",
)

# Extensions always skipped
SKIP_EXTS = {".lock", ".metadata"}


# ═══════════════════════════════════════════════════════════
# Internal state (in-memory)
# ═══════════════════════════════════════════════════════════

_lock           = threading.Lock()
_queue: Dict[str, float] = {}       # path -> time added
_stop_flag      = False
_watcher        = None
_last_online    = True              # for reconnect notification


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

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
    if os.path.isabs(path):
        try:
            path = os.path.relpath(path, PROJECT_ROOT)
        except Exception:
            pass
    return path.replace("\\", "/")


def _full(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(PROJECT_ROOT, path)


def _is_private(rel: str) -> bool:
    return any(rel.startswith(p) for p in PRIVATE_PREFIXES)


def _load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _notify(message: str, kind: str = "info") -> None:
    try:
        os.makedirs(os.path.dirname(NOTIFICATIONS), exist_ok=True)
        with open(NOTIFICATIONS, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "time": datetime.now().isoformat(),
                "kind": kind,
                "message": message,
                "read": False,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _queue_load() -> None:
    global _queue
    data = _load_json(QUEUE_FILE, {})
    if isinstance(data, dict):
        _queue = data


def _queue_save() -> None:
    with _lock:
        snapshot = dict(_queue)
    _save_json(QUEUE_FILE, snapshot)


# ═══════════════════════════════════════════════════════════
# Hugging Face
# ═══════════════════════════════════════════════════════════

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


def _remote_prefix(rel: str) -> str:
    if rel.startswith("web_new/"):
        return "web"
    if rel.startswith("memory/workspace/analyzer/"):
        return "analyzer"
    if rel.startswith("memory/workspace/isolation/"):
        return "isolation"
    if rel.startswith("memory/cloud/"):
        return "cloud"
    return "files"


# ═══════════════════════════════════════════════════════════
# Batch upload (fast)
# ═══════════════════════════════════════════════════════════

def _upload_batch(paths: List[str]) -> Dict[str, bool]:
    """
    Upload multiple files. Group by remote prefix.
    Uses upload_folder for one HTTP call per group.
    Returns {path: success}.
    """
    api, repo_id = _hf_api()
    if not api:
        return {p: False for p in paths}

    result = {}
    groups: Dict[str, List[str]] = {}

    # Final filter: skip private files even if they slipped through
    def _keep(r: str) -> bool:
        if _is_private(r):
            return False
        _, ext = os.path.splitext(r)
        if ext in SKIP_EXTS:
            return False
        return True

    paths = [p for p in paths if _keep(p)]

    for rel in paths:
        groups.setdefault(_remote_prefix(rel), []).append(rel)

    for prefix, files in groups.items():
        # Build allow_patterns for upload_folder.
        # For "web" prefix, we need to remap web_new/... -> web/...
        try:
            if prefix == "web":
                # web_new/<sub> -> "web/<sub>"
                patterns = [rel.replace("web_new/", "", 1) for rel in files]
                api.upload_folder(
                    folder_path=os.path.join(PROJECT_ROOT, "web_new"),
                    path_in_repo="web",
                    repo_id=repo_id,
                    repo_type="dataset",
                    token=api.token,
                    allow_patterns=patterns,
                )
            elif prefix == "analyzer":
                api.upload_folder(
                    folder_path=os.path.join(PROJECT_ROOT, "memory/workspace/analyzer"),
                    path_in_repo="analyzer",
                    repo_id=repo_id,
                    repo_type="dataset",
                    token=api.token,
                    ignore_patterns=["*.lock", "*.metadata", ".gitignore"],
                )
            elif prefix == "isolation":
                api.upload_folder(
                    folder_path=os.path.join(PROJECT_ROOT, "memory/workspace/isolation"),
                    path_in_repo="isolation",
                    repo_id=repo_id,
                    repo_type="dataset",
                    token=api.token,
                )
            elif prefix == "cloud":
                # Upload only the requested files (safer than full folder)
                for rel in files:
                    full = _full(rel)
                    if os.path.isfile(full):
                        api.upload_file(
                            path_or_fileobj=full,
                            path_in_repo="cloud/" + os.path.basename(rel),
                            repo_id=repo_id,
                            repo_type="dataset",
                            token=api.token,
                        )
            else:
                # misc: upload each individually (rare)
                for rel in files:
                    full = _full(rel)
                    api.upload_file(
                        path_or_fileobj=full,
                        path_in_repo="files/" + rel,
                        repo_id=repo_id,
                        repo_type="dataset",
                        token=api.token,
                    )

            for f in files:
                result[f] = True
        except Exception:
            for f in files:
                result[f] = False

    return result


# ═══════════════════════════════════════════════════════════
# Flush queue (the main worker)
# ═══════════════════════════════════════════════════════════

def _flush() -> Dict[str, Any]:
    """Take everything from queue and try to upload in one batch."""
    global _last_online

    with _lock:
        if not _queue:
            return {"flushed": 0, "failed": 0}
        items = list(_queue.keys())
        _queue.clear()

    # Detect internet via quick check
    api, _ = _hf_api()
    if not api:
        # offline — put back, notify once
        with _lock:
            for it in items:
                _queue[it] = time.time()
        if _last_online:
            _notify("⚠️ لا يوجد اتصال — سيُستأنف الرفع لاحقاً", "sync_offline")
            _last_online = False
        return {"flushed": 0, "failed": len(items), "offline": True}

    # We're back online
    if not _last_online:
        _notify("✅ عاد الاتصال — جاري رفع الملفات المعلّقة", "sync_resumed")
        _last_online = True

    result = _upload_batch(items)
    ok = sum(1 for v in result.values() if v)
    failed = [p for p, v in result.items() if not v]

    if failed:
        # put failures back
        with _lock:
            for it in failed:
                _queue[it] = time.time()

    _queue_save()
    return {"flushed": ok, "failed": len(failed)}


# ═══════════════════════════════════════════════════════════
# Public API — called by MOROAI
# ═══════════════════════════════════════════════════════════

def notify_change(path: str) -> None:
    """
    Called after any file write. Does not block. Never raises.
    Small important files (.json, .md, tiny) are flushed immediately.
    Others are queued for the next batch (30s max).
    """
    try:
        rel = _relative(path)
        if _is_private(rel):
            return
        if not os.path.isfile(_full(rel)):
            return

        size = os.path.getsize(_full(rel))
        _, ext = os.path.splitext(rel)

        # Immediate flush for tiny important files
        if size <= SMALL_FILE_BYTES or ext in IMMEDIATE_EXTS:
            result = _upload_batch([rel])
            if result.get(rel):
                return
            # failed -> queue for retry
            with _lock:
                _queue[rel] = time.time()
            _queue_save()
            return

        # Otherwise queue for batch
        with _lock:
            _queue[rel] = time.time()
        _queue_save()
    except Exception:
        pass


def start_watcher() -> None:
    """Start the background watcher thread. Idempotent."""
    global _watcher, _stop_flag
    if _watcher is not None and _watcher.is_alive():
        return
    _queue_load()
    _stop_flag = False
    _watcher = threading.Thread(target=_watcher_loop, daemon=True, name="moroai-sync")
    _watcher.start()


def on_shutdown() -> Dict[str, Any]:
    """Flush everything and stop the watcher. Call before exit."""
    global _stop_flag
    _stop_flag = True
    result = _flush()
    try:
        if _watcher is not None:
            _watcher.join(timeout=10)
    except Exception:
        pass
    return result


def _watcher_loop() -> None:
    while not _stop_flag:
        try:
            _flush()
        except Exception:
            pass
        # Sleep in small chunks to respond fast to stop_flag
        for _ in range(WATCH_INTERVAL * 2):
            if _stop_flag:
                return
            time.sleep(0.5)


# ═══════════════════════════════════════════════════════════
# Status
# ═══════════════════════════════════════════════════════════

def status() -> Dict[str, Any]:
    with _lock:
        q = len(_queue)
    return {
        "queued": q,
        "watcher_alive": _watcher.is_alive() if _watcher else False,
        "last_online": _last_online,
    }


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    print("=" * 50)
    print("  MOROAI — Sync Cloud")
    print("=" * 50)
    print()

    if cmd == "status":
        s = status()
        print(f"  في الطابور : {s['queued']}")
        print(f"  المراقب    : {'يعمل' if s['watcher_alive'] else 'متوقف'}")
        print(f"  متصل       : {s['last_online']}")
    elif cmd == "flush":
        _queue_load()
        r = _flush()
        print(f"  ✅ تم رفع : {r['flushed']}")
        print(f"  ⚠️ فشل    : {r['failed']}")
    elif cmd == "watch":
        print("⏳ تشغيل المراقب... (Ctrl+C للإيقاف)")
        start_watcher()
        try:
            while True:
                time.sleep(5)
        except KeyboardInterrupt:
            on_shutdown()
            print("\n✅ توقف")
    else:
        print(f"أمر غير معروف: {cmd}")
