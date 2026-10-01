"""
tools/deterministic_verifier.py
================================
Deterministic verifier — the first "inspector" in MOROAI.

Checks (no LLM, no internet):
    1. File existence + size
    2. Python syntax (py_compile)
    3. JSON / YAML syntax
    4. Local link references
    5. Fabrication guard: "claimed X" but X doesn't exist

Every result is saved to memory/learning.db (verifications + patterns).
"""

import os
import json
import subprocess
import importlib.util
from typing import Dict, Any, List, Optional

try:
    from brain.core_paths import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = os.path.expanduser("~/moroai")

# Optional: use YAML if available
try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


# ═══════════════════════════════════════════════════════════
# Individual checks
# ═══════════════════════════════════════════════════════════

def check_file_exists(path: str) -> Dict[str, Any]:
    """Is the file present? How big?"""
    full = path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)
    if not os.path.exists(full):
        return {
            "check": "file_exists",
            "passed": False,
            "score": 0.0,
            "findings": f"الملف غير موجود: {path}",
            "pattern_key": "file_missing",
        }
    size = os.path.getsize(full)
    return {
        "check": "file_exists",
        "passed": True,
        "score": 1.0,
        "findings": f"موجود ({size} بايت)",
        "size": size,
    }


def check_python_syntax(path: str) -> Dict[str, Any]:
    """Is this valid Python?"""
    full = path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)
    if not os.path.isfile(full):
        return {
            "check": "python_syntax",
            "passed": False,
            "score": 0.0,
            "findings": "الملف غير موجود",
            "pattern_key": "file_missing",
        }
    try:
        r = subprocess.run(
            ["python", "-m", "py_compile", full],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            return {
                "check": "python_syntax",
                "passed": True,
                "score": 1.0,
                "findings": "كود Python سليم",
            }
        return {
            "check": "python_syntax",
            "passed": False,
            "score": 0.0,
            "findings": r.stderr.strip()[:500] or "خطأ غير معروف",
            "pattern_key": "python_syntax_error",
        }
    except Exception as e:
        return {
            "check": "python_syntax",
            "passed": False,
            "score": 0.0,
            "findings": f"{type(e).__name__}: {e}",
            "pattern_key": "python_syntax_error",
        }


def check_json_syntax(path: str) -> Dict[str, Any]:
    full = path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)
    if not os.path.isfile(full):
        return {"check": "json_syntax", "passed": False, "score": 0.0,
                "findings": "غير موجود", "pattern_key": "file_missing"}
    try:
        with open(full, "r", encoding="utf-8") as f:
            json.load(f)
        return {"check": "json_syntax", "passed": True, "score": 1.0,
                "findings": "JSON سليم"}
    except Exception as e:
        return {"check": "json_syntax", "passed": False, "score": 0.0,
                "findings": str(e)[:500], "pattern_key": "json_syntax_error"}


def check_yaml_syntax(path: str) -> Dict[str, Any]:
    full = path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)
    if not os.path.isfile(full):
        return {"check": "yaml_syntax", "passed": False, "score": 0.0,
                "findings": "غير موجود", "pattern_key": "file_missing"}
    if not _HAS_YAML:
        return {"check": "yaml_syntax", "passed": True, "score": 0.5,
                "findings": "PyYAML غير مثبّت — تم التجاوز"}
    try:
        with open(full, "r", encoding="utf-8") as f:
            yaml.safe_load(f)
        return {"check": "yaml_syntax", "passed": True, "score": 1.0,
                "findings": "YAML سليم"}
    except Exception as e:
        return {"check": "yaml_syntax", "passed": False, "score": 0.0,
                "findings": str(e)[:500], "pattern_key": "yaml_syntax_error"}


def check_local_links(path: str) -> Dict[str, Any]:
    """For .md files — do local links point to existing files?"""
    full = path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)
    if not os.path.isfile(full):
        return {"check": "local_links", "passed": False, "score": 0.0,
                "findings": "غير موجود", "pattern_key": "file_missing"}

    broken = []
    try:
        with open(full, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        return {"check": "local_links", "passed": True, "score": 0.5,
                "findings": f"تعذّرت القراءة: {e}"}

    import re
    # Match [text](path) where path doesn't start with http
    for m in re.finditer(r"\[([^\]]+)\]\(([^)\s]+)\)", text):
        link = m.group(2)
        if link.startswith(("http://", "https://", "#", "mailto:")):
            continue
        # Strip anchor
        link_path = link.split("#", 1)[0]
        if not link_path:
            continue
        target = os.path.join(os.path.dirname(full), link_path)
        if not os.path.exists(target):
            broken.append(link)

    if not broken:
        return {"check": "local_links", "passed": True, "score": 1.0,
                "findings": "كل الروابط المحلية سليمة"}
    return {
        "check": "local_links",
        "passed": False,
        "score": max(0.0, 1.0 - len(broken) * 0.2),
        "findings": f"روابط مكسورة: {', '.join(broken[:5])}",
        "pattern_key": "broken_local_link",
    }


def check_claim(claim: str) -> Dict[str, Any]:
    """
    Fabrication guard: "I created X" — does X exist?
    Simple heuristic: look for a path-like substring.
    """
    import re
    # find something like path/to/file.ext
    m = re.search(r"([\w./-]+\.\w{1,5})", claim)
    if not m:
        return {"check": "claim", "passed": True, "score": 1.0,
                "findings": "لا يوجد ادعاء قابل للتحقق"}
    path = m.group(1)
    full = os.path.join(PROJECT_ROOT, path)
    if os.path.exists(full):
        return {"check": "claim", "passed": True, "score": 1.0,
                "findings": f"الملف المُدّعى موجود: {path}"}
    return {
        "check": "claim",
        "passed": False,
        "score": 0.0,
        "findings": f"ادعاء كاذب: '{path}' غير موجود",
        "pattern_key": "false_claim",
    }


# ═══════════════════════════════════════════════════════════
# High-level API
# ═══════════════════════════════════════════════════════════

def _route_check(path: str) -> List[Dict[str, Any]]:
    """Pick which checks to run based on file extension."""
    _, ext = os.path.splitext(path)
    ext = ext.lower()
    checks = [check_file_exists(path)]
    if ext == ".py":
        checks.append(check_python_syntax(path))
    elif ext == ".json":
        checks.append(check_json_syntax(path))
    elif ext in (".yaml", ".yml"):
        checks.append(check_yaml_syntax(path))
    elif ext == ".md":
        checks.append(check_local_links(path))
    return checks


def verify_file(path: str, save: bool = True) -> Dict[str, Any]:
    """
    Run all applicable checks on a file.
    Saves results to learning.db if save=True.
    """
    results = _route_check(path)

    # Overall
    all_passed = all(r.get("passed", False) for r in results)
    avg_score = sum(r.get("score", 0.0) for r in results) / max(len(results), 1)

    summary = {
        "target": path,
        "passed": all_passed,
        "score": round(avg_score, 3),
        "checks": results,
        "failed_checks": [r["check"] for r in results if not r.get("passed")],
    }

    # Save to memory
    if save:
        try:
            from memory.learning import LearningMemory
            m = LearningMemory()
            m.save_verification(
                target_type="file",
                target_ref=path,
                verifier="deterministic",
                passed=all_passed,
                score=avg_score,
                findings="; ".join(
                    f"{r['check']}: {r.get('findings','')}"
                    for r in results if not r.get("passed")
                )[:2000],
            )
            # Register failed patterns
            for r in results:
                if not r.get("passed") and r.get("pattern_key"):
                    m.record_pattern(
                        pattern_type=r.get("check", "unknown"),
                        pattern_key=r["pattern_key"],
                        severity="medium",
                        notes=r.get("findings", "")[:200],
                    )
        except Exception:
            pass

    return summary


def verify_claim(claim: str, save: bool = True) -> Dict[str, Any]:
    """Verify a textual claim about created files."""
    r = check_claim(claim)
    summary = {
        "claim": claim[:200],
        "passed": r.get("passed", False),
        "score": r.get("score", 0.0),
        "findings": r.get("findings", ""),
    }
    if save:
        try:
            from memory.learning import LearningMemory
            m = LearningMemory()
            m.save_verification(
                target_type="claim",
                target_ref=claim[:100],
                verifier="deterministic",
                passed=summary["passed"],
                score=summary["score"],
                findings=summary["findings"],
            )
            if not summary["passed"] and r.get("pattern_key"):
                m.record_pattern(
                    pattern_type="claim",
                    pattern_key=r["pattern_key"],
                    severity="high",
                    notes=summary["findings"][:200],
                )
        except Exception:
            pass
    return summary


# ═══════════════════════════════════════════════════════════
# Self-test
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  Deterministic Verifier — self-test")
    print("=" * 60)
    print()

    tests = [
        ("tools/file_ops.py", "Python — موجود وسليم"),
        ("brain/core.py", "Python — موجود وسليم"),
        ("memory/data/learning.db", "موجود (ليس Python)"),
        ("tools/nonexistent_file.py", "غير موجود — يجب أن يفشل"),
    ]

    for path, label in tests:
        print(f"🔍 {label}")
        print(f"   المسار: {path}")
        r = verify_file(path, save=True)
        status = "✅" if r["passed"] else "❌"
        print(f"   {status} النتيجة: {r['score']}")
        for c in r["checks"]:
            mark = "✅" if c.get("passed") else "❌"
            print(f"      {mark} {c['check']}: {c.get('findings','')[:80]}")
        print()

    print("=" * 60)
    print("  اختبار الادعاء الكاذب")
    print("=" * 60)
    r = verify_claim("لقد أنشأت tools/new_awesome_tool.py بنجاح", save=True)
    print(f"   {r}")
    print()

    print("=" * 60)
    print("  الإحصاءات النهائية")
    print("=" * 60)
    try:
        from memory.learning import LearningMemory
        m = LearningMemory()
        print("  Counts:", m.count())
        print("  Verification stats:")
        for k, v in m.verification_stats().items():
            print(f"     {k}: {v}")
        print("  Top patterns:")
        for p in m.top_patterns(limit=5):
            print(f"     {p['pattern_key']}: {p['occurrences']}× [{p['severity']}]")
    except Exception as e:
        print("  (خطأ في القراءة:", e, ")")
