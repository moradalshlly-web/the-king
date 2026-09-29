"""
memory/checkpoint.py
====================

Git-based checkpointing for MOROAI.

Creates checkpoints of the project state using git.
Checkpoints are commits with a special prefix in the message.

Design:
    - Uses the project's git repo (not a separate shadow repo)
    - Auto-initializes git if not present
    - Creates a safety checkpoint before any restore (undo the undo)
    - No external dependencies

Inspiration (no code copied):
    - phlox/checkpoints.py: Git-based checkpointing
    - fabricatio-checkpoint: Shadow Git repositories
    - PraisonAI checkpoints: Shadow git checkpointing
    - hermes-agent: Pre-rollback snapshot pattern
"""

import os
import subprocess
from datetime import datetime, timezone
from typing import List, Dict, Optional


CHECKPOINT_PREFIX = "[CHECKPOINT]"


class CheckpointManager:
    """Manages project checkpoints using git."""

    def __init__(self, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self._ensure_git()

    # -------- Setup --------

    def _ensure_git(self) -> None:
        """Initialize git if not already done."""
        git_dir = os.path.join(self.project_root, ".git")
        if not os.path.exists(git_dir):
            self._git("init")
            self._git("config", "user.email", "moroai@local")
            self._git("config", "user.name", "MOROAI")

            gitignore = os.path.join(self.project_root, ".gitignore")
            if not os.path.exists(gitignore):
                with open(gitignore, "w", encoding="utf-8") as f:
                    f.write(
                        "node_modules/\n__pycache__/\n*.pyc\n.env\n*.log\n"
                        ".moroai/workspace/\n.moroai/checkpoints/\n"
                    )

            self._git("add", "-A")
            self._git(
                "commit", "-m",
                f"{CHECKPOINT_PREFIX} Initial state",
                check=False,
            )

    def _git(self, *args: str, check: bool = True) -> str:
        """Run a git command in the project directory."""
        result = subprocess.run(
            ["git"] + list(args),
            cwd=self.project_root,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout

    # -------- Public API --------

    def create(self, message: str = "Auto checkpoint") -> Optional[str]:
        """
        Create a checkpoint.
        Returns commit hash, or None if there are no changes to commit.
        """
        status = self._git("status", "--porcelain")
        if not status.strip():
            return None

        self._git("add", "-A")
        now = datetime.now(timezone.utc).isoformat()
        full_message = f"{CHECKPOINT_PREFIX} {message} ({now})"
        self._git("commit", "-m", full_message)

        return self._git("rev-parse", "HEAD").strip()

    def list(self, limit: int = 20) -> List[Dict[str, str]]:
        """List checkpoints (most recent first)."""
        try:
            output = self._git(
                "log",
                f"--grep={CHECKPOINT_PREFIX}",
                "-n", str(limit),
                "--format=%H|%ai|%s",
            )
        except RuntimeError:
            return []

        checkpoints = []
        for line in output.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) == 3:
                checkpoints.append({
                    "hash": parts[0],
                    "date": parts[1],
                    "message": parts[2].replace(CHECKPOINT_PREFIX, "").strip(),
                })
        return checkpoints

    def restore(self, commit_hash: Optional[str]) -> bool:
        """
        Restore working tree to a checkpoint.
        Creates a safety checkpoint before restoring (undo the undo).
        Returns False if commit_hash is None or empty.
        """
        if not commit_hash:
            return False

        try:
            self.create(f"Pre-restore to {commit_hash[:8]}")
            self._git("checkout", commit_hash, "--", ".")
            return True
        except RuntimeError:
            return False

    def last_successful(self) -> Optional[Dict[str, str]]:
        """Get the most recent checkpoint."""
        checkpoints = self.list(limit=1)
        return checkpoints[0] if checkpoints else None

    def count(self) -> int:
        """Total number of checkpoints."""
        return len(self.list(limit=10000))


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    import tempfile
    import shutil

    tmp = tempfile.mkdtemp()
    try:
        # 1. Create initial file BEFORE checkpoint manager
        test_file = os.path.join(tmp, "test.txt")
        with open(test_file, "w") as f:
            f.write("hello")

        cm = CheckpointManager(tmp)
        print(f"Initial checkpoints: {cm.count()}")

        # 2. Modify file → first checkpoint
        with open(test_file, "w") as f:
            f.write("hello v2")
        h1 = cm.create("First checkpoint")
        print(f"Checkpoint 1: {h1[:8] if h1 else 'none'}")

        # 3. Modify again → second checkpoint
        with open(test_file, "w") as f:
            f.write("world")
        h2 = cm.create("Second checkpoint")
        print(f"Checkpoint 2: {h2[:8] if h2 else 'none'}")

        # 4. No change → should return None
        h3 = cm.create("No changes")
        print(f"Checkpoint 3 (no changes): {h3}")

        # 5. List
        print(f"Total checkpoints: {cm.count()}")
        for cp in cm.list():
            print(f"  {cp['hash'][:8]} | {cp['message']}")

        # 6. Last
        last = cm.last_successful()
        print(f"Last: {last['hash'][:8] if last else 'none'}")

        # 7. Restore to first → content should be "hello v2"
        ok = cm.restore(h1)
        print(f"Restore to first: {ok}")
        with open(test_file) as f:
            content = f.read()
        print(f"Content after restore: {content}")
        assert content == "hello v2", "Restore failed!"

        # 8. Restore with None → should return False gracefully
        ok_none = cm.restore(None)
        print(f"Restore None: {ok_none}")
        assert ok_none is False

        print("\n✅ All tests passed.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
