"""
brain/template_loader.py
========================
Template loader for MOROAI.

Templates live in web_new/templates/*.html
They use placeholders like {{TITLE}}, {{BRAND}} that get replaced.

Used by:
    - Planner  : sees available templates as context
    - Builder  : can fill a template directly
"""

import os
import re
from typing import Dict, List, Optional, Any

try:
    from brain.core_paths import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = os.path.expanduser("~/moroai")


TPL_DIR = os.path.join(PROJECT_ROOT, "web_new", "templates")

# What each template is for (used to help the LLM pick)
TEMPLATE_HINTS = {
    "landing":   "صفحة هبوط تسويقية (Hero + Features + Pricing + CTA) — للشركات والمنتجات",
    "dashboard": "لوحة تحكم إدارية (Sidebar + Stats + Activity) — للتطبيقات والأنظمة",
    "login":     "صفحة تسجيل دخول (نموذج مصادقة) — للبوابات المحمية",
    "portfolio": "معرض أعمال شخصي (Hero + مشاريع + عني + تواصل) — للمستقلين والمصممين",
    "blog":      "مدونة/مجلة (قائمة مقالات + تاريخ) — للمحتوى والكتابة",
    "docs":      "صفحة توثيق تقنية (Sidebar + Markdown style) — للمشاريع البرمجية",
}


def list_templates() -> List[str]:
    """Return available template names (without .html)."""
    if not os.path.isdir(TPL_DIR):
        return []
    return sorted(
        f[:-5] for f in os.listdir(TPL_DIR)
        if f.endswith(".html") and not f.startswith("_")
    )


def load_template(name: str) -> Optional[str]:
    """Return the raw content of a template."""
    if not name:
        return None
    path = os.path.join(TPL_DIR, f"{name}.html")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def fill_template(name: str, values: Dict[str, str]) -> Optional[str]:
    """
    Fill a template: replace {{KEY}} with values[KEY].
    Unknown keys remain untouched.
    """
    content = load_template(name)
    if not content:
        return None

    def repl(m: re.Match) -> str:
        k = m.group(1).strip()
        return str(values.get(k, m.group(0)))

    return re.sub(r"\{\{\s*([A-Z_][A-Z0-9_]*)\s*\}\}", repl, content)


def template_context(max_lines: int = 25) -> str:
    """
    Build a short text describing available templates.
    Used to enrich the Planner's prompt.
    """
    names = list_templates()
    if not names:
        return ""

    lines = ["القوالب المتوفرة في web_new/templates/:"]
    for n in names:
        hint = TEMPLATE_HINTS.get(n, "قالب HTML")
        lines.append(f"  • {n}.html — {hint}")
    lines.append("")
    lines.append("استخدم القوالب عند الطلب: انسخ القالب ثم عدّله.")
    lines.append("يمكن استبدال الأقواس {{KEY}} بقيم حقيقية.")
    return "\n".join(lines)


def show_template(name: str, max_lines: int = 40) -> str:
    """Return a truncated view of the template (for LLM prompt)."""
    content = load_template(name)
    if not content:
        return ""
    lines = content.split("\n")[:max_lines]
    return "\n".join(lines)


# ═══════════════════════════════════════════════
# Self-test
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print("Template Loader — self-test")
    print("=" * 55)

    names = list_templates()
    print(f"Available templates: {len(names)}")
    for n in names:
        content = load_template(n)
        size = len(content or "")
        print(f"  • {n}.html ({size} bytes)")

    print()
    print("Context for Planner:")
    print(template_context())

    print()
    print("Fill test (landing):")
    filled = fill_template("landing", {
        "TITLE": "موقعي الأول",
        "BRAND": "شركتي",
        "BADGE": "جديد",
        "HERO_TITLE": "ابدأ رحلتك",
        "HERO_SUBTITLE": "أفضل منصة في العالم",
    })
    if filled:
        # Show only the replaced lines
        for line in filled.split("\n")[:30]:
            if "{{" not in line and ("موقعي" in line or "شركتي" in line or "جديد" in line):
                print(f"  ✅ {line.strip()}")
