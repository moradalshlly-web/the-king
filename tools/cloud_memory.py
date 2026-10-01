"""
tools/cloud_memory.py
=====================
Cloud memory for MOROAI using Hugging Face Hub.

What it does:
    1. Upload analysis reports
    2. Read / list reports
    3. Download reports back
    4. Save / read skills (learned patterns)
    5. Save workspace snapshots
    6. Show status

Uses .env file: HUGGINGFACE_TOKEN=hf_...
Repository: <username>/moroai-memory (private, dataset type)
"""

import os
import json
import glob
from datetime import datetime
from typing import Dict, Any, List, Optional

try:
    from ..brain.core_paths import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = os.path.expanduser("~/moroai")

try:
    from huggingface_hub import HfApi, create_repo, hf_hub_download
except ImportError:
    HfApi = None
    create_repo = None
    hf_hub_download = None


ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
REPO_NAME = "moroai-memory"
REPO_TYPE = "dataset"


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

def _read_token() -> Optional[str]:
    """Read HUGGINGFACE_TOKEN from .env."""
    if not os.path.exists(ENV_FILE):
        return None
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("HUGGINGFACE_TOKEN="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        return None
    return None


def _get_api():
    """Return (api, repo_id) or (None, None) if not ready."""
    if HfApi is None:
        return None, None
    token = _read_token()
    if not token:
        return None, None
    try:
        api = HfApi(token=token)
        user = api.whoami()
        username = user.get("name")
        if not username:
            return None, None
        return api, f"{username}/{REPO_NAME}"
    except Exception:
        return None, None


def _ensure_repo(api, repo_id: str) -> bool:
    """Create repo if it doesn't exist. Returns True on success."""
    try:
        create_repo(
            repo_id=repo_id,
            repo_type=REPO_TYPE,
            private=True,
            token=api.token,
            exist_ok=True,
        )
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════
# 1. Upload a report
# ═══════════════════════════════════════════════════════════

def upload_report(local_path: str) -> Dict[str, Any]:
    """
    Upload a single report file to cloud.
    Saves under: analyzer/<filename>
    """
    api, repo_id = _get_api()
    if not api:
        return {"success": False, "error": "Cloud not configured (check .env)"}

    if not os.path.isfile(local_path):
        return {"success": False, "error": f"File not found: {local_path}"}

    if not _ensure_repo(api, repo_id):
        return {"success": False, "error": "Could not create/open repo"}

    remote_name = os.path.basename(local_path)
    remote_path = f"analyzer/{remote_name}"

    try:
        api.upload_file(
            path_or_fileobj=local_path,
            path_in_repo=remote_path,
            repo_id=repo_id,
            repo_type=REPO_TYPE,
            token=api.token,
        )
        return {
            "success": True,
            "remote_path": remote_path,
            "repo_id": repo_id,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def upload_all_reports() -> Dict[str, Any]:
    """Upload all local reports at once."""
    pattern = os.path.join(PROJECT_ROOT, "memory", "workspace", "analyzer", "*.md")
    files = sorted(glob.glob(pattern))
    if not files:
        return {"success": False, "error": "No local reports found"}

    results = []
    for f in files:
        results.append(upload_report(f))

    ok = sum(1 for r in results if r.get("success"))
    return {
        "success": True,
        "uploaded": ok,
        "total": len(files),
        "details": results,
    }


# ═══════════════════════════════════════════════════════════
# 2. List reports
# ═══════════════════════════════════════════════════════════

def list_reports() -> Dict[str, Any]:
    """List all reports stored in cloud."""
    api, repo_id = _get_api()
    if not api:
        return {"success": False, "error": "Cloud not configured"}

    try:
        files = list(api.list_repo_files(
            repo_id=repo_id, repo_type=REPO_TYPE, token=api.token
        ))
        reports = [f for f in files if f.startswith("analyzer/") and f.endswith(".md")]
        return {"success": True, "count": len(reports), "files": reports}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
# 3. Download a report
# ═══════════════════════════════════════════════════════════

def download_report(remote_path: str, local_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Download one report from cloud.
    remote_path example: 'analyzer/report-xxx.md'
    """
    if HfApi is None or hf_hub_download is None:
        return {"success": False, "error": "huggingface_hub not installed"}

    api, repo_id = _get_api()
    if not api:
        return {"success": False, "error": "Cloud not configured"}

    target_dir = local_dir or os.path.join(PROJECT_ROOT, "memory", "workspace", "analyzer")
    os.makedirs(target_dir, exist_ok=True)

    try:
        path = hf_hub_download(
            repo_id=repo_id,
            filename=remote_path,
            repo_type=REPO_TYPE,
            token=api.token,
            local_dir=target_dir,
        )

        # hf_hub_download preserves the remote path structure
        # e.g., analyzer/report-xxx.md -> target_dir/analyzer/report-xxx.md
        # We flatten it: move to target_dir/report-xxx.md
        import shutil
        filename = os.path.basename(remote_path)
        final_path = os.path.join(target_dir, filename)

        if os.path.abspath(path) != os.path.abspath(final_path):
            shutil.move(path, final_path)

            # cleanup: remove the now-empty nested folder if any
            nested_dir = os.path.dirname(path)
            try:
                if os.path.isdir(nested_dir) and not os.listdir(nested_dir):
                    os.rmdir(nested_dir)
            except Exception:
                pass

        return {"success": True, "local_path": final_path}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
# 4. Upload / get skills
# ═══════════════════════════════════════════════════════════

SKILLS_LOCAL = os.path.join(PROJECT_ROOT, "memory", "cloud", "skills.json")
SKILLS_REMOTE = "skills/skills.json"


def upload_skill(skill: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a skill to the local skills file, then upload it.
    A skill looks like:
        {"name": "...", "source": "...", "learned_at": "..."}
    """
    api, repo_id = _get_api()
    if not api:
        return {"success": False, "error": "Cloud not configured"}

    os.makedirs(os.path.dirname(SKILLS_LOCAL), exist_ok=True)

    # Load existing
    skills = []
    if os.path.exists(SKILLS_LOCAL):
        try:
            with open(SKILLS_LOCAL, "r", encoding="utf-8") as f:
                skills = json.load(f)
        except Exception:
            skills = []

    # Add timestamp if missing
    if "learned_at" not in skill:
        skill["learned_at"] = datetime.now().isoformat()

    skills.append(skill)

    # Save locally
    try:
        with open(SKILLS_LOCAL, "w", encoding="utf-8") as f:
            json.dump(skills, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return {"success": False, "error": f"Local save failed: {e}"}

    # Upload
    if not _ensure_repo(api, repo_id):
        return {"success": False, "error": "Could not open repo"}

    try:
        api.upload_file(
            path_or_fileobj=SKILLS_LOCAL,
            path_in_repo=SKILLS_REMOTE,
            repo_id=repo_id,
            repo_type=REPO_TYPE,
            token=api.token,
        )
        return {"success": True, "total_skills": len(skills)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_skills() -> Dict[str, Any]:
    """Download and return skills list from cloud."""
    if HfApi is None or hf_hub_download is None:
        return {"success": False, "error": "huggingface_hub not installed"}

    api, repo_id = _get_api()
    if not api:
        return {"success": False, "error": "Cloud not configured"}

    try:
        path = hf_hub_download(
            repo_id=repo_id,
            filename=SKILLS_REMOTE,
            repo_type=REPO_TYPE,
            token=api.token,
        )
        with open(path, "r", encoding="utf-8") as f:
            skills = json.load(f)
        return {"success": True, "count": len(skills), "skills": skills}
    except Exception as e:
        return {"success": False, "error": str(e), "skills": []}


# ═══════════════════════════════════════════════════════════
# 5. Save workspace snapshot (small files only)
# ═══════════════════════════════════════════════════════════

def save_snapshot(name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save a JSON snapshot to cloud under snapshots/<name>.json.
    Use for small state (progress, counters, metadata).
    """
    api, repo_id = _get_api()
    if not api:
        return {"success": False, "error": "Cloud not configured"}

    if not _ensure_repo(api, repo_id):
        return {"success": False, "error": "Could not open repo"}

    local_path = os.path.join(PROJECT_ROOT, "memory", "cloud", f"{name}.json")
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    try:
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return {"success": False, "error": f"Local save failed: {e}"}

    try:
        api.upload_file(
            path_or_fileobj=local_path,
            path_in_repo=f"snapshots/{name}.json",
            repo_id=repo_id,
            repo_type=REPO_TYPE,
            token=api.token,
        )
        return {"success": True, "remote": f"snapshots/{name}.json"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
# 6. Status
# ═══════════════════════════════════════════════════════════

def status() -> Dict[str, Any]:
    """Show cloud connection status."""
    api, repo_id = _get_api()
    if not api:
        return {
            "connected": False,
            "reason": "No token in .env, or huggingface_hub missing",
        }
    try:
        user = api.whoami()
        return {
            "connected": True,
            "user": user.get("name"),
            "repo_id": repo_id,
            "repo_url": f"https://huggingface.co/datasets/{repo_id}",
        }
    except Exception as e:
        return {"connected": False, "reason": str(e)}


# ═══════════════════════════════════════════════════════════
# Self-test
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=== Cloud Memory ===")
    print()
    print("1) الحالة:")
    s = status()
    if s.get("connected"):
        print(f"   ✅ متصل")
        print(f"   المستخدم: {s['user']}")
        print(f"   المستودع: {s['repo_id']}")
        print(f"   الرابط: {s['repo_url']}")
    else:
        print(f"   ❌ غير متصل: {s.get('reason')}")
        raise SystemExit(1)

    print()
    print("2) الملفات في السحابة:")
    r = list_reports()
    if r.get("success"):
        for f in r.get("files", []):
            print(f"   • {f}")
        print(f"   المجموع: {r['count']}")
    else:
        print(f"   ❌ {r.get('error')}")
