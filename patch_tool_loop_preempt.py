path = "brain/tool_loop.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# 1. Add import
if "from brain import preprocessor as PP" not in c:
    c = c.replace(
        "from brain import tools_registry as TR",
        "from brain import tools_registry as TR\nfrom brain import preprocessor as PP",
        1,
    )

# 2. Add preempt check at the start of run_with_tools
old = '''def run_with_tools(
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
    register_default_tools()'''

new = '''def run_with_tools(
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
        enriched_prompt = (
            f"سياق من الأداة ({detected['tool']}):\\n\\n"
            f"{formatted}\\n\\n"
            f"---\\n"
            f"سؤال المستخدم الأصلي: {prompt}\\n\\n"
            f"قدم إجابة نهائية بالعربية بناءً على النتائج أعلاه. "
            f"لا تقل أنك لا تعرف، استخدم البيانات المعروضة."
        )

        # Call the LLM with the enriched prompt (no tool loop needed)
        response = brain.ask(
            prompt=enriched_prompt,
            content_class=content_class,
            system=system,
        )
        return response'''

if old in c and "PP.detect_tool" not in c:
    c = c.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("PATCHED")
else:
    print("SKIP (already patched or anchor not found)")
