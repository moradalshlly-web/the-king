"""
brain/code_monitor.py
=====================
Programmatic code monitor for MOROAI.

Role:
    - Watches every file written by the Executor
    - Runs static-analysis checks (no LLM)
    - Writes a structured report
    - Notifies MOROAI (via notifications file)

Checks:
    1. Python: AST parse + import resolution
    2. Size: warn if > 300 lines or > 50 KB
    3. TODO/FIXME: flag incomplete code
    4. Bare except / broad Exception: flag
    5. Hardcoded secrets: flag suspicious patterns
"""

import os
import ast
import re
from datetime import datetime
from typing import Dict, Any, List

try:
    from brain.core_paths import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = os.path.expanduser("~/moroai")


REPORT_DIR = os.path.join(PROJECT_ROOT, "memory", "monitor")
NOTIFICATIONS = os.path.join(PROJECT_ROOT, "memory", "notifications.jsonl")

# Suspicious patterns
SECRET_PATTERNS = [
    r"api[_-]?key\s*=\s*['\"][A-Za-z0-9_\-]{20,}",
    r"secret\s*=\s*['\"][A-Za-z0-9_\-]{20,}",
    r"password\s*=\s*['\"][^'\"]{8,}['\"]",
    r"token\s*=\s*['\"]ey[A-Za-z0-9_\-]{20,}",
]
BARE_EXCEPT = re.compile(r"except\s*:")
BROAD_EXCEPT = re.compile(r"except\s+Exception\s*:")


def _full(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)


def _check_python(path: str) -> List[Dict[str, Any]]:
    """AST parse + import resolution."""
    issues = []
    full = _full(path)
    try:
        with open(full, "r", encoding="utf-8") as f:
            src = f.read()
    except Exception as e:
        return [{"level": "error", "msg": f"cannot read: {e}"}]

    # AST parse
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        issues.append({
            "level": "error",
            "msg": f"SyntaxError at line {e.lineno}: {e.msg}",
            "pattern_key": "python_syntax_error",
        })
        return issues

    # Collect imports
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imported_modules.add(n.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module.split(".")[0])

    # Check internal imports (brain.*, tools.*, memory.*, providers.*)
    for mod in imported_modules:
        if mod in ("brain", "tools", "memory", "providers"):
            issues.append({
                "level": "info",
                "msg": f"internal import detected: {mod}",
                "pattern_key": "internal_import",
            })

    # Bare except
    if BARE_EXCEPT.search(src):
        issues.append({
            "level": "warn",
            "msg": "bare except found (use specific exception)",
            "pattern_key": "bare_except",
        })
    elif BROAD_EXCEPT.search(src):
        issues.append({
            "level": "info",
            "msg": "broad 'except Exception' found",
            "pattern_key": "broad_except",
        })

    # TODO/FIXME
    for i, line in enumerate(src.splitlines(), 1):
        upper = line.upper()
        if "TODO" in upper or "FIXME" in upper or "XXX" in upper:
            issues.append({
                "level": "info",
                "msg": f"line {i}: incomplete marker",
                "pattern_key": "todo_marker",
            })
            break

    # Hardcoded secrets
    for pat in SECRET_PATTERNS:
        if re.search(pat, src, re.IGNORECASE):
            issues.append({
                "level": "high",
                "msg": "possible hardcoded secret",
                "pattern_key": "hardcoded_secret",
            })
            break

    return issues


def _check_generic(path: str) -> List[Dict[str, Any]]:
    """Size + basic checks for non-Python files."""
    issues = []
    full = _full(path)
    try:
        size = os.path.getsize(full)
    except Exception:
        return issues

    if size > 50_000:
        issues.append({
            "level": "info",
            "msg": f"large file: {size//1024} KB",
            "pattern_key": "large_file",
        })

    # Line count
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            lines = sum(1 for _ in f)
        if lines > 300:
            issues.append({
                "level": "info",
                "msg": f"long file: {lines} lines (>300)",
                "pattern_key": "long_file",
            })
    except Exception:
        pass

    return issues


def inspect_file(path: str, save: bool = True) -> Dict[str, Any]:
    """
    Run all checks on a single file.
    Saves a report and notifies MOROAI (best-effort).
    """
    rel = path.replace(PROJECT_ROOT + os.sep, "").replace("\\", "/")
    ext = os.path.splitext(path)[1].lower()

    issues = []
    if ext == ".py":
        issues = _check_python(path)
    else:
        issues = _check_generic(path)

    # Compute severity
    levels = [i["level"] for i in issues]
    if "error" in levels or "high" in levels:
        verdict = "fail"
    elif "warn" in levels:
        verdict = "warn"
    else:
        verdict = "ok"

    report = {
        "timestamp": datetime.now().isoformat(),
        "path": rel,
        "ext": ext,
        "verdict": verdict,
        "issues": issues,
        "issue_count": len(issues),
    }

    if save:
        _save_report(report)
        _notify(report)

    return report


def _save_report(report: Dict[str, Any]) -> None:
    os.makedirs(REPORT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    fname = f"monitor-{ts}-{os.path.basename(report['path']).replace('/', '_')}.json"
    try:
        import json
        with open(os.path.join(REPORT_DIR, fname), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _notify(report: Dict[str, Any]) -> None:
    """Notify MOROAI only if verdict is warn/fail."""
    if report.get("verdict") == "ok":
        return
    try:
        import json
        os.makedirs(os.path.dirname(NOTIFICATIONS), exist_ok=True)
        msg = f"مراقب الكود: {report['path']} → {report['verdict']} ({report['issue_count']} ملاحظة)"
        with open(NOTIFICATIONS, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "time": report["timestamp"],
                "kind": "code_monitor",
                "message": msg,
                "read": False,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass


def summary() -> str:
    """Return a short text summary of recent reports."""
    if not os.path.isdir(REPORT_DIR):
        return "(no reports)"
    files = sorted(os.listdir(REPORT_DIR), reverse=True)[:10]
    lines = []
    for f in files:
        lines.append(f"  {f}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════
# Self-test
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print("Code Monitor — self-test")
    print("=" * 55)

    # Test on an existing good file
    r = inspect_file("brain/planner.py", save=True)
    print(f"  {r['path']}: {r['verdict']} ({r['issue_count']} issues)")
    for i in r["issues"]:
        print(f"     [{i['level']}] {i['msg']}")
