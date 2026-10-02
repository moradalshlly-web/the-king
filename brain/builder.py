"""
brain/builder.py
================

MOROAI Builder: generate complete files from natural language.

Workflow:
    1. Owner describes what they want (Arabic or English)
    2. MOROAI generates the FULL content of the file
    3. Content is sanitized (markdown fences stripped)
    4. Preview shown -> owner confirms
    5. Checkpoint created -> file written

Design principles:
    - NEVER write without a checkpoint (D2)
    - Strip markdown fences automatically
    - Validate: empty or too-large content is rejected
    - Save inside the project sandbox only

Inspiration (no code copied):
    - OpenHands CodeAct: LLM produces raw content
    - Aider: confirm before write
    - Cline: strip markdown fences
    - SWE-Agent: checkpoint before change
"""

import os
import re
from typing import Optional, Dict, Any

from tools.file_ops import FileOps


MAX_FILE_BYTES = 200_000  # 200KB safety cap
MIN_FILE_BYTES = 10       # reject near-empty


# ============================================================
# Prompt
# ============================================================

BUILDER_SYSTEM = """You are MOROAI's file generator.

You produce the COMPLETE, ready-to-use content of a single file.
You do NOT explain. You do NOT add commentary.

Strict rules:
- Output ONLY the raw file content.
- Do NOT wrap the output in markdown code fences (no ``` at start or end).
- Do NOT add introductory text like "Here is the file:".
- Do NOT add trailing notes like "This file does X".
- The file must be complete and functional.
- Use the appropriate language and syntax for the requested path.
- If the content is Arabic-first, use proper RTL-friendly markup.
- Keep it self-contained when possible (minimal external dependencies).
"""


# ============================================================
# Sanitization
# ============================================================

FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9_+-]*\s*\n(.*?)\n```\s*$", re.DOTALL)


def strip_markdown_fences(text: str) -> str:
    """Remove leading/trailing markdown code fences if present."""
    if not text:
        return text
    m = FENCE_RE.match(text.strip())
    if m:
        return m.group(1).rstrip() + "\n"
    return text


# ============================================================
# Builder
# ============================================================

class Builder:
    """Generates complete files from descriptions."""

    def __init__(self, brain, root: Optional[str] = None):
        self.brain = brain
        self.file_ops = FileOps(root)

    # -------- Generate --------

    def generate(
        self,
        target_path: str,
        description: str,
        language: Optional[str] = None,
        temperature: float = 0.4,
    ) -> Dict[str, Any]:
        """
        Generate content for a file. Does NOT write it.

        Returns:
            {success, content, bytes, provider, model, latency_ms, error}
        """
        if not target_path or not description:
            return {"success": False, "content": "", "error": "Missing path or description"}

        # Infer language from extension if not provided
        if not language:
            ext = os.path.splitext(target_path)[1].lower()
            language = {
                ".html": "HTML5",
                ".css": "CSS3",
                ".js": "JavaScript (ES2022)",
                ".py": "Python 3",
                ".json": "JSON",
                ".md": "Markdown",
                ".txt": "Plain text",
                ".sh": "Bash",
                ".yml": "YAML",
                ".yaml": "YAML",
            }.get(ext, "plain text")

        # Inject design system context for web files
        design_block = ""
        ext_low = os.path.splitext(target_path)[1].lower()
        try:
            from brain.design_injector import design_context, design_css_path_for
            if ext_low in (".html", ".css"):
                design_block = design_context()
                css_rel = design_css_path_for(target_path)
                design_block += f"\n\nRELATIVE PATH TO design.css from this file: {css_rel}\n"
        except Exception:
            pass

        # Extra rules for HTML files
        if ext_low == ".html":
            design_block += (
                "\n=== HTML-SPECIFIC RULES (STRICT) ===\n"
                "0. The <html> tag MUST be:  <html lang=\"ar\" dir=\"rtl\" data-theme=\"purple\">\n"
                "   These three attributes are MANDATORY. Do not omit them.\n"
                "1. If you reference a script, it MUST be <script src=\"script.js\"></script>\n"
                "   (assume sibling file in the SAME folder — no ../).\n"
                "2. If you reference a style.css, it MUST be <link href=\"style.css\">\n"
                "   (assume sibling). If you only use design.css, DO NOT create a style.css.\n"
                "3. ALWAYS link design.css with the correct relative path shown above.\n"
                "4. NEVER reference files that were not created and are not part of the design system.\n"
                "5. NEVER use placeholder image URLs like via.placeholder.com.\n"
                "   Use inline SVG, CSS gradients, or leave a comment <!-- image here -->.\n"
                "6. Do NOT invent class names. Only use classes listed in the DESIGN SYSTEM block above.\n"
                "7. Start with <!DOCTYPE html> and end with </html> — complete valid HTML only.\n"
                "=== END HTML-SPECIFIC RULES ===\n"
            )

        user_prompt = f"""Target file path: {target_path}
Language/format: {language}
What the file should do: {description}

{design_block}

Generate the complete content of this file now.
"""

        resp = self.brain.ask(
            prompt=user_prompt,
            content_class="standard",
            system=BUILDER_SYSTEM,
            temperature=temperature,
        )

        if not resp.success:
            return {"success": False, "content": "", "error": resp.error}

        content = strip_markdown_fences(resp.text or "")
        size = len(content.encode("utf-8"))

        if size < MIN_FILE_BYTES:
            return {
                "success": False,
                "content": "",
                "error": f"Generated content too small ({size} bytes)",
            }
        if size > MAX_FILE_BYTES:
            return {
                "success": False,
                "content": "",
                "error": f"Generated content too large ({size} bytes > {MAX_FILE_BYTES})",
            }

        return {
            "success": True,
            "content": content,
            "bytes": size,
            "provider": resp.provider,
            "model": resp.model,
            "latency_ms": resp.latency_ms,
            "error": None,
        }

    # -------- Write --------

    def write(self, target_path: str, content: str) -> Dict[str, Any]:
        """Write content to the target file (sandbox-checked)."""
        return self.file_ops.write_file(target_path, content)


# ============================================================
# Self-test (no API call)
# ============================================================

if __name__ == "__main__":
    # Test fence stripping
    cases = [
        ("```html\n<html></html>\n```", "<html></html>\n"),
        ("```python\nprint('hi')\n```", "print('hi')\n"),
        ("<html></html>", "<html></html>"),
        ("```\nbody\n```", "body\n"),
    ]
    for inp, expected in cases:
        got = strip_markdown_fences(inp)
        assert got == expected, f"Input: {inp!r} -> got {got!r}, expected {expected!r}"
        print(f"OK: {inp!r} -> {got!r}")

    print("\n✅ Builder sanitization tests passed.")
