"""
brain/session.py
================

Session lifecycle manager for MOROAI.

Responsibilities:
    - On session END:
        1. Create a Git checkpoint (last known good state)
        2. Take a snapshot of the project into a new workspace session
        3. Save conversation reference + metadata
        4. Trigger background work (in background, non-blocking)
    - On session START:
        1. Check for pending workspace sessions
        2. Present them to the user for review

Design:
    - No external dependencies.
    - Background work is a stub for now; it will be replaced by the
      background agent in a future phase.
    - Uses CheckpointManager + WorkspaceManager.

Inspiration (no code copied):
    - aceclaw/self-learning.md: SessionEndExtractor pattern
    - OpenHands session manager: on_close / on_start lifecycle
    - hermes-agent: session context as JSON
    - SafeLoop: local flight recorder for long-running agents
"""

import os
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict

try:
    from .core_paths import (
        PROJECT_ROOT, SESSION_STATE_FILE, CONVERSATION_LOG,
    )
except ImportError:
    from core_paths import (
        PROJECT_ROOT, SESSION_STATE_FILE, CONVERSATION_LOG,
    )

from memory.checkpoint import CheckpointManager
from memory.workspace import (
    WorkspaceManager,
    STATUS_READY,
    STATUS_PENDING,
)


# ============================================================
# Session Lifecycle
# ============================================================

class SessionLifecycle:
    """Manages the start and end of a MOROAI session."""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = os.path.abspath(project_root or PROJECT_ROOT)
        self.checkpoints = CheckpointManager(self.project_root)
        self.workspace = WorkspaceManager(self.project_root)

    # -------- Session END --------

    def on_session_end(
        self,
        conversation_ref: Optional[str] = None,
        note: str = "",
    ) -> Dict:
        """
        Called when the user closes the session.

        Steps:
            1. Create a checkpoint (if there are changes).
            2. Create a new workspace session (copy of project).
            3. Save session state to disk.
            4. Mark for background processing.

        Returns a summary dict.
        """
        summary = {
            "checkpoint_hash": None,
            "session_id": None,
            "started_at": self._now(),
            "status": "ok",
        }

        # 1. Checkpoint (only if there are changes)
        try:
            ck_hash = self.checkpoints.create("Session end")
            summary["checkpoint_hash"] = ck_hash
        except Exception as e:
            summary["status"] = f"checkpoint_error: {e}"

        # 2. Create isolated workspace session
        try:
            sid = self.workspace.create_session(
                conversation_ref=conversation_ref,
                note=note or "Auto session snapshot at close",
            )
            summary["session_id"] = sid
        except Exception as e:
            summary["status"] = f"workspace_error: {e}"

        # 3. Save session state (so we can find it on next launch)
        self._save_state({
            "last_session_id": summary["session_id"],
            "last_checkpoint": summary["checkpoint_hash"],
            "closed_at": self._now(),
            "status": "closed",
        })

        return summary

    # -------- Session START --------

    def on_session_start(self) -> Dict:
        """
        Called when the user reopens MOROAI.

        Checks:
            - Is there a pending workspace session to review?
            - What was the last checkpoint?

        Returns a dict with:
            pending_reviews : list of sessions awaiting decision
            last_checkpoint : last successful checkpoint hash
            last_session_id : ID of the previous session
        """
        state = self._load_state()

        # Look for READY sessions (background work finished)
        ready = self.workspace.pending_reviews()

        # If a session was left as PENDING (background never ran),
        # promote it to READY with a generic note.
        stale = self.workspace.list_sessions(status=STATUS_PENDING)
        for s in stale:
            self.workspace.mark_ready(
                session_id=s["id"],
                changes_summary="(Background processing not yet implemented)",
                files_changed=[],
            )
        if stale:
            ready = self.workspace.pending_reviews()

        # Last checkpoint
        last_cp = self.checkpoints.last_successful()

        return {
            "pending_reviews": ready,
            "last_checkpoint": last_cp,
            "last_session_id": state.get("last_session_id"),
            "closed_at": state.get("closed_at"),
        }

    # -------- Helpers --------

    def _state_path(self) -> str:
        return os.path.join(self.project_root, SESSION_STATE_FILE)

    def _save_state(self, data: Dict) -> None:
        path = self._state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    import tempfile
    import shutil

    tmp = tempfile.mkdtemp()
    try:
        # Prepare a fake project
        with open(os.path.join(tmp, "app.py"), "w") as f:
            f.write("print('hello')\n")

        sl = SessionLifecycle(tmp)

        # 1. No state yet
        info = sl.on_session_start()
        print(f"Initial pending_reviews: {len(info['pending_reviews'])}")
        assert len(info["pending_reviews"]) == 0

        # 2. Simulate a session end
        with open(os.path.join(tmp, "app.py"), "w") as f:
            f.write("print('hello v2')\n")
        summary = sl.on_session_end(
            conversation_ref="conv-001",
            note="Test close",
        )
        print(f"Session ended: {summary['session_id']}")
        assert summary["session_id"] is not None
        assert summary["checkpoint_hash"] is not None

        # 3. Restart → should show pending review
        sl2 = SessionLifecycle(tmp)
        info = sl2.on_session_start()
        print(f"Pending reviews after restart: {len(info['pending_reviews'])}")
        assert len(info["pending_reviews"]) == 1

        # 4. Accept the changes
        sid = info["pending_reviews"][0]["id"]
        assert sl2.workspace.accept(sid) is True
        print("Changes accepted.")

        print("\n✅ All session tests passed.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
