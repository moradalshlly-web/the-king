"""
brain/arabic_layer.py
=====================
Translate execution reports into natural Arabic.

Three styles:
    detailed  — for developers (mentions file paths, actions)
    brief     — bullet points, minimal
    friendly  — no jargon, analogies, like talking to a friend

Uses templates (free) for common cases; falls back to LLM only if needed.
"""

from typing import Dict, Any, List, Optional


# ═══════════════════════════════════════════════
# Action templates (Arabic)
# ═══════════════════════════════════════════════

ACTION_TEMPLATES = {
    "create": {
        "detailed": "أنشأتُ ملف {path}: {desc}",
        "brief":    "✅ أنشأتُ {basename}",
        "friendly": "صنعتُ شيئاً جديداً اسمه {basename}",
    },
    "modify": {
        "detailed": "عدّلتُ ملف {path}: {desc}",
        "brief":    "✅ عدّلتُ {basename}",
        "friendly": "لمستُ ملفاً موجوداً ({basename}) وحسّنتُه",
    },
    "delete": {
        "detailed": "حذفتُ ملف {path}",
        "brief":    "🗑️ حذفتُ {basename}",
        "friendly": "أزلتُ ملفاً قديماً ({basename})",
    },
    "ask": {
        "detailed": "أحتاج توضيحاً: {desc}",
        "brief":    "❓ {desc}",
        "friendly": "عندي سؤال قبل أن أكمل: {desc}",
    },
}

# ═══════════════════════════════════════════════
# Summary templates by outcome
# ═══════════════════════════════════════════════

SUMMARY_TEMPLATES = {
    "all_ok": {
        "detailed": "أنجزتُ {ok}/{total} خطوة بنجاح في {seconds} ثانية.",
        "brief":    "✅ {ok}/{total} في {seconds}s",
        "friendly": "خلصتُ! أنجزتُ كل شيء ({ok} خطوات) في {seconds} ثانية فقط.",
    },
    "partial": {
        "detailed": "أنجزتُ {ok} من {total} خطوة. {failed} خطوة تعثّرت.",
        "brief":    "⚠️ {ok}/{total} نجحت",
        "friendly": "خلصتُ جزءاً من العمل ({ok} من {total}). عندي {failed} خطوة تحتاج نظرة.",
    },
    "failed": {
        "detailed": "فشلت كل الخطوات ({failed} من {total}).",
        "brief":    "❌ فشل كامل",
        "friendly": "آسف يا صديقي، لم أنجح هذه المرة. جاهز أحاول من زاوية أخرى.",
    },
    "validation": {
        "detailed": "الخطة مرفوضة قبل التنفيذ: {errors}",
        "brief":    "🚫 الخطة مرفوضة",
        "friendly": "قبل أن أبدأ، انتبهتُ أن الخطة فيها مشاكل. لم أرغب في إهدار وقتك.",
    },
    "empty": {
        "detailed": "لا توجد خطوات لتنفيذ.",
        "brief":    "(لا خطوات)",
        "friendly": "لم يكن هناك شيء لتنفيذه.",
    },
}

# ═══════════════════════════════════════════════
# File-type friendly names
# ═══════════════════════════════════════════════

FRIENDLY_FILE_NAMES = {
    ".html":  "صفحة الموقع",
    ".css":   "ملف التنسيق والجمال",
    ".js":    "ملف الحركة والتفاعل",
    ".py":    "ملف برمجي (Python)",
    ".json":  "ملف بيانات",
    ".md":    "ملف نصي",
    ".svg":   "شعار أو رسمة",
    ".png":   "صورة",
    ".jpg":   "صورة",
    ".txt":   "ملف نصي",
}


# ═══════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════

def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1] if "/" in path else path


def _friendly_file(path: str) -> str:
    ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return FRIENDLY_FILE_NAMES.get(ext, _basename(path))


def _format_step(step: Dict[str, Any], style: str) -> str:
    """Format one step in the given style."""
    action = step.get("action", "create")
    path = step.get("path", "")
    desc = step.get("description", "")

    tmpl = ACTION_TEMPLATES.get(action, ACTION_TEMPLATES["create"])[style]

    # Special handling for friendly style: replace path with friendly name
    if style == "friendly":
        return tmpl.format(
            path=path,
            basename=_friendly_file(path),
            desc=desc,
        )

    return tmpl.format(
        path=path,
        basename=_basename(path),
        desc=desc or "(بلا وصف)",
    )


def _build_summary(report: Dict[str, Any], style: str) -> str:
    stage = report.get("stage", "done")

    if stage == "validation":
        return SUMMARY_TEMPLATES["validation"][style].format(
            errors=", ".join(report.get("errors", [])[:2]),
        )

    total = report.get("steps_total", 0)
    ok = report.get("steps_ok", 0)
    failed = report.get("steps_failed", 0)
    seconds = round(report.get("elapsed_seconds", 0), 1)

    if total == 0:
        return SUMMARY_TEMPLATES["empty"][style]

    if failed == 0:
        return SUMMARY_TEMPLATES["all_ok"][style].format(
            ok=ok, total=total, seconds=seconds,
        )
    if ok == 0:
        return SUMMARY_TEMPLATES["failed"][style].format(
            failed=failed, total=total,
        )
    return SUMMARY_TEMPLATES["partial"][style].format(
        ok=ok, total=total, failed=failed,
    )


# ═══════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════

def explain(report: Dict[str, Any],
            style: str = "friendly") -> Dict[str, Any]:
    """
    Turn an execution report into Arabic.

    report: output of executor.execute_plan()
    style : "detailed" | "brief" | "friendly"

    Returns:
        {
            "style": style,
            "summary": "<one paragraph>",
            "steps": ["<line>", ...],
            "is_success": bool,
        }
    """
    if style not in ("detailed", "brief", "friendly"):
        style = "friendly"

    # Summary
    summary_line = _build_summary(report, style)

    # Steps
    results = report.get("results") or []
    steps_lines: List[str] = []

    for r in results:
        if not isinstance(r, dict):
            continue
        action = r.get("action", "create")
        success = r.get("success", False)
        path = r.get("path", "")

        # Reconstruct step dict for the template
        step = {
            "action": action,
            "path": path,
            "description": r.get("description") or "",
        }
        base = _format_step(step, style)

        if not success:
            base = "❌ " + base.replace("✅ ", "")
        steps_lines.append(base)

    return {
        "style": style,
        "summary": summary_line,
        "steps": steps_lines,
        "is_success": bool(report.get("success")),
    }


def render(report: Dict[str, Any],
           style: str = "friendly",
           include_steps: bool = True) -> str:
    """Convenience: return a single Arabic string ready to print."""
    e = explain(report, style)
    lines = [e["summary"]]
    if include_steps and e["steps"]:
        lines.append("")
        for s in e["steps"]:
            lines.append("  " + s)
    return "\n".join(lines)


# ═══════════════════════════════════════════════
# Self-test (no LLM)
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    sample = {
        "success": True,
        "stage": "done",
        "steps_total": 3,
        "steps_ok": 3,
        "steps_failed": 0,
        "elapsed_seconds": 7.5,
        "results": [
            {"action": "create", "path": "web_new/index.html",
             "description": "الهيكل الأساسي", "success": True},
            {"action": "create", "path": "web_new/style.css",
             "description": "التنسيق", "success": True},
            {"action": "create", "path": "web_new/app.js",
             "description": "التفاعل", "success": True},
        ],
    }

    print("═══ مفصّل ═══")
    print(render(sample, "detailed"))
    print()
    print("═══ مختصر ═══")
    print(render(sample, "brief"))
    print()
    print("═══ صديق ═══")
    print(render(sample, "friendly"))
