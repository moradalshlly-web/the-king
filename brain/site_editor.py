"""
brain/site_editor.py
====================
Site Editor — modify MOROAI's own website from natural language.

Flow:
    1. Read target file (default: web_new/index.html)
    2. Snapshot before
    3. Ask LLM to apply ONE user instruction
    4. Save to file
    5. Verify HTML validity
    6. Critic check (optional) — revert if quality drops
    7. Return {success, before_size, after_size, summary}
"""

import os
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional


try:
    from brain.core_paths import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = os.path.expanduser("~/moroai")


DEFAULT_TARGET = "web_new/index.html"
WEB_NEW_DIR = os.path.join(PROJECT_ROOT, "web_new")


SITE_EDITOR_SYSTEM = """You are MOROAI's Site Editor — a surgical HTML/CSS editor.

You receive:
    1. A user instruction (Arabic or English) about a WEBSITE file.
    2. The current content of that file.
    3. A list of available files in web_new/ (for reference).

Your job:
    - Apply ONLY the requested change.
    - Preserve everything else exactly as-is.
    - Do NOT rewrite the file from scratch.
    - Do NOT change unrelated classes, IDs, or text.
    - Keep design.css linked with the correct path.
    - Keep <html lang="ar" dir="rtl" data-theme="..."> on the first line.

CRITICAL RULES:
    1. Output ONLY this format, nothing else:

===SUMMARY===
<short description of what changed, in Arabic>
===CONTENT===
<the complete new file content>

    2. No markdown fences. No explanation outside the format.
    3. The file must be complete and valid.
    4. If the instruction is impossible, output ===IMPOSSIBLE=== on its own line.
"""


# ───────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_file(path: str) -> Optional[str]:
    full = path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)
    if not os.path.isfile(full):
        return None
    try:
        with open(full, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def _write_file(path: str, content: str) -> bool:
    full = path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)
    try:
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception:
        return False


def _list_web_files() -> str:
    if not os.path.isdir(WEB_NEW_DIR):
        return "(web_new/ غير موجود)"
    lines = []
    for root, dirs, files in os.walk(WEB_NEW_DIR):
        dirs[:] = [d for d in dirs if d not in (".cache", "_archive") and not d.startswith(".")]
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), PROJECT_ROOT)
            lines.append(f"  {rel}")
    return "\n".join(sorted(lines)[:40])


# ───────────────────────────────────────────────
# Parse LLM output
# ───────────────────────────────────────────────

def _parse_editor_output(text: str) -> Dict[str, Any]:
    """
    Parse:
    ===SUMMARY===
    ...
    ===CONTENT===
    ...
    """
    if not text:
        return {"ok": False, "error": "empty response"}

    if "===IMPOSSIBLE===" in text:
        return {"ok": False, "error": "instruction impossible"}

    # Extract summary
    summary = ""
    m = re.search(r"===SUMMARY===\s*(.+?)(?:===CONTENT===|$)", text, re.DOTALL)
    if m:
        summary = m.group(1).strip()[:300]

    # Extract content
    c = re.search(r"===CONTENT===\s*(.+)$", text, re.DOTALL)
    if not c:
        # Fallback: take whole text as content if it looks like HTML
        if "<!DOCTYPE" in text or "<html" in text:
            return {"ok": True, "summary": summary or "تعديل", "content": text.strip()}
        return {"ok": False, "error": "no content section found"}

    content = c.group(1).strip()

    # Strip markdown fences if present
    if content.startswith("```"):
        lines = content.split("\n")
        if len(lines) > 1:
            content = "\n".join(lines[1:])
        if content.rstrip().endswith("```"):
            content = content.rstrip()[:-3].rstrip()

    return {"ok": True, "summary": summary or "تعديل", "content": content}


# ───────────────────────────────────────────────
# Validate HTML/CSS
# ───────────────────────────────────────────────

def _validate_content(path: str, content: str) -> Dict[str, Any]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".html":
        if "<!DOCTYPE" not in content and "<html" not in content:
            return {"ok": False, "error": "no DOCTYPE or <html> tag"}
        if content.count("<html") != content.count("</html>"):
            return {"ok": False, "error": "unbalanced <html> tags"}
        # Check design.css link preserved
        if "design.css" not in content:
            return {"ok": False, "error": "design.css link missing"}
    elif ext == ".css":
        if content.count("{") != content.count("}"):
            return {"ok": False, "error": "unbalanced braces in CSS"}
    return {"ok": True}


# ───────────────────────────────────────────────
# Main edit
# ───────────────────────────────────────────────

def edit_site(brain, instruction: str,
              target: Optional[str] = None,
              check_critic: bool = False,
              critic_threshold: float = 1.5,
              verbose: bool = True) -> Dict[str, Any]:
    """
    Apply a natural-language instruction to a website file.

    Parameters:
        brain            : MOROAI instance
        instruction      : user's request (Arabic/English)
        target           : relative path (default: web_new/index.html)
        check_critic     : run Visual Critic before/after (slower)
        critic_threshold : if score drops more than this, revert
    """
    if not instruction or not instruction.strip():
        return {"ok": False, "error": "empty instruction"}

    target = target or DEFAULT_TARGET
    before = _read_file(target)
    if before is None:
        return {"ok": False, "error": f"target not found: {target}"}

    if verbose:
        print(f"   📄 الملف: {target}")
        print(f"   📏 الحجم قبل: {len(before)} حرف")

    # Build prompt
    web_files = _list_web_files()
    prompt = f"""USER INSTRUCTION (could be Arabic or English):
{instruction.strip()}

TARGET FILE: {target}

FILES IN web_new/:
{web_files}

--- CURRENT CONTENT OF {target} ---
{before[:12000]}
--- END CURRENT CONTENT ---

Apply the instruction. Output ONLY in the required format."""

    # Ask LLM
    resp = brain.ask(
        prompt=prompt,
        content_class="standard",
        system=SITE_EDITOR_SYSTEM,
        temperature=0.2,
    )
    if not resp.success:
        return {"ok": False, "error": resp.error}

    parsed = _parse_editor_output(resp.text or "")
    if not parsed.get("ok"):
        return {"ok": False, "error": parsed.get("error", "parse failed"),
                "raw": (resp.text or "")[:400]}

    new_content = parsed["content"]
    summary = parsed["summary"]

    # Validate
    val = _validate_content(target, new_content)
    if not val.get("ok"):
        return {"ok": False, "error": f"invalid output: {val['error']}",
                "summary": summary}

    # Optional critic before/after
    critic_before = None
    critic_after = None
    if check_critic:
        try:
            from brain.visual_critic import static_critique
            cb = static_critique(target)
            if cb.get("ok"):
                critic_before = cb.get("static_score")
        except Exception:
            pass

    # Write
    if not _write_file(target, new_content):
        return {"ok": False, "error": "write failed"}

    # Post-write critic
    if check_critic:
        try:
            from brain.visual_critic import static_critique
            ca = static_critique(target)
            if ca.get("ok"):
                critic_after = ca.get("static_score")
        except Exception:
            pass

    # Revert if quality dropped too much
    if (check_critic and critic_before is not None and critic_after is not None
            and critic_before - critic_after > critic_threshold):
        _write_file(target, before)
        return {
            "ok": False,
            "error": f"quality dropped: {critic_before:.1f} → {critic_after:.1f} (reverted)",
            "summary": summary,
        }

    if verbose:
        print(f"   📏 الحجم بعد: {len(new_content)} حرف")
        print(f"   📝 التغيير: {summary}")

    return {
        "ok": True,
        "target": target,
        "summary": summary,
        "before_size": len(before),
        "after_size": len(new_content),
        "provider": resp.provider,
        "model": resp.model,
        "latency_ms": resp.latency_ms,
        "critic_before": critic_before,
        "critic_after": critic_after,
    }


def render_arabic(result: Dict[str, Any]) -> str:
    if not result.get("ok"):
        return f"❌ فشل التعديل: {result.get('error')}"

    lines = [
        f"✅ تم التعديل في {result.get('target')}",
        f"   📝 {result.get('summary')}",
        f"   📏 {result.get('before_size')} → {result.get('after_size')} حرف",
    ]
    cb = result.get("critic_before")
    ca = result.get("critic_after")
    if cb is not None and ca is not None:
        arrow = "↑" if ca > cb else ("↓" if ca < cb else "=")
        lines.append(f"   🎨 جودة: {cb} → {ca} ({arrow})")
    return "\n".join(lines)


# ───────────────────────────────────────────────
# Self-test
# ───────────────────────────────────────────────

if __name__ == "__main__":
    print("Site Editor — module loaded")
    print("Usage: edit_site(brain, instruction, target=web_new/index.html)")
    print()
    print("Files in web_new/:")
    print(_list_web_files())
