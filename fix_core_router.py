path = "brain/core.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

if "SMART ROUTING" in c:
    print("ALREADY DONE")
    raise SystemExit(0)

# The exact block including the extra comment line
old = '''        # 4. EXECUTE via registry (with automatic fallback)
        # Merge MOROAI identity + lessons + any per-call system prompt
        parts = [self.identity]'''

new = '''        # 3. SMART ROUTING (pick best model for this task type)
        if model is None:
            try:
                avail = self.available_providers()
                available = [n for n, info in avail.items() if info.get("is_available")]
                routing = task_router.analyze(prompt, available)
                if routing.get("model"):
                    model = routing["model"]
            except Exception:
                pass

        # 4. EXECUTE via registry (with automatic fallback)
        # Merge MOROAI identity + lessons + any per-call system prompt
        parts = [self.identity]'''

if old in c:
    c = c.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("PATCHED")
else:
    print("ANCHOR NOT FOUND AGAIN")
