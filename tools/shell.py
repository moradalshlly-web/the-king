"""
tools/shell.py
==============

Safe shell command execution for MOROAI.

Security model:
    - Allowlist of safe binaries (no sudo, no rm -rf, etc.)
    - Blocks shell metacharacters: ; | & ` $() > <
    - Enforces cwd inside the project sandbox
    - Timeout enforced (default 30s)
    - Output capped (default 50KB)
    - Returns structured dict, never raises

Inspiration (no code copied):
    - SWE-Agent: allowlist of commands + dangerous pattern block
    - OpenHands runtime: sandboxed execution
    - Aider: subprocess with shell=False
"""

import os
import shlex
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any


DEFAULT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

# Commands that are always allowed (safe, read-only or project-local)
ALLOWED_COMMANDS = {
    # Navigation / inspection
    "ls", "pwd", "cat", "head", "tail", "wc", "file", "stat",
    "grep", "find", "which", "tree", "du", "df",
    # Text processing
    "echo", "printf", "sed", "awk", "sort", "uniq", "cut", "tr",
    # Python (project-local only)
    "python", "python3", "pip", "pip3",
    # Node
    "node", "npm", "npx",
    # Git (only safe subcommands, checked separately)
    "git",
    # Misc safe
    "date", "whoami", "env", "sleep",
    "mkdir", "touch", "cp",
}

# Git subcommands considered safe (read-only or local)
SAFE_GIT_SUBCOMMANDS = {
    "status", "log", "diff", "show", "branch", "add", "commit",
    "stash", "checkout", "restore", "rev-parse", "config",
    "remote", "fetch", "pull",
}

# Git subcommands explicitly FORBIDDEN
FORBIDDEN_GIT = {
    "push",  # require manual approval
    "reset",
    "rebase",
    "clean",
    "filter-branch",
    "gc",
}

# Patterns that are always forbidden in any command
FORBIDDEN_PATTERNS = [
    "rm -rf", "rm -fr",
    "sudo", "su ",
    "chmod", "chown", "chgrp",
    "> /", ">> /",
    "curl |", "wget |",
    "curl|", "wget|",
    "| sh", "| bash", "|sh", "|bash",
    "eval ", "exec ",
    "dd if=",
    "mkfs", "fdisk",
    ":(){",  # fork bomb
]

# Shell metacharacters that we refuse (prevents command chaining)
FORBIDDEN_METACHARS = [";", "|", "&", "`", "$(", "${", ">", "<"]


class ShellOps:
    """Safe shell execution restricted to a root directory."""

    def __init__(self, root: Optional[str] = None,
                 timeout: int = 30,
                 max_output: int = 50_000):
        self.root = Path(root or DEFAULT_ROOT).resolve()
        self.timeout = timeout
        self.max_output = max_output

    # -------- Validation --------

    def is_safe_command(self, cmd: str) -> Dict[str, Any]:
        """Return {safe: bool, reason: str}."""
        if not cmd or not cmd.strip():
            return {"safe": False, "reason": "Empty command"}

        raw = cmd.strip()

        # 1. Forbidden patterns
        lower = raw.lower()
        for pat in FORBIDDEN_PATTERNS:
            if pat in lower:
                return {"safe": False, "reason": f"Forbidden pattern: '{pat}'"}

        # 2. Forbidden metacharacters
        for ch in FORBIDDEN_METACHARS:
            if ch in raw:
                return {"safe": False, "reason": f"Forbidden metacharacter: '{ch}'"}

        # 3. Parse with shlex
        try:
            parts = shlex.split(raw)
        except ValueError as e:
            return {"safe": False, "reason": f"Parse error: {e}"}

        if not parts:
            return {"safe": False, "reason": "Empty command"}

        binary = parts[0]

        # 4. Binary must be in allowlist
        if binary not in ALLOWED_COMMANDS:
            return {"safe": False, "reason": f"Command '{binary}' not in allowlist"}

        # 5. Special handling for git
        if binary == "git":
            if len(parts) < 2:
                return {"safe": False, "reason": "git requires a subcommand"}
            sub = parts[1].lower()
            if sub in FORBIDDEN_GIT:
                return {"safe": False, "reason": f"git {sub} is forbidden"}
            if sub not in SAFE_GIT_SUBCOMMANDS:
                return {"safe": False, "reason": f"git {sub} not in safe list"}

        # 6. pip / npm special: block publish/global installs
        if binary in ("pip", "pip3", "npm"):
            risky = ("publish", "--global", "-g", "uninstall")
            for r in risky:
                if r in parts:
                    return {"safe": False, "reason": f"'{r}' is forbidden"}

        return {"safe": True, "reason": ""}

    # -------- Execution --------

    def run(self, cmd: str, cwd: Optional[str] = None,
            timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        Run a shell command after validation.

        Returns:
            {success, stdout, stderr, exit_code, error, blocked}
        """
        # 1. Validate
        check = self.is_safe_command(cmd)
        if not check["safe"]:
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "error": f"Blocked: {check['reason']}",
                "blocked": True,
            }

        # 2. Resolve cwd (must be inside root)
        try:
            work_dir = Path(cwd or self.root)
            if not work_dir.is_absolute():
                work_dir = self.root / work_dir
            work_dir = work_dir.resolve()
            work_dir.relative_to(self.root)
        except (ValueError, Exception):
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "error": "cwd is outside sandbox",
                "blocked": True,
            }

        # 3. Execute
        try:
            result = subprocess.run(
                shlex.split(cmd),
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=timeout or self.timeout,
                shell=False,  # critical: no shell interpretation
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "error": f"Timeout after {timeout or self.timeout}s",
                "blocked": False,
            }
        except FileNotFoundError as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "error": f"Binary not found: {e}",
                "blocked": False,
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "error": f"{type(e).__name__}: {e}",
                "blocked": False,
            }

        # 4. Cap output
        stdout = result.stdout[: self.max_output]
        stderr = result.stderr[: self.max_output]

        return {
            "success": result.returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": result.returncode,
            "error": None if result.returncode == 0 else f"Exit code {result.returncode}",
            "blocked": False,
        }


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    import tempfile
    import shutil

    tmp = tempfile.mkdtemp()
    try:
        sh = ShellOps(tmp)

        # 1. Safe command
        r = sh.run("pwd")
        print(f"pwd: {r['success']} -> {r['stdout'].strip()}")
        assert r["success"]

        # 2. Forbidden: rm -rf
        r = sh.run("rm -rf /tmp")
        print(f"rm -rf blocked: {r['blocked']} ({r['error']})")
        assert r["blocked"]

        # 3. Forbidden: sudo
        r = sh.run("sudo ls")
        print(f"sudo blocked: {r['blocked']}")
        assert r["blocked"]

        # 4. Forbidden: pipe
        r = sh.run("ls | grep foo")
        print(f"pipe blocked: {r['blocked']}")
        assert r["blocked"]

        # 5. Forbidden: command substitution
        r = sh.run("echo $(whoami)")
        print(f"substitution blocked: {r['blocked']}")
        assert r["blocked"]

        # 6. Forbidden: not in allowlist
        r = sh.run("bash -c 'echo hi'")
        print(f"bash blocked: {r['blocked']}")
        assert r["blocked"]

        # 7. Safe git status
        r = sh.run("git status", cwd=tmp)
        # May fail because tmp is not a git repo, but should not be BLOCKED
        print(f"git status blocked={r['blocked']} exit={r['exit_code']}")
        assert not r["blocked"]

        # 8. Forbidden: git push
        r = sh.run("git push")
        print(f"git push blocked: {r['blocked']}")
        assert r["blocked"]

        # 9. Safe echo
        r = sh.run("echo hello")
        print(f"echo: {r['success']} -> {r['stdout'].strip()}")
        assert r["success"] and "hello" in r["stdout"]

        # 10. Escape cwd
        r = sh.run("pwd", cwd="/etc")
        print(f"cwd escape blocked: {r['blocked']}")
        assert r["blocked"]

        print("\n✅ All ShellOps tests passed.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
