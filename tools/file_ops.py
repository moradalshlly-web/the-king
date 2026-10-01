"""
tools/file_ops.py
=================

Safe file operations for MOROAI.

Security model:
    - All operations are restricted to a configurable ROOT directory
      (defaults to the MOROAI project root).
    - Paths are resolved to absolute form and checked to be inside ROOT.
    - Symlinks are NOT followed outside ROOT.
    - Delete requires explicit confirm=True.

Inspiration (no code copied):
    - OpenHands runtime: sandbox to project root
    - Pydantic AI tools: simple Python functions
    - SWE-Agent: safe file access patterns
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any


# Default sandbox root: MOROAI project directory
DEFAULT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)


class FileOps:
    """Safe file operations restricted to a root directory."""

    def __init__(self, root: Optional[str] = None):
        self.root = Path(root or DEFAULT_ROOT).resolve()

    # -------- Internal --------

    def _resolve(self, user_path: str) -> Path:
        """Resolve a user path and ensure it's inside the root."""
        p = Path(user_path)
        if not p.is_absolute():
            p = self.root / p
        p = p.resolve()
        # Check containment
        try:
            p.relative_to(self.root)
        except ValueError:
            raise PermissionError(
                f"Path '{user_path}' is outside the sandbox root."
            )
        return p

    # -------- Read --------

    def read_file(self, path: str, max_bytes: int = 1_000_000) -> Dict[str, Any]:
        """Read a text file. Returns {success, content, error, size}."""
        try:
            p = self._resolve(path)
        except PermissionError as e:
            return {"success": False, "content": "", "error": str(e), "size": 0}

        if not p.exists():
            return {"success": False, "content": "", "error": "File not found", "size": 0}
        if not p.is_file():
            return {"success": False, "content": "", "error": "Not a file", "size": 0}
        if p.stat().st_size > max_bytes:
            return {"success": False, "content": "", "error": f"File too large (>{max_bytes} bytes)", "size": 0}

        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            return {"success": True, "content": content, "error": None, "size": p.stat().st_size}
        except Exception as e:
            return {"success": False, "content": "", "error": str(e), "size": 0}

    # -------- Write --------

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Write text to a file (creates parent dirs). Returns {success, path, bytes_written, error}."""
        try:
            p = self._resolve(path)
        except PermissionError as e:
            return {"success": False, "path": "", "bytes_written": 0, "error": str(e)}

        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            try:
                from tools.sync_cloud import notify_change
                notify_change(str(p))
            except Exception:
                pass

            # Run deterministic verifier (only for small/quick checks)
            verification = None
            try:
                from tools.deterministic_verifier import verify_file
                verification = verify_file(str(p), save=True)
            except Exception:
                pass

            result = {
                "success": True,
                "path": str(p),
                "bytes_written": len(content.encode("utf-8")),
                "error": None,
            }
            if verification:
                result["verification"] = {
                    "passed": verification.get("passed"),
                    "score": verification.get("score"),
                    "failed": verification.get("failed_checks", []),
                }
            return result
        except Exception as e:
            return {"success": False, "path": str(p), "bytes_written": 0, "error": str(e)}

    def append_file(self, path: str, content: str) -> Dict[str, Any]:
        """Append text to a file (creates if missing)."""
        try:
            p = self._resolve(path)
        except PermissionError as e:
            return {"success": False, "path": "", "bytes_written": 0, "error": str(e)}

        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(content)
            try:
                from tools.sync_cloud import notify_change
                notify_change(str(p))
            except Exception:
                pass
            return {"success": True, "path": str(p), "bytes_written": len(content.encode("utf-8")), "error": None}
        except Exception as e:
            return {"success": False, "path": str(p), "bytes_written": 0, "error": str(e)}

    # -------- List --------

    def list_dir(self, path: str = ".", recursive: bool = False) -> Dict[str, Any]:
        """List files in a directory. Returns {success, items, error}."""
        try:
            p = self._resolve(path)
        except PermissionError as e:
            return {"success": False, "items": [], "error": str(e)}

        if not p.exists() or not p.is_dir():
            return {"success": False, "items": [], "error": "Not a directory"}

        items = []
        try:
            if recursive:
                for f in p.rglob("*"):
                    if f.is_file():
                        items.append(str(f.relative_to(self.root)))
            else:
                for f in p.iterdir():
                    rel = str(f.relative_to(self.root))
                    items.append(rel + ("/" if f.is_dir() else ""))
            items.sort()
            return {"success": True, "items": items, "error": None}
        except Exception as e:
            return {"success": False, "items": [], "error": str(e)}

    # -------- Exists / Info --------

    def exists(self, path: str) -> bool:
        try:
            p = self._resolve(path)
            return p.exists()
        except PermissionError:
            return False

    def info(self, path: str) -> Dict[str, Any]:
        try:
            p = self._resolve(path)
        except PermissionError as e:
            return {"success": False, "error": str(e)}
        if not p.exists():
            return {"success": False, "error": "Not found"}
        st = p.stat()
        return {
            "success": True,
            "path": str(p),
            "is_file": p.is_file(),
            "is_dir": p.is_dir(),
            "size": st.st_size,
            "modified": st.st_mtime,
        }

    # -------- Delete (requires confirm) --------

    def delete(self, path: str, confirm: bool = False) -> Dict[str, Any]:
        """Delete a file or empty directory. Requires confirm=True."""
        if not confirm:
            return {"success": False, "error": "Delete requires confirm=True"}

        try:
            p = self._resolve(path)
        except PermissionError as e:
            return {"success": False, "error": str(e)}

        if not p.exists():
            return {"success": False, "error": "Not found"}

        try:
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                p.rmdir()  # only empty dirs
            return {"success": True, "error": None}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -------- Mkdir --------

    def make_dir(self, path: str) -> Dict[str, Any]:
        try:
            p = self._resolve(path)
            p.mkdir(parents=True, exist_ok=True)
            return {"success": True, "path": str(p), "error": None}
        except Exception as e:
            return {"success": False, "path": "", "error": str(e)}


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    import tempfile
    import shutil

    tmp = tempfile.mkdtemp()
    try:
        ops = FileOps(tmp)

        # 1. Write
        r = ops.write_file("sub/hello.txt", "مرحبا MOROAI")
        print(f"Write: {r['success']} ({r['bytes_written']} bytes)")
        assert r["success"]

        # 2. Read
        r = ops.read_file("sub/hello.txt")
        print(f"Read: {r['success']} content='{r['content']}'")
        assert r["success"] and r["content"] == "مرحبا MOROAI"

        # 3. List
        r = ops.list_dir(".", recursive=True)
        print(f"List: {r['items']}")
        assert "sub/hello.txt" in r["items"]

        # 4. Sandbox escape test
        r = ops.read_file("/etc/passwd")
        print(f"Escape blocked: {not r['success']} ({r['error']})")
        assert not r["success"]

        r = ops.write_file("../../evil.txt", "bad")
        print(f"Write escape blocked: {not r['success']}")
        assert not r["success"]

        # 5. Delete without confirm
        r = ops.delete("sub/hello.txt", confirm=False)
        print(f"Delete without confirm: {not r['success']}")
        assert not r["success"]

        # 6. Delete with confirm
        r = ops.delete("sub/hello.txt", confirm=True)
        print(f"Delete with confirm: {r['success']}")
        assert r["success"]

        print("\n✅ All FileOps tests passed.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
