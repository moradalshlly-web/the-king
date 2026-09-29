"""
brain/tools_registry.py
=======================

Registry of tools that MOROAI can call.

Textual calling protocol (Pattern B):
    MOROAI responds with a line of the form:
        TOOL: <tool_name> <arg1>=<val1> <arg2>=<val2> ...

    We parse it, execute the tool, and feed back the result.

Future (Pattern A): add JSON schema calling on top.

Inspiration (no code copied):
    - OpenAI Function Calling: tool descriptions
    - SWE-Agent: loop LLM -> tool call -> observation
    - Hermes function-calling: textual tool calls
"""

import re
import shlex
from typing import Dict, Any, Optional, Callable


# ============================================================
# Tool registry
# ============================================================

_TOOLS: Dict[str, Dict[str, Any]] = {}


def register(name: str, description: str, params: str, func: Callable):
    """
    Register a tool.

    Args:
        name        : tool name (used in `TOOL: <name>`)
        description : short description for the LLM
        params      : human-readable params (e.g. "path=<file>")
        func        : callable that takes **kwargs and returns a dict
    """
    _TOOLS[name] = {
        "name": name,
        "description": description,
        "params": params,
        "func": func,
    }


def all_tools() -> Dict[str, Dict[str, Any]]:
    return dict(_TOOLS)


def tools_prompt() -> str:
    """Return a compact prompt listing all tools."""
    lines = ["Available tools (use them when needed):"]
    for t in _TOOLS.values():
        lines.append(f"  - {t['name']} {t['params']}: {t['description']}")
    lines.append("")
    lines.append("To use a tool, respond with EXACTLY one line:")
    lines.append("  TOOL: <tool_name> <arg>=<value> <arg>=<value> ...")
    lines.append("Then STOP. You will receive the tool result in the next message.")
    lines.append("If no tool is needed, answer normally.")
    return "\n".join(lines)


# ============================================================
# Parser
# ============================================================

TOOL_PATTERN = re.compile(r"^\s*TOOL:\s*(\S+)\s*(.*)$", re.IGNORECASE | re.MULTILINE)


def parse_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """
    Parse a TOOL: line from LLM output.

    Returns {name, args} or None.
    Supports:
        TOOL: read_file path=brain/core.py
        TOOL: read_file path="brain/core.py"
        TOOL: search_reddit query="python asyncio" limit=5
    """
    if not text:
        return None

    m = TOOL_PATTERN.search(text)
    if not m:
        return None

    name = m.group(1).strip().lower()
    rest = m.group(2).strip()

    if name not in _TOOLS:
        return None

    args = {}
    if rest:
        try:
            parts = shlex.split(rest)
        except ValueError:
            return None
        for p in parts:
            if "=" not in p:
                continue
            k, _, v = p.partition("=")
            args[k.strip()] = v.strip()

    return {"name": name, "args": args}


def execute_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool by name. Never raises."""
    tool = _TOOLS.get(name)
    if not tool:
        return {"success": False, "error": f"Unknown tool: {name}"}
    try:
        result = tool["func"](**args)
        if not isinstance(result, dict):
            return {"success": True, "result": str(result)}
        return result
    except TypeError as e:
        return {"success": False, "error": f"Bad arguments: {e}"}
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def format_result(result: Dict[str, Any], max_len: int = 3000) -> str:
    """Format tool result as text for the LLM."""
    if not result.get("success"):
        return f"TOOL RESULT (error): {result.get('error', 'unknown error')}"

    # Common keys
    for k in ("content", "stdout", "result"):
        if k in result and result[k]:
            txt = str(result[k])
            return f"TOOL RESULT:\n{txt[:max_len]}"

    if "items" in result:
        return "TOOL RESULT:\n" + "\n".join(str(i) for i in result["items"][:100])

    return f"TOOL RESULT: {str(result)[:max_len]}"


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    # Register a dummy tool
    register(
        name="dummy",
        description="Test tool",
        params="x=<value>",
        func=lambda x="": {"success": True, "result": f"got {x}"},
    )

    # Test parsing
    assert parse_tool_call("TOOL: dummy x=hello") == {"name": "dummy", "args": {"x": "hello"}}
    assert parse_tool_call('TOOL: dummy x="hello world"') == {"name": "dummy", "args": {"x": "hello world"}}
    assert parse_tool_call("just a normal reply") is None

    # Test execution
    r = execute_tool("dummy", {"x": "world"})
    print("Exec:", r)
    assert r["success"]

    print("\nTool prompt sample:")
    print(tools_prompt())

    print("\n✅ tools_registry tests passed.")
