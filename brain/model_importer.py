"""
brain/model_importer.py
=======================
Model importer for MOROAI — from Hugging Face Hub.

Capabilities:
    - search(query)         : search HF for models
    - info(model_id)        : size, license, downloads, tags
    - import_model(id)      : download to local storage (if <= size cap)
    - list_imported()       : list already imported models
    - remove(model_id)      : delete an imported model
    - status()              : total disk usage

Storage layout:
    models/
      <owner>/<name>/       : downloaded model files
      registry.json         : index of imported models

Size cap: 50 MB by default (configurable per call).
"""

import os
import json
import shutil
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


try:
    from brain.core_paths import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = os.path.expanduser("~/moroai")


MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
REGISTRY   = os.path.join(MODELS_DIR, "registry.json")

DEFAULT_SIZE_CAP_MB = 50
DEFAULT_SIZE_CAP_BYTES = DEFAULT_SIZE_CAP_MB * 1024 * 1024


# ───────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_token() -> Optional[str]:
    env = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(env):
        return None
    try:
        with open(env, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("HUGGINGFACE_TOKEN="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        return None
    return None


def _api():
    try:
        from huggingface_hub import HfApi
    except ImportError:
        return None
    token = _read_token()
    if not token:
        return None
    try:
        return HfApi(token=token)
    except Exception:
        return None


def _load_registry() -> Dict[str, Any]:
    if not os.path.exists(REGISTRY):
        return {"version": 1, "models": {}}
    try:
        with open(REGISTRY, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": 1, "models": {}}


def _save_registry(data: Dict[str, Any]) -> None:
    os.makedirs(MODELS_DIR, exist_ok=True)
    with open(REGISTRY, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _human_size(n_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} TB"


def _local_path(model_id: str) -> str:
    safe = model_id.replace("/", "_")
    return os.path.join(MODELS_DIR, safe)


# ───────────────────────────────────────────────
# Public API: search / info
# ───────────────────────────────────────────────

def search(query: str, limit: int = 15,
           max_size_mb: Optional[float] = None) -> List[Dict[str, Any]]:
    """
    Search HF for models matching `query`.
    If max_size_mb given, filters out models larger than that.
    """
    api = _api()
    if not api:
        return [{"error": "no HF token or huggingface_hub missing"}]

    try:
        results = list(api.list_models(
            search=query, limit=limit, sort="downloads", direction=-1,
        ))
    except Exception as e:
        return [{"error": str(e)}]

    out: List[Dict[str, Any]] = []
    for m in results:
        # Estimate size from siblings
        size_bytes = 0
        try:
            if m.siblings:
                size_bytes = sum((s.size or 0) for s in m.siblings)
        except Exception:
            pass

        size_mb = size_bytes / 1024 / 1024 if size_bytes else 0
        license_ = "?"
        try:
            if m.cardData:
                license_ = m.cardData.get("license", "?") or "?"
        except Exception:
            pass

        entry = {
            "id": m.id,
            "downloads": m.downloads or 0,
            "likes": m.likes or 0,
            "tags": (m.tags or [])[:6],
            "license": license_,
            "size_mb": round(size_mb, 2) if size_mb else None,
            "pipeline": m.pipeline_tag or "?",
        }
        if max_size_mb is None or (size_mb and size_mb <= max_size_mb):
            out.append(entry)

    return out


def info(model_id: str) -> Dict[str, Any]:
    """Get detailed info about a model."""
    api = _api()
    if not api:
        return {"error": "no HF token"}

    try:
        m = api.model_info(model_id, files_metadata=True)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    size_bytes = 0
    file_list = []
    try:
        if m.siblings:
            for s in m.siblings:
                sz = s.size or 0
                size_bytes += sz
                file_list.append({
                    "name": s.rfilename,
                    "size": sz,
                })
    except Exception:
        pass

    license_ = "?"
    try:
        if m.cardData:
            license_ = m.cardData.get("license", "?") or "?"
    except Exception:
        pass

    return {
        "id": m.id,
        "downloads": m.downloads or 0,
        "likes": m.likes or 0,
        "tags": (m.tags or [])[:8],
        "pipeline": m.pipeline_tag or "?",
        "license": license_,
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / 1024 / 1024, 2) if size_bytes else 0,
        "size_human": _human_size(size_bytes),
        "files": file_list[:20],
    }


# ───────────────────────────────────────────────
# Public API: import / remove
# ───────────────────────────────────────────────

def import_model(model_id: str,
                 size_cap_mb: float = DEFAULT_SIZE_CAP_MB,
                 allow_patterns: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Download a model to local storage (models/<safe_id>/).

    - Refuses if total size > size_cap_mb.
    - Records in registry.json.
    """
    api = _api()
    if not api:
        return {"success": False, "error": "no HF token"}

    # 1) Check size first
    inf = info(model_id)
    if "error" in inf:
        return {"success": False, "error": inf["error"]}

    size_mb = inf.get("size_mb", 0)
    cap_bytes = size_cap_mb * 1024 * 1024

    if inf.get("size_bytes", 0) > cap_bytes:
        return {
            "success": False,
            "error": f"النموذج أكبر من الحد ({size_mb} MB > {size_cap_mb} MB)",
            "size_mb": size_mb,
            "cap_mb": size_cap_mb,
        }

    # 2) Download
    local = _local_path(model_id)
    os.makedirs(local, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download
        path = snapshot_download(
            repo_id=model_id,
            local_dir=local,
            local_dir_use_symlinks=False,
            token=_read_token(),
            allow_patterns=allow_patterns,
            ignore_patterns=["*.md", "*.txt", "*.gitattributes"],
        )
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    # 3) Actual size on disk
    actual_bytes = 0
    for root, _, files in os.walk(local):
        for f in files:
            actual_bytes += os.path.getsize(os.path.join(root, f))

    # 4) Record
    reg = _load_registry()
    reg["models"][model_id] = {
        "id": model_id,
        "path": local,
        "size_bytes": actual_bytes,
        "size_human": _human_size(actual_bytes),
        "license": inf.get("license", "?"),
        "pipeline": inf.get("pipeline", "?"),
        "imported_at": _now(),
    }
    _save_registry(reg)

    return {
        "success": True,
        "id": model_id,
        "path": local,
        "size_bytes": actual_bytes,
        "size_human": _human_size(actual_bytes),
    }


def list_imported() -> List[Dict[str, Any]]:
    reg = _load_registry()
    return list(reg.get("models", {}).values())


def remove(model_id: str) -> Dict[str, Any]:
    reg = _load_registry()
    if model_id not in reg.get("models", {}):
        return {"success": False, "error": "not imported"}

    path = reg["models"][model_id].get("path") or _local_path(model_id)
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
    except Exception as e:
        return {"success": False, "error": str(e)}

    del reg["models"][model_id]
    _save_registry(reg)
    return {"success": True, "removed": model_id}


def status() -> Dict[str, Any]:
    reg = _load_registry()
    models = reg.get("models", {})
    total = sum(m.get("size_bytes", 0) for m in models.values())
    return {
        "count": len(models),
        "total_bytes": total,
        "total_human": _human_size(total),
        "models": [
            {
                "id": m["id"],
                "size_human": m.get("size_human", "?"),
                "pipeline": m.get("pipeline", "?"),
            }
            for m in models.values()
        ],
    }


# ───────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("Model Importer — MOROAI")
    print("=" * 55)

    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        s = status()
        print(f"Imported: {s['count']} models")
        print(f"Total:    {s['total_human']}")
        print()
        for m in s["models"]:
            print(f"  • {m['id']}")
            print(f"      {m['size_human']} ({m['pipeline']})")

    elif cmd == "search":
        q = " ".join(sys.argv[2:]) or "arabic nlp"
        print(f"Searching HF: '{q}' (max 50 MB)")
        print()
        res = search(q, limit=15, max_size_mb=50)
        if not res:
            print("  (لا نتائج)")
        for m in res:
            if "error" in m:
                print(f"  ❌ {m['error']}")
                continue
            print(f"  • {m['id']}")
            print(f"     size={m.get('size_mb','?')} MB | "
                  f"downloads={m['downloads']} | license={m['license']}")

    elif cmd == "info":
        if len(sys.argv) < 3:
            print("Usage: python -m brain.model_importer info <model_id>")
        else:
            r = info(sys.argv[2])
            for k, v in r.items():
                if k == "files":
                    print(f"  files: {len(v)}")
                    for f in v[:5]:
                        print(f"     - {f['name']} ({f['size']} B)")
                else:
                    print(f"  {k}: {v}")

    elif cmd == "import":
        if len(sys.argv) < 3:
            print("Usage: python -m brain.model_importer import <model_id>")
        else:
            r = import_model(sys.argv[2])
            for k, v in r.items():
                print(f"  {k}: {v}")

    elif cmd == "remove":
        if len(sys.argv) < 3:
            print("Usage: python -m brain.model_importer remove <model_id>")
        else:
            print(remove(sys.argv[2]))

    else:
        print(f"Unknown: {cmd}")
        print("Commands: status | search <query> | info <id> | import <id> | remove <id>")
