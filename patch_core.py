import re

path = "brain/core.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# 1. Add import
if "from brain.identity import load_identity" not in c:
    c = c.replace(
        "from providers.base import AIResponse",
        "from providers.base import AIResponse\nfrom brain.identity import load_identity",
        1,
    )

# 2. Load identity in __init__
if "self.identity = load_identity()" not in c:
    c = c.replace(
        "        # Subsystems\n        self.memory = MemoryManager()",
        "        # Identity\n        self.identity = load_identity()\n\n        # Subsystems\n        self.memory = MemoryManager()",
        1,
    )

# 3. Use identity in ask()
if "combined_system" not in c:
    old = '''        # 3. EXECUTE via registry (with automatic fallback)
        response = self.registry.call_with_fallback(
            prompt=prompt,
            model=model,
            system=system,
            temperature=temperature,
        )'''
    new = '''        # 3. EXECUTE via registry (with automatic fallback)
        # Merge MOROAI identity with any per-call system prompt
        if system:
            combined_system = self.identity + "\\n\\n" + system
        else:
            combined_system = self.identity

        response = self.registry.call_with_fallback(
            prompt=prompt,
            model=model,
            system=combined_system,
            temperature=temperature,
        )'''
    c = c.replace(old, new, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("PATCH DONE")
