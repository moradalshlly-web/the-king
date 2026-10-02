"""
brain/design_injector.py
========================
Extracts the MOROAI Design System (design.css) into a compact text
form that the Builder LLM can understand and reuse.

The Builder should NOT invent new CSS — it should use the existing tokens
and classes from design.css.
"""

import os
import re
from typing import Dict, List, Optional


try:
    from brain.core_paths import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = os.path.expanduser("~/moroai")


DESIGN_CSS = os.path.join(PROJECT_ROOT, "web_new", "design.css")


# ───────────────────────────────────────────────
# Extraction
# ───────────────────────────────────────────────

_VAR_RE = re.compile(r"(--[a-z0-9\-]+)\s*:\s*([^;]+);", re.IGNORECASE)
_CLASS_RE = re.compile(r"\.([a-z][a-z0-9\-_]+)\s*\{", re.IGNORECASE)


def _read() -> str:
    try:
        with open(DESIGN_CSS, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def extract_variables() -> Dict[str, str]:
    """Return {--variable: value} from the first :root block."""
    css = _read()
    if not css:
        return {}
    # find first :root { ... } block
    m = re.search(r":root\s*\{([^}]*)\}", css, re.DOTALL)
    if not m:
        return {}
    block = m.group(1)
    return {k: v.strip() for k, v in _VAR_RE.findall(block)}


def extract_classes() -> List[str]:
    """Return list of unique .class names defined in the CSS."""
    css = _read()
    if not css:
        return []
    names = set()
    for m in _CLASS_RE.finditer(css):
        n = m.group(1).lower()
        # skip obvious pseudo/utility noise
        if n in ("before", "after", "hover", "focus"):
            continue
        names.add(n)
    return sorted(names)


def extract_theme_summaries() -> Dict[str, Dict[str, str]]:
    """Return {theme_name: {--var: value}} for each [data-theme=...]."""
    css = _read()
    if not css:
        return {}
    themes: Dict[str, Dict[str, str]] = {}
    for m in re.finditer(r'\[data-theme="([a-z]+)"\]\s*\{([^}]*)\}', css, re.DOTALL):
        name = m.group(1)
        block = m.group(2)
        vars_ = {k: v.strip() for k, v in _VAR_RE.findall(block)}
        themes[name] = vars_
    return themes


# ───────────────────────────────────────────────
# Public: compact context for the LLM
# ───────────────────────────────────────────────

def design_context(max_classes: int = 60,
                   max_vars: int = 40) -> str:
    """
    Build a compact Arabic/English description of the design system.
    Injected into Builder's prompt when generating .html/.css files.
    """
    css = _read()
    if not css:
        return ""

    vars_ = extract_variables()
    classes = extract_classes()
    themes = extract_theme_summaries()

    lines = [
        "=== MOROAI DESIGN SYSTEM (design.css) ===",
        "",
        "CRITICAL RULES:",
        "1. ALWAYS link the design system: <link rel=\"stylesheet\" href=\"../design.css\">",
        "   (use ./design.css if the file is at web_new/ root, ../design.css if in a subfolder)",
        "2. NEVER redefine colors that already exist as CSS variables.",
        "   Use var(--color-accent), var(--text-primary), etc.",
        "3. REUSE the existing classes below instead of inventing new ones.",
        "4. Only add NEW CSS for elements that are NOT already styled.",
        "5. The default theme is applied by: <html data-theme=\"purple\">",
        "",
    ]

    if vars_:
        lines.append("AVAILABLE CSS VARIABLES:")
        for k, v in list(vars_.items())[:max_vars]:
            lines.append(f"  {k}: {v}")
        lines.append("")

    if classes:
        lines.append("REUSABLE CLASSES (from design.css):")
        # group by prefix for readability
        shown = classes[:max_classes]
        lines.append("  " + ", ".join("." + c for c in shown))
        lines.append("")

    if themes:
        names = list(themes.keys())
        lines.append(f"AVAILABLE THEMES: {', '.join(names)}")
        lines.append("  switch by changing <html data-theme=\"...\">")
        lines.append("")

    lines.append("=== END DESIGN SYSTEM ===")
    return "\n".join(lines)


def design_css_path_for(target_path: str) -> str:
    """
    Return the correct relative path to design.css based on target_path.
    Assumes design.css lives at web_new/design.css.
    """
    p = (target_path or "").replace("\\", "/").lstrip("./")
    if not p.startswith("web_new/"):
        # file isn't under web_new — still suggest absolute-ish
        return "/web_new/design.css"
    rest = p[len("web_new/"):]
    depth = rest.count("/")
    if depth == 0:
        return "./design.css"
    # depth >= 1 -> use ../
    return "../" * depth + "design.css"


# ───────────────────────────────────────────────
# Self-test
# ───────────────────────────────────────────────

if __name__ == "__main__":
    print("Design Injector — self-test")
    print("=" * 55)

    vars_ = extract_variables()
    print(f"CSS variables found: {len(vars_)}")
    for k, v in list(vars_.items())[:6]:
        print(f"  {k}: {v}")

    classes = extract_classes()
    print(f"\nCSS classes found: {len(classes)}")
    print("  " + ", ".join(classes[:20]))

    themes = extract_theme_summaries()
    print(f"\nThemes found: {list(themes.keys())}")

    print(f"\nPath for web_new/najma/index.html: {design_css_path_for('web_new/najma/index.html')}")
    print(f"Path for web_new/index.html:        {design_css_path_for('web_new/index.html')}")
    print(f"Path for web_new/css/x.css:         {design_css_path_for('web_new/css/x.css')}")

    print()
    print("=== Sample context ===")
    print(design_context(max_classes=15)[:900])
