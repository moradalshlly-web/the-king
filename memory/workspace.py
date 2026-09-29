"""
memory/workspace.py
===================

Isolated workspace for MOROAI background work.

When the user closes the session, MOROAI:
    1. Takes a snapshot of the current project
    2. Copies it into .moroai/workspace/sessions/<id>/project/
    3. Stores session metadata (start, end, conversation ref, status)
    4. The background agent can modify this copy safely
    5. On next launch, MOROAI presents the session for review

Session lifecycle:
    pending  → the agent is still working or session not yet reviewed
    ready    → the agent finished, waiting for user's decision
    accepted → user merged changes back
    rejected → user discarded changes
    deleted  → session removed

Design:
    - Never touches the original project until user accepts.
    - Each session is fully isolated.
    - Metadata is JSON; project copy is plain files.
    - Optional: a .diff file showing changes.

Inspiration (no code copied):
    - aceclaw/self-learning.md: SessionEndExtractor pattern
    - learning-scratchpad-loop: repo-local scratchpad
    - SafeLoop: local flight recorder for long-running agents
    - hermes-agent: pre-rollback snapshot pattern
"""

import os
import json
import shutil
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional


# ============================================================
# Constants
# ============================================================

WORKSPACE_DIRNAME = ".moroai/workspace"
SESSIONS_DIRNAME = "sessions"

STATUS_PENDING = "pending"
STATUS_READY = "ready"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"
STATUS_DELETED = "deleted"

# Folders/files to skip when copying the project
SKIP_PATTERNS = {
    ".git", "__pycache__", "node_modules", ".moroai",
    ".venv", "venv", ".env", ".pytest_cache",
}


# ============================================================
# Workspace Manager
# ============================================================

class WorkspaceManager:
    """Manages isolated background-work sessions."""

    def __init__(self, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.workspace_dir = os.path.join(self.project_root, WORKSPACE_DIRNAME)
        self.sessions_dir = os.path.join(self.workspace_dir, SESSIONS_DIRNAME)
        os.makedirs(self.sessions_dir, exist_ok=True)

    # -------- Paths --------

    def _session_dir(self, session_id: str) -> str:
        return os.path.join(self.sessions_dir, session_id)

    def _session_project_dir(self, session_id: str) -> str:
        return os.path.join(self._session_dir(session_id), "project")

    def _session_metadata_path(self, session_id: str) -> str:
        return os.path.join(self._session_dir(session_id), "metadata.json")

    # -------- Session Creation --------

    def create_session(
        self,
        conversation_ref: Optional[str] = None,
        note: str = "",
    ) -> str:
        """
        Create a new isolated session.
        Copies the current project into the session folder.
        Returns the session_id.
        """
        session_id = self._new_id()
        session_dir = self._session_dir(session_id)
        project_copy = self._session_project_dir(session_id)

        os.makedirs(session_dir, exist_ok=True)

        # Copy project into the session (skip heavy/irrelevant folders)
        shutil.copytree(
            self.project_root,
            project_copy,
            ignore=self._ignore_fn,
            dirs_exist_ok=False,
        )

        # Write metadata
        metadata = {
            "id": session_id,
            "created_at": self._now(),
            "updated_at": self._now(),
            "status": STATUS_PENDING,
            "conversation_ref": conversation_ref or "",
            "note": note,
            "changes_summary": "",
            "files_changed": [],
        }
        self._write_metadata(session_id, metadata)

        return session_id

    def _new_id(self) -> str:
        short = uuid.uuid4().hex[:8]
        return f"{self._now_compact()}-{short}"

    # -------- Session Update --------

    def mark_ready(
        self,
        session_id: str,
        changes_summary: str = "",
        files_changed: Optional[List[str]] = None,
    ) -> None:
        """Mark a session as ready for user review."""
        metadata = self._read_metadata(session_id)
        if not metadata:
            return
        metadata["status"] = STATUS_READY
        metadata["updated_at"] = self._now()
        metadata["changes_summary"] = changes_summary
        metadata["files_changed"] = files_changed or []
        self._write_metadata(session_id, metadata)

    def update_note(self, session_id: str, note: str) -> None:
        """Append or replace the session note."""
        metadata = self._read_metadata(session_id)
        if not metadata:
            return
        metadata["note"] = note
        metadata["updated_at"] = self._now()
        self._write_metadata(session_id, metadata)

    # -------- Session Listing --------

    def list_sessions(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """List all sessions, newest first. Filter by status optionally."""
        sessions = []
        if not os.path.isdir(self.sessions_dir):
            return sessions

        for sid in os.listdir(self.sessions_dir):
            metadata = self._read_metadata(sid)
            if not metadata:
                continue
            if status and metadata.get("status") != status:
                continue
            sessions.append(metadata)

        sessions.sort(key=lambda m: m.get("created_at", ""), reverse=True)
        return sessions[:limit]

    def pending_reviews(self) -> List[Dict]:
        """Return sessions waiting for user decision."""
        return self.list_sessions(status=STATUS_READY)

    # -------- Session Acceptance / Rejection --------

    def accept(self, session_id: str) -> bool:
        """
        Copy the session's modified files back into the project.
        Does NOT overwrite files that don't exist in the session copy.

        Returns True on success.
        """
        project_copy = self._session_project_dir(session_id)
        if not os.path.isdir(project_copy):
            return False

        try:
            self._copy_back(project_copy, self.project_root)
        except Exception:
            return False

        metadata = self._read_metadata(session_id)
        if metadata:
            metadata["status"] = STATUS_ACCEPTED
            metadata["updated_at"] = self._now()
            self._write_metadata(session_id, metadata)
        return True

    def reject(self, session_id: str) -> bool:
        """Mark a session as rejected (keeps files for reference)."""
        metadata = self._read_metadata(session_id)
        if not metadata:
            return False
        metadata["status"] = STATUS_REJECTED
        metadata["updated_at"] = self._now()
        self._write_metadata(session_id, metadata)
        return True

    def delete(self, session_id: str) -> bool:
        """Fully delete a session directory."""
        session_dir = self._session_dir(session_id)
        if not os.path.isdir(session_dir):
            return False
        try:
            shutil.rmtree(session_dir)
            return True
        except Exception:
            return False

    # -------- Internal Helpers --------

    def _copy_back(self, source_dir: str, dest_dir: str) -> None:
        """Copy every file from source into dest, overwriting."""
        for root, dirs, files in os.walk(source_dir):
            dirs[:] = [d for d in dirs if d not in SKIP_PATTERNS]
            rel = os.path.relpath(root, source_dir)
            target_root = os.path.join(dest_dir, rel) if rel != "." else dest_dir
            os.makedirs(target_root, exist_ok=True)
            for fname in files:
                src = os.path.join(root, fname)
                dst = os.path.join(target_root, fname)
                shutil.copy2(src, dst)

    def _ignore_fn(self, dir_path, names):
        """Ignore function for shutil.copytree."""
        return [n for n in names if n in SKIP_PATTERNS]

    def _read_metadata(self, session_id: str) -> Optional[Dict]:
        path = self._session_metadata_path(session_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def _write_metadata(self, session_id: str, metadata: Dict) -> None:
        path = self._session_metadata_path(session_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _now_compact() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    import tempfile

    tmp = tempfile.mkdtemp()
    try:
        # Prepare a small fake project
        with open(os.path.join(tmp, "app.py"), "w") as f:
            f.write("print('v1')\n")
        os.makedirs(os.path.join(tmp, "sub"), exist_ok=True)
        with open(os.path.join(tmp, "sub", "readme.md"), "w") as f:
            f.write("# Hello\n")

        wm = WorkspaceManager(tmp)

        # 1. Create session
        sid = wm.create_session(note="Test session")
        print(f"Session created: {sid}")

        # 2. Verify copy exists and is isolated
        sdir = wm._session_project_dir(sid)
        assert os.path.exists(os.path.join(sdir, "app.py"))
        assert os.path.exists(os.path.join(sdir, "sub", "readme.md"))
        print("Copy verified.")

        # 3. Modify the copy (simulate background work)
        with open(os.path.join(sdir, "app.py"), "w") as f:
            f.write("print('v2 - modified')\n")

        wm.mark_ready(
            session_id=sid,
            changes_summary="Updated app.py to v2",
            files_changed=["app.py"],
        )

        # 4. Original should still be v1
        with open(os.path.join(tmp, "app.py")) as f:
            assert f.read() == "print('v1')\n"
        print("Original untouched.")

        # 5. Pending reviews
        pending = wm.pending_reviews()
        print(f"Pending: {len(pending)}")
        assert len(pending) == 1

        # 6. Accept
        ok = wm.accept(sid)
        print(f"Accept: {ok}")
        with open(os.path.join(tmp, "app.py")) as f:
            assert f.read() == "print('v2 - modified')\n"
        print("Changes copied back.")

        # 7. Delete
        assert wm.delete(sid) is True
        assert not os.path.exists(wm._session_dir(sid))
        print("Session deleted.")

        print("\n✅ All workspace tests passed.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
