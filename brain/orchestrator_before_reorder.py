"""
brain/orchestrator.py
=====================
Tri-Brain conductor.

Flow:
    1. classify (chat vs build)
    2a. chat  -> legacy: brain.ask(prompt)
    2b. build -> planner -> checker -> executor -> arabic_layer

Result object:
{
    "mode": "chat" | "build",
    "text": "<display text in Arabic>",
    "success": bool,
    "raw": {...}  # AIResponse or execution report
}
"""

from typing import Dict, Any, Optional


def _render_chat(AIResponse) -> Dict[str, Any]:
    """Legacy chat rendering."""
    if not AIResponse.success:
        return {
            "mode": "chat",
            "success": False,
            "text": f"❌ تعذّر الرد: {AIResponse.error}",
            "raw": AIResponse,
        }
    return {
        "mode": "chat",
        "success": True,
        "text": AIResponse.text,
        "raw": AIResponse,
        "provider": AIResponse.provider,
        "model": AIResponse.model,
        "latency_ms": AIResponse.latency_ms,
    }


def _handle_site_edit(brain, message: str,
                      verbose: bool = True) -> Dict[str, Any]:
    """
    Handle a site-edit request: modify web_new/index.html by NL instruction.
    """
    try:
        from brain.site_editor import edit_site, render_arabic
    except Exception as e:
        return {
            "mode": "site_edit",
            "success": False,
            "text": f"❌ site_editor غير متاح: {e}",
            "raw": None,
        }

    # Checkpoint before modification
    try:
        if hasattr(brain, "checkpoints"):
            brain.checkpoints.create(f"Before site_edit: {message[:60]}")
    except Exception:
        pass

    # Run the edit
    result = edit_site(
        brain,
        instruction=message,
        target="web_new/index.html",
        check_critic=True,
        verbose=verbose,
    )

    if result.get("ok"):
        text = "🌐 " + render_arabic(result)
        text += "\n\n💡 حدّث الصفحة لرؤية التغيير."
        return {
            "mode": "site_edit",
            "success": True,
            "text": text,
            "raw": result,
            "target": result.get("target"),
        }
    else:
        text = "❌ " + render_arabic(result)
        if result.get("summary"):
            text += f"\n(ملخص المحاولة: {result.get('summary')})"
        return {
            "mode": "site_edit",
            "success": False,
            "text": text,
            "raw": result,
        }


def handle(brain, message: str,
           style: str = "friendly",
           content_class: str = "standard",
           verbose: bool = True) -> Dict[str, Any]:
    """
    Main entry: handle one user message end-to-end.

    Returns a unified result dict (see module docstring).
    """
    if not message or not message.strip():
        return {
            "mode": "chat",
            "success": False,
            "text": "(رسالة فارغة)",
            "raw": None,
        }

    # ─── 1. Classify ───
    try:
        from brain.task_classifier import classify
        cls = classify(brain, message)
    except Exception as e:
        # If classifier fails, fall back to chat
        cls = {"mode": "chat", "reason": f"classifier error: {e}"}

    mode = cls.get("mode", "chat")

    # ─── 2a. Chat path ───
    if mode != "build":
        if verbose:
            print(f"💬 [chat · {cls.get('confidence', 0):.2f}]")
        resp = brain.ask(
            prompt=message,
            content_class=content_class,
        )
        return _render_chat(resp)

    # ─── 2a.5 Site edit path ───
    if mode == "site_edit":
        if verbose:
            print(f"🌐 [site_edit · {cls.get('confidence', 0):.2f}] mode ← site editor")
        return _handle_site_edit(brain, message, verbose=verbose)

    # ─── 2b. Build path ───
    if verbose:
        print(f"🏗️  [build · {cls.get('confidence', 0):.2f}] mode ← planner")

    # ── Planner ──
    try:
        from brain.planner import plan
        p = plan(brain, message)
    except Exception as e:
        return {
            "mode": "build",
            "success": False,
            "text": f"❌ فشل التخطيط: {e}",
            "raw": None,
        }

    if not p.get("success"):
        return {
            "mode": "build",
            "success": False,
            "text": f"❌ لم أستطع التخطيط: {p.get('error', '?')}",
            "raw": p,
        }

    # Handle "ask" plan (rare — truly unactionable)
    first_step = (p.get("steps") or [{}])[0]
    if first_step.get("action") == "ask":
        q = first_step.get("description", "أحتاج توضيحاً")
        return {
            "mode": "build",
            "success": False,
            "text": f"❓ {q}",
            "raw": p,
        }

    # ── Plan Checker (independent audit) ──
    check = None
    try:
        from brain.plan_checker import check_plan
        check = check_plan(brain, p, planner_provider=p.get("provider", ""))
        if verbose and check:
            print(f"🔍 [check · {check.get('verdict')} · {check.get('score')}/10]")
    except Exception:
        pass

    # If checker rejects -> stop and report
    if check and check.get("verdict") == "reject":
        return {
            "mode": "build",
            "success": False,
            "text": (
                "🚫 الخطة رُفضت من المدقق المستقل:\n"
                + "\n".join(f"   • {c}" for c in check.get("concerns", [])[:3])
                + f"\n\n💡 التغذية الراجعة: {check.get('feedback', '')[:300]}"
            ),
            "raw": {"plan": p, "check": check},
            "plan": p,
            "check": check,
        }

    # ── Executor ──
    try:
        from brain.executor import execute_plan
        report = execute_plan(brain, p, verbose=verbose)
    except Exception as e:
        return {
            "mode": "build",
            "success": False,
            "text": f"❌ فشل التنفيذ: {e}",
            "raw": p,
            "plan": p,
            "check": check,
        }

    # ── Visual Critic + Refiner (for HTML outputs) ──
    critique = None
    refinement = None
    try:
        # هل أنشأنا أي .html؟
        html_files = [
            r["path"] for r in (report.get("results") or [])
            if isinstance(r, dict) and r.get("path", "").endswith(".html")
            and r.get("success")
        ]
        if html_files:
            target_path = html_files[0]
            # Refiner: يحسّن الملف حتى الهدف (افتراضي 8/10)
            from brain.refiner import refine_until
            if verbose:
                print()
                print("   ✨ التحسين الذاتي (حتى 8/10)...")
            refinement = refine_until(
                brain, target_path,
                target=8.0,
                max_iterations=4,
                verbose=verbose,
            )
            critique = refinement.get("final_critique") if refinement else None
    except Exception as e:
        if verbose:
            print(f"   ⚠️ Refiner: {e}")

    # ── Skill Registry (auto-learn) ──
    skills_touched = []
    try:
        from memory.skills import SkillRegistry
        sr = SkillRegistry()
        skills_touched = sr.learn_from_execution(p, report, source="tri-brain")
    except Exception:
        pass

    # ── Arabic Layer ──
    try:
        from brain.arabic_layer import render
        text = render(report, style=style, include_steps=True)
    except Exception:
        # Fallback: minimal English
        text = f"Done: {report.get('steps_ok')}/{report.get('steps_total')}"

    # Append visual critique (if any)
    if critique and critique.get("ok"):
        try:
            from brain.visual_critic import render_arabic as render_critique
            text += "\n\n" + render_critique(critique)
        except Exception:
            text += f"\n\n🎨 الناقد البصري: {critique.get('overall', '?')}/10"

    # Append refinement report (if any)
    if refinement and refinement.get("iterations", 0) > 0:
        try:
            from brain.refiner import render_arabic as render_refine
            text += "\n\n" + render_refine(refinement)
        except Exception:
            text += (
                f"\n\n🔧 التحسين: {refinement.get('initial_score','?')}"
                f" → {refinement.get('final_score','?')}"
            )

    # Append skills learned (if any)
    if skills_touched:
        text += "\n\n🎓 مهارات تحدّثت:"
        for sk in set(skills_touched):
            text += f"\n   • {sk}"

    # Add check summary if refined
    if check and check.get("verdict") == "refine" and check.get("concerns"):
        text += "\n\n⚠️ ملاحظات المدقق:\n" + "\n".join(
            f"   • {c}" for c in check["concerns"][:2]
        )

    return {
        "mode": "build",
        "success": bool(report.get("success")),
        "text": text,
        "raw": report,
        "plan": p,
        "check": check,
        "skills_touched": skills_touched,
        "visual_critique": critique,
        "refinement": refinement,
    }


# ═══════════════════════════════════════════════
# Self-test (no LLM)
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print("Orchestrator module loaded.")
    print("Usage: handle(brain, message, style='friendly')")
