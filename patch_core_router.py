path = "brain/core.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

changes = 0

# 1. Add import
if "from brain import router as task_router" not in c:
    c = c.replace(
        "from brain import preprocessor",
        "from brain import preprocessor\nfrom brain import router as task_router",
        1,
    )
    if "task_router" not in c:
        # fallback: add after existing brain imports
        c = c.replace(
            "from brain import prime_directives as PD",
            "from brain import prime_directives as PD\nfrom brain import router as task_router",
            1,
        )
    changes += 1

# 2. In ask(): add router call before registry
old = '''        # 3. EXECUTE via registry (with automatic fallback)
        response = self.registry.call_with_fallback(
            prompt=prompt,
            model=model,
            system=combined_system,
            temperature=temperature,
        )'''

new = '''        # 3. SMART ROUTING (pick best provider/model for this task)
        if model is None:
            try:
                available = list(self.available_providers().keys())
                available = [n for n in available if self.available_providers()[n]["is_available"]]
                routing = task_router.analyze(prompt, available)
                if routing.get("model"):
                    model = routing["model"]
            except Exception:
                pass

        # 4. EXECUTE via registry (with automatic fallback)
        response = self.registry.call_with_fallback(
            prompt=prompt,
            model=model,
            system=combined_system,
            temperature=temperature,
        )'''

if old in c and "SMART ROUTING" not in c:
    c = c.replace(old, new, 1)
    changes += 1

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print(f"CHANGES: {changes}")
