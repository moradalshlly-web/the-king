"""
brain/project_scanner.py
========================
Scans the MOROAI project and produces a manifest of all files.
Used by /evolve to know what already exists before proposing changes.
"""

import os
from typing import Dict, Any

try:
    from .core_paths import PROJECT_ROOT
except ImportError:
    from core_paths import PROJECT_ROOT


SCAN_DIRS = ["brain", "tools", "providers", "memory", "web", "config"]

SKIP_NAMES = {
    "__pycache__", ".git", "_backups", ".moroai",
    "node_modules", ".venv", "venv", ".pytest_cache",
}

INCLUDE_EXTS = {".py", ".md", ".json", ".yaml", ".yml"}

TRIPLE_DQ = chr(34) * 3
TRIPLE_SQ = chr(39) * 3
NL = chr(10)


def _should_skip(name: str) -> bool:
    return name in SKIP_NAMES or name.startswith(".")


def _extract_python_info(filepath: str) -> Dict[str, Any]:
    info = {"description": "", "classes": [], "functions": []}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return info

    head = content[:1000]
    for quote in (TRIPLE_DQ, TRIPLE_SQ):
        if quote in head:
            start = content.find(quote) + 3
            end = content.find(quote, start)
            if end > start:
                docstring = content[start:end]
                for raw_line in docstring.split(NL):
                    line = raw_line.strip()
                    if not line:
                        continue
                    if line.endswith(".py") and "/" in line:
                        continue
                    if len(line) > 3 and len(set(line)) <= 2:
                        continue
                    if len(line) < 4:
                        continue
                    info["description"] = line
                    break
            break

    for line in content.split(NL):
        if line.startswith("class "):
            name = line[6:].split("(")[0].split(":")[0].strip()
            if name:
                info["classes"].append(name)
        elif line.startswith("def "):
            name = line[4:].split("(")[0].strip()
            if name:
                info["functions"].append(name)

    return info


def scan_project() -> Dict[str, Any]:
    manifest = {
        "root": PROJECT_ROOT,
        "directories": {},
        "total_files": 0,
        "total_bytes": 0,
    }

    for scan_dir in SCAN_DIRS:
        full_dir = os.path.join(PROJECT_ROOT, scan_dir)
        if not os.path.isdir(full_dir):
            continue

        files = []
        for dirpath, dirnames, filenames in os.walk(full_dir):
            dirnames[:] = [d for d in dirnames if not _should_skip(d)]

            for fname in filenames:
                if _should_skip(fname):
                    continue
                ext = os.path.splitext(fname)[1].lower()
                if ext not in INCLUDE_EXTS:
                    continue

                full_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(full_path, PROJECT_ROOT)
                try:
                    size = os.path.getsize(full_path)
                except OSError:
                    continue

                info = {"path": rel_path, "size": size, "ext": ext}
                if ext == ".py":
                    info.update(_extract_python_info(full_path))

                files.append(info)
                manifest["total_files"] += 1
                manifest["total_bytes"] += size

        manifest["directories"][scan_dir] = files

    return manifest


def manifest_prompt() -> str:
    m = scan_project()
    header = "## PROJECT MANIFEST (" + str(m["total_files"]) + " files, " + str(m["total_bytes"] // 1024) + " KB)"
    lines = [header, ""]

    for dirname, files in m["directories"].items():
        if not files:
            continue
        lines.append("### " + dirname + "/")
        for f in files:
            size_kb = max(1, f["size"] // 1024)
            desc = f.get("description", "")
            line = "  - " + f["path"] + " (" + str(size_kb) + " KB)"
            if desc:
                line += " -- " + desc
            lines.append(line)

            classes = f.get("classes", [])
            functions = f.get("functions", [])
            if classes:
                lines.append("      classes: " + ", ".join(classes[:5]))
            if functions:
                lines.append("      funcs: " + ", ".join(functions[:8]))
        lines.append("")

    return NL.join(lines)


def manifest_summary() -> str:
    m = scan_project()
    lines = ["Project: " + str(m["total_files"]) + " files, " + str(m["total_bytes"] // 1024) + " KB"]
    for dirname, files in m["directories"].items():
        lines.append("  " + dirname.ljust(12) + " : " + str(len(files)) + " files")
    return NL.join(lines)


if __name__ == "__main__":
    print(manifest_summary())
    print()
    print("--- first 60 lines of manifest_prompt ---")
    prompt = manifest_prompt()
    print(NL.join(prompt.split(NL)[:60]))
