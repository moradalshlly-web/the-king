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

    _registered = True


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


def run_with_tools(
    brain,
    prompt: str,
    content_class: str = "standard",
    system: Optional[str] = None,
    max_iterations: int = MAX_ITERATIONS,
    verbose: bool = False,
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
