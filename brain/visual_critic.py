"""
brain/visual_critic.py
======================
Visual Critic for MOROAI — scores generated HTML/CSS.

Two layers:
    1. Static analysis (no LLM)   — deterministic checks
    2. LLM critique              — overall visual score + suggestions

Output shape:
{
    "file": "web_new/najma/index.html",
    "static_score": 0-10,
    "llm_score":    0-10,
    "overall":      0-10,  # weighted average
    "verdict":      "excellent" | "good" | "fair" | "poor",
    "issues":       [...],
    "suggestions":  [...],
    "dimensions": {
        "structure":   0-10,
        "design_system": 0-10,
        "accessibility": 0-10,
        "content":     0-10,
        "responsive":  0-10,
    }
}
"""

import os
import re
from typing import Dict, Any, List, Optional


try:
    from brain.core_paths import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = os.path.expanduser("~/moroai")


# ═══════════════════════════════════════════════
# Static analysis (no LLM)
# ═══════════════════════════════════════════════

# Known design-system classes
KNOWN_CLASSES = {
    "btn", "btn-primary", "btn-secondary", "btn-ghost",
    "card", "card-glass",
    "input",
    "badge", "badge-accent", "badge-success", "badge-warning", "badge-danger",
    "container", "container-sm", "container-lg",
    "row", "row-between", "row-center", "row-wrap",
    "stack", "stack-sm", "stack-lg",
    "grid", "grid-2", "grid-3", "grid-4",
    "hero", "hero-title", "hero-subtitle",
    "navbar", "navbar-brand",
    "footer",
    "text-center", "text-start", "text-end",
    "text-muted", "text-accent", "text-luxury",
    "mt-4", "mt-8", "mb-4", "mb-8",
    "hidden", "flex", "block",
    "animate-fade-in", "animate-pulse-glow",
}

PLACEHOLDER_PATTERNS = [
    r"via\.placeholder\.com",
    r"placeholder\.com",
    r"lorem\s+ipsum",
    r"TODO:",
    r"FIXME:",
    r"<!--\s*your\s+content\s+here",
    r"example\.com",
]


def _read_file(path: str) -> Optional[str]:
    full = path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)
    if not os.path.isfile(full):
        return None
    try:
        with open(full, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def _extract_classes(html: str) -> List[str]:
    """Return all class names used in the HTML."""
    names = []
    for m in re.finditer(r'class\s*=\s*"([^"]*)"', html):
        for c in m.group(1).split():
            if c:
                names.append(c)
    return names


def _has_design_link(html: str) -> bool:
    return bool(re.search(r'<link[^>]+design\.css', html, re.IGNORECASE))


def _has_theme_attr(html: str) -> bool:
    return bool(re.search(r'data-theme\s*=\s*"[a-z]+"', html, re.IGNORECASE))


def _count_sections(html: str) -> int:
    return len(re.findall(r"<section\b", html, re.IGNORECASE))


def _count_headings(html: str) -> Dict[str, int]:
    out = {}
    for lvl in "123456":
        out[f"h{lvl}"] = len(re.findall(rf"<h{lvl}\b", html, re.IGNORECASE))
    return out


def _has_viewport(html: str) -> bool:
    return bool(re.search(r'name\s*=\s*"viewport"', html, re.IGNORECASE))


def _has_lang(html: str) -> bool:
    return bool(re.search(r'<html[^>]+lang\s*=\s*"[a-z\-]+"', html, re.IGNORECASE))


def _has_rtl(html: str) -> bool:
    return bool(re.search(r'dir\s*=\s*"rtl"', html, re.IGNORECASE))


def _has_placeholder(html: str) -> Optional[str]:
    for pat in PLACEHOLDER_PATTERNS:
        if re.search(pat, html, re.IGNORECASE):
            return pat
    return None


def _count_inline_style(html: str) -> int:
    return len(re.findall(r"<style\b", html, re.IGNORECASE))


def _score_structure(html: str, issues: List[str]) -> float:
    score = 10.0
    sections = _count_sections(html)
    headings = _count_headings(html)

    if sections == 0:
        score -= 3.0
        issues.append("لا توجد <section> — البنية ضعيفة")
    elif sections < 2:
        score -= 1.0

    total_h = sum(headings.values())
    if total_h == 0:
        score -= 3.0
        issues.append("لا توجد عناوين <h1..h6>")
    elif headings["h1"] == 0:
        score -= 1.5
        issues.append("لا يوجد <h1> (عنوان رئيسي)")
    elif headings["h1"] > 1:
        score -= 0.5
        issues.append("يوجد أكثر من <h1> (يُفضّل واحد)")

    return max(0.0, min(10.0, score))


def _score_design_system(html: str, issues: List[str]) -> float:
    score = 10.0

    if not _has_design_link(html):
        score -= 4.0
        issues.append("design.css غير مربوط")
    if not _has_theme_attr(html):
        score -= 1.0
        issues.append("data-theme غير محدد")

    used = set(_extract_classes(html))
    known_used = used & KNOWN_CLASSES
    unknown = used - KNOWN_CLASSES

    if len(known_used) < 3:
        score -= 3.0
        issues.append(f"قليل من classes Design System ({len(known_used)} فقط)")
    if len(unknown) > len(known_used):
        score -= 1.5
        issues.append(f"classes غير معروفة كثيرة ({len(unknown)})")

    inline = _count_inline_style(html)
    if inline > 0:
        score -= 1.0 * min(inline, 2)
        issues.append(f"{inline} كتلة <style> inline (يُفضّل بلا CSS إضافي)")

    return max(0.0, min(10.0, score))


def _score_accessibility(html: str, issues: List[str]) -> float:
    score = 10.0

    if not _has_lang(html):
        score -= 2.0
        issues.append("لا يوجد lang attribute")
    if not _has_viewport(html):
        score -= 2.0
        issues.append("لا يوجد meta viewport")
    if not _has_rtl(html):
        score -= 1.0
        issues.append("لا يوجد dir='rtl' (للعربية)")

    # Buttons should have text
    btns = re.findall(r"<button[^>]*>\s*</button>", html, re.IGNORECASE)
    if btns:
        score -= 1.5
        issues.append(f"{len(btns)} <button> فارغ (بلا نص)")

    # Images should have alt
    imgs = re.findall(r"<img\b[^>]*>", html, re.IGNORECASE)
    no_alt = [i for i in imgs if "alt=" not in i.lower()]
    if no_alt:
        score -= 0.5 * len(no_alt)
        issues.append(f"{len(no_alt)} <img> بلا alt")

    return max(0.0, min(10.0, score))


def _score_content(html: str, issues: List[str]) -> float:
    score = 10.0

    ph = _has_placeholder(html)
    if ph:
        score -= 4.0
        issues.append(f"placeholders موجودة ({ph})")

    # Very short pages
    text = re.sub(r"<[^>]+>", " ", html)
    words = len(text.split())
    if words < 30:
        score -= 3.0
        issues.append(f"المحتوى قصير جداً ({words} كلمة)")
    elif words < 80:
        score -= 1.0

    # Empty hrefs
    if re.search(r'href\s*=\s*"#"\s*>\s*</a>', html):
        score -= 1.0
        issues.append("روابط فارغة (#)")

    return max(0.0, min(10.0, score))


def _score_responsive(html: str, issues: List[str]) -> float:
    score = 10.0

    if not _has_viewport(html):
        score -= 4.0
    if "@media" not in html and "media" not in html:
        # Not a big deal if using design.css (which has media queries)
        if not _has_design_link(html):
            score -= 2.0
            issues.append("لا media queries ولا design.css")

    return max(0.0, min(10.0, score))


def static_critique(path: str) -> Dict[str, Any]:
    """Run all static checks. No LLM."""
    html = _read_file(path)
    if not html:
        return {"ok": False, "error": "file not found or unreadable"}

    issues: List[str] = []

    dimensions = {
        "structure":     round(_score_structure(html, issues), 2),
        "design_system": round(_score_design_system(html, issues), 2),
        "accessibility": round(_score_accessibility(html, issues), 2),
        "content":       round(_score_content(html, issues), 2),
        "responsive":    round(_score_responsive(html, issues), 2),
    }

    avg = sum(dimensions.values()) / len(dimensions)

    return {
        "ok": True,
        "path": path,
        "dimensions": dimensions,
        "static_score": round(avg, 2),
        "issues": issues,
    }


# ═══════════════════════════════════════════════
# LLM critique
# ═══════════════════════════════════════════════

CRITIC_SYSTEM = """You are MOROAI's Visual Critic.

You read HTML code and judge the VISUAL quality of the page as if you saw it.

Score from 0 to 10 across these axes, but only give ONE overall score (0-10).

Criteria:
- Layout & spacing:      balanced, breathable, no clutter
- Color harmony:         uses design system colors consistently
- Typography:            clear hierarchy, readable sizes
- Content:               real meaningful text, not placeholders
- Interaction signals:   buttons/links look clickable
- Overall "wow":         does it feel premium or generic?

Output valid JSON ONLY:
{
  "score": 0-10,
  "verdict": "excellent" | "good" | "fair" | "poor",
  "suggestions": ["<short suggestion 1>", "<short suggestion 2>"],
  "strengths": ["<what works>"]
}

Rules:
- Be honest but constructive.
- Score 7+ means it looks genuinely good.
- Score 5-6 means acceptable but bland.
- Score <5 means ugly or broken.
- Max 4 suggestions, max 3 strengths.
- Output JSON only. No markdown. No text outside JSON.
"""


def _strip_fences(text: str) -> str:
    if not text:
        return text
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if len(lines) > 1:
            t = "\n".join(lines[1:])
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3].rstrip()
    return t


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    t = _strip_fences(text)
    try:
        import json
        return json.loads(t)
    except Exception:
        pass
    s, e = t.find("{"), t.rfind("}")
    if s != -1 and e > s:
        try:
            import json
            return json.loads(t[s:e+1])
        except Exception:
            pass
    return None


def llm_critique(brain, path: str, max_chars: int = 6000) -> Dict[str, Any]:
    """Ask the LLM for a visual quality score."""
    html = _read_file(path)
    if not html:
        return {"ok": False, "error": "file unreadable"}

    snippet = html[:max_chars]

    resp = brain.ask(
        prompt=f"HTML to critique:\n\n{snippet}",
        content_class="standard",
        system=CRITIC_SYSTEM,
        temperature=0.2,
    )

    if not resp.success:
        return {"ok": False, "error": resp.error}

    parsed = _extract_json(resp.text or "")
    if not parsed:
        return {"ok": False, "error": "could not parse LLM output",
                "raw": (resp.text or "")[:400]}

    try:
        score = float(parsed.get("score", 5))
    except (TypeError, ValueError):
        score = 5.0

    return {
        "ok": True,
        "llm_score": round(score, 2),
        "verdict": (parsed.get("verdict") or "fair").lower(),
        "suggestions": parsed.get("suggestions") or [],
        "strengths": parsed.get("strengths") or [],
        "provider": resp.provider,
        "model": resp.model,
        "latency_ms": resp.latency_ms,
    }


# ═══════════════════════════════════════════════
# Public: full critique
# ═══════════════════════════════════════════════

def critique(brain, path: str, use_llm: bool = True) -> Dict[str, Any]:
    """
    Full visual critique: static + optional LLM.
    Returns unified report.
    """
    static = static_critique(path)
    if not static.get("ok"):
        return {"ok": False, "error": static.get("error", "static failed")}

    result = {
        "ok": True,
        "path": path,
        "dimensions": static["dimensions"],
        "static_score": static["static_score"],
        "issues": static["issues"],
        "suggestions": [],
        "strengths": [],
        "llm_score": None,
        "llm_verdict": None,
    }

    if use_llm:
        llm = llm_critique(brain, path)
        if llm.get("ok"):
            result["llm_score"] = llm["llm_score"]
            result["llm_verdict"] = llm["verdict"]
            result["suggestions"] = llm["suggestions"]
            result["strengths"] = llm["strengths"]
            result["llm_provider"] = llm.get("provider")
            # Weighted overall: static 40% + llm 60%
            overall = 0.4 * static["static_score"] + 0.6 * llm["llm_score"]
        else:
            result["llm_error"] = llm.get("error")
            overall = static["static_score"]
    else:
        overall = static["static_score"]

    result["overall"] = round(overall, 2)
    # Verdict from overall
    if overall >= 8:   result["verdict"] = "excellent"
    elif overall >= 6.5: result["verdict"] = "good"
    elif overall >= 5: result["verdict"] = "fair"
    else:              result["verdict"] = "poor"

    return result


def render_arabic(report: Dict[str, Any]) -> str:
    """Format a critique report in Arabic for the user."""
    if not report.get("ok"):
        return f"❌ تعذّر النقد: {report.get('error')}"

    v = report.get("verdict", "?")
    v_ar = {
        "excellent": "ممتاز 🌟",
        "good": "جيد ✅",
        "fair": "مقبول 🟡",
        "poor": "ضعيف ❌",
    }.get(v, v)

    lines = [
        f"🎨 الناقد البصري: {report['overall']}/10 — {v_ar}",
        "",
    ]

    dims = report.get("dimensions", {})
    labels = {
        "structure": "البنية",
        "design_system": "نظام التصميم",
        "accessibility": "الوصولية",
        "content": "المحتوى",
        "responsive": "الاستجابة",
    }
    for key, label in labels.items():
        val = dims.get(key, 0)
        bar = "█" * int(val) + "░" * (10 - int(val))
        lines.append(f"  {label:14} [{bar}] {val}/10")

    if report.get("strengths"):
        lines.append("")
        lines.append("✨ نقاط القوة:")
        for s in report["strengths"][:3]:
            lines.append(f"   • {s}")

    if report.get("issues"):
        lines.append("")
        lines.append("⚠️  مشاكل:")
        for s in report["issues"][:5]:
            lines.append(f"   • {s}")

    if report.get("suggestions"):
        lines.append("")
        lines.append("💡 اقتراحات:")
        for s in report["suggestions"][:4]:
            lines.append(f"   • {s}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════
# Self-test (no LLM)
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print("Visual Critic — static self-test")
    print("=" * 55)

    # Test on the newest najma index
    import glob
    candidates = sorted(glob.glob(os.path.join(PROJECT_ROOT, "web_new/najma/*.html")))
    if not candidates:
        candidates = sorted(glob.glob(os.path.join(PROJECT_ROOT, "web_new/templates/*.html")))

    for f in candidates[:2]:
        rel = os.path.relpath(f, PROJECT_ROOT)
        print(f"\n📄 {rel}")
        r = static_critique(rel)
        if r.get("ok"):
            print(f"   static_score: {r['static_score']}/10")
            for k, v in r["dimensions"].items():
                print(f"     {k}: {v}")
            if r["issues"]:
                print(f"   issues: {len(r['issues'])}")
                for i in r["issues"][:3]:
                    print(f"     • {i}")
