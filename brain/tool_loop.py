"""
brain/tool_loop.py
==================

Agentic loop for MOROAI: LLM -> tool call -> execute -> observe -> LLM.

Limits:
    - Max iterations: 3 (protects free-tier quota)
    - If the LLM never calls a tool, returns immediately (fast path)
    - If a tool fails, the error is fed back to the LLM for a retry

Registration:
    Call `register_default_tools()` once at startup.

Inspiration (no code copied):
    - SWE-Agent: LLM -> tool call -> observation loop
    - OpenHands: agent loop with max_iterations
    - Hermes function-calling: textual tool calls
"""

from typing import Dict, Any, Optional

from brain import tools_registry as TR
from brain import preprocessor as PP
from providers.base import AIResponse


MAX_ITERATIONS = 3


# ============================================================
# Register default MOROAI tools
# ============================================================

_registered = False


def register_default_tools() -> None:
    """Register all MOROAI tools once."""
    global _registered
    if _registered:
        return

    from tools.file_ops import FileOps
    from tools.shell import ShellOps
    from tools.reddit import search_reddit
    from tools.web_search import search_web
    from tools.youtube import search_youtube
    from tools.github import search_repos
    from tools.stack_exchange import search_stackexchange
    from tools.wikipedia import search_wikipedia, get_summary
    from tools.pollinations import generate_image
    from tools.whisper import transcribe

    fops = FileOps()
    sops = ShellOps()

    # read_file
    TR.register(
        name="read_file",
        description="Read the content of a text file inside the project.",
        params="path=<relative_path>",
        func=lambda path: fops.read_file(path),
    )

    # list_dir
    TR.register(
        name="list_dir",
        description="List files in a directory inside the project.",
        params="path=<relative_path>",
        func=lambda path=".": fops.list_dir(path, recursive=False),
    )

    # write_file
    TR.register(
        name="write_file",
        description="Write text to a file inside the project. Creates parent dirs.",
        params='path=<relative_path> content="<text>"',
        func=lambda path, content="": fops.write_file(path, content),
    )

    # run_shell
    TR.register(
        name="run_shell",
        description="Run a safe, allowlisted shell command inside the project.",
        params='cmd="<command>"',
        func=lambda cmd="": sops.run(cmd),
    )

    # search_reddit
    TR.register(
        name="search_reddit",
        description="Search Reddit for posts matching a query (returns titles + URLs).",
        params='query="<text>" limit=5',
        func=lambda query, limit=5: {
            "success": True,
            "result": _format_reddit(search_reddit(query, limit=int(limit))),
        },
    )

    # web_search
    TR.register(
        name="web_search",
        description="Search the web via DuckDuckGo for information.",
        params='query="<text>" limit=5',
        func=lambda query, limit=5: {
            "success": True,
            "result": _format_web(search_web(query, int(limit))),
        },
    )

    # youtube_search
    TR.register(
        name="youtube_search",
        description="Search YouTube for videos.",
        params='query="<text>" limit=3',
        func=lambda query, limit=3: {
            "success": True,
            "result": _format_youtube(search_youtube(query, int(limit))),
        },
    )

    # github_search
    TR.register(
        name="github_search",
        description="Search GitHub for open-source projects (returns stars, license, language).",
        params='query="<text>" limit=5',
        func=lambda query, limit=5: {
            "success": True,
            "result": _format_github(search_repos(query, int(limit))),
        },
    )

    # stackoverflow_search
    TR.register(
        name="stackoverflow_search",
        description="Search Stack Overflow for programming questions and answers.",
        params='query="<text>" limit=5',
        func=lambda query, limit=5: {
            "success": True,
            "result": _format_stack(search_stackexchange(query, limit=int(limit))),
        },
    )

    # wikipedia_search
    TR.register(
        name="wikipedia_search",
        description="Search Wikipedia in Arabic or English for knowledge.",
        params='query="<text>" lang="ar" limit=5',
        func=lambda query, lang="ar", limit=5: {
            "success": True,
            "result": _format_wiki(search_wikipedia(query, lang=lang, limit=int(limit))),
        },
    )

    # image_generate
    TR.register(
        name="image_generate",
        description="Generate an image from a text description (free, no API key).",
        params='prompt="<text>" width=1024 height=1024 model="flux"',
        func=lambda prompt, width=1024, height=1024, model="flux": _do_image(prompt, width, height, model),
    )

    # audio_transcribe
    TR.register(
        name="audio_transcribe",
        description="Transcribe an audio file to text (Arabic, English, 90+ langs).",
        params='path="<audio_file>" language="ar"',
        func=lambda path, language=None: _do_transcribe(path, language),
    )

    # text_to_speech (Hakim + edge-tts fallback)
    TR.register(
        name="text_to_speech",
        description="Generate speech from text. Arabic-first with automatic fallback (Hakim AI -> edge-tts).",
        params='text="<text>" voice="Nadia"',
        func=lambda text, voice="cmokbc1r70001vu39tnmjj9v7": _do_text_to_speech(text, voice),
    )

    _registered = True


# ============================================================
# Tool helper functions
# ============================================================

def _do_text_to_speech(text, voice="cmokbc1r70001vu39tnmjj9v7"):
    """Generate speech from text: try Hakim (Arabic), fallback to edge-tts."""
    text = (text or "").strip()
    if not text:
        return {"success": False, "error": "Empty text", "kind": "speech"}

    try:
        from tools.hakim_tts import synthesize
        r = synthesize(text, voice=voice)
        if r.get("success"):
            return {
                "success": True,
                "path": r.get("path"),
                "kind": "speech",
                "engine": "hakim",
                "error": None,
            }
    except Exception:
        pass

    try:
        from tools.edge_tts import text_to_speech
        r = text_to_speech(text, voice="ar-EG-SalmaNeural")
        return {
            "success": r.get("success", False),
            "path": r.get("path"),
            "kind": "speech",
            "engine": "edge-tts",
            "error": r.get("error"),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "kind": "speech"}


def _do_image(prompt, width=1024, height=1024, model="flux"):
    """Generate an image via Pollinations (free, no key)."""
    try:
        from tools.pollinations import generate_image
        r = generate_image(prompt, width=int(width), height=int(height))
        return {
            "success": r.get("success", False),
            "path": r.get("path"),
            "kind": "image",
            "error": r.get("error"),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "kind": "image"}


def _do_transcribe(path, language=None):
    """Transcribe audio file to text via Groq Whisper."""
    try:
        from tools.whisper import transcribe
        r = transcribe(path, language=language)
        return {
            "success": r.get("success", False),
            "text": r.get("text", ""),
            "language": r.get("language"),
            "kind": "transcript",
            "error": r.get("error"),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "kind": "transcript"}


def _format_reddit(posts) -> str:
    if not posts:
        return "(no results)"
    lines = []
    for i, p in enumerate(posts, 1):
        lines.append(f"{i}. r/{p['subreddit']} — {p['title']}")
        lines.append(f"   {p['url']}")
    return "\n".join(lines)


# ============================================================
# The loop
# ============================================================

def _format_web(results) -> str:
    if not results:
        return "(no results)"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   {r['url']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet'][:150]}")
    return "\n".join(lines)


def _format_youtube(results) -> str:
    if not results:
        return "(no videos)"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   {r['url']}")
        lines.append(f"   by {r.get('channel','?')}  ({r.get('duration','?')}s)")
    return "\n".join(lines)


def _media_direct_response(result, tool_name):
    """Build a direct AIResponse for media outputs (no LLM roundtrip)."""
    if not result.get("success"):
        text = "[فشل " + tool_name + "] " + str(result.get("error", "unknown"))
        return AIResponse(
            text=text,
            model=tool_name,
            provider="direct",
            success=False,
            error=result.get("error"),
            latency_ms=0,
        )

    kind = result.get("kind", "")
    path = result.get("path", "")

    if kind == "speech":
        engine = result.get("engine", "?")
        text = "[تم توليد الصوت — " + engine + "]\n" + path
    elif kind == "image":
        text = "[تم توليد الصورة]\n" + path
    elif kind == "transcript":
        text = result.get("text", "(فارغ)")
        lang = result.get("language", "")
        if lang:
            text = "[" + lang + "]\n" + text
    else:
        text = "[تم التنفيذ]\n" + str(result)

    return AIResponse(
        text=text,
        model=tool_name,
        provider="direct",
        success=True,
        latency_ms=0,
    )


def run_with_tools(
    brain,
    prompt: str,
    content_class: str = "standard",
    system: Optional[str] = None,
    max_iterations: int = MAX_ITERATIONS,
    verbose: bool = False,
    on_chunk=None,
):
    """
    Run the agentic loop.

    Returns the final AIResponse.
    """
    register_default_tools()

    # ---- PRE-PROCESSOR: FORCE tool usage if detected ----
    detected = PP.detect_tool(prompt)
    if detected is not None:
        if verbose:
            print(f"[preprocessor] detected: {detected['tool']} args={detected['args']}")

        # Execute the tool immediately
        result = PP.execute_preempt(detected)

        # For media tools (speech/image/transcript): return directly, no LLM
        if result.get("kind") in ("speech", "image", "transcript"):
            return _media_direct_response(result, detected["tool"])

        formatted = PP.format_results(result)

        # Build a new prompt that includes the tool result
        FORMAT_RULES = (
            "قدم إجابة عربية منظمة. لكل عنصر اعرض 4 أسطر فقط:\n"
            "  🎯 ماهية: <وصف في سطر واحد>\n"
            "  ⭐ التقييم: <ميزته الأساسية في سطر واحد>\n"
            "  🔧 للمحاكاة: <أفضل بديل أو استخدام>\n"
            "  📜 الرخصة: <SPDX> — مسموح/ممنوع (باختصار)\n"
            "افصل بين العناصر بسطر فارغ.\n"
            "لا تكتب جداول. لا تكرر. لا تطل."
        )

        enriched_prompt = (
            f"سياق من الأداة ({detected['tool']}):\n\n"
            f"{formatted}\n\n"
            f"---\n"
            f"سؤال المستخدم الأصلي: {prompt}\n\n"
            f"{FORMAT_RULES}"
        )

        # Call the LLM with the enriched prompt (no tool loop needed)
        response = brain.ask(
            prompt=enriched_prompt,
            content_class=content_class,
            system=system,
            on_chunk=on_chunk,
        )
        return response

    # Build the tool-aware system prompt
    tool_section = TR.tools_prompt()
    if system:
        sys = f"{system}\n\n{tool_section}"
    else:
        sys = tool_section

    # First call
    response = brain.ask(
        prompt=prompt,
        content_class=content_class,
        system=sys,
        on_chunk=on_chunk,
    )

    if not response.success:
        return response

    # Iterate
    for iteration in range(max_iterations):
        call = TR.parse_tool_call(response.text)
        if call is None:
            # No tool call -> final answer
            return response

        # Execute
        result = TR.execute_tool(call["name"], call["args"])

        # Surface verification results to the LLM and user
        if isinstance(result, dict) and result.get("verification"):
            v = result["verification"]
            if not v.get("passed"):
                failed = ", ".join(v.get("failed", []))
                print(f"⚠️  تحذير المدقق: {failed}")
                # Add note to the tool result shown to the LLM
                if "content" in result and isinstance(result["content"], str):
                    result["content"] = (
                        "[تحذير المدقق: " + failed + "]\n" + result["content"]
                    )

        formatted = TR.format_result(result)

        if verbose:
            print(f"[tool_loop] iter={iteration+1} "
                  f"tool={call['name']} args={call['args']} "
                  f"success={result.get('success')}")

        # Ask the LLM again with the result
        followup_prompt = (
            f"Tool result for `{call['name']}`:\n\n"
            f"{formatted}\n\n"
            f"Now give the final answer to the user's original question. "
            f"Do not call another tool unless absolutely necessary."
        )
        response = brain.ask(
            prompt=followup_prompt,
            content_class=content_class,
            system=sys,
            on_chunk=on_chunk,
        )
        if not response.success:
            return response

    return response


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    register_default_tools()
    tools = TR.all_tools()
    print(f"Registered tools: {list(tools.keys())}")
    assert "read_file" in tools
    assert "list_dir" in tools
    assert "run_shell" in tools
    assert "search_reddit" in tools
    print("✅ tool_loop registration OK.")
