path = "brain/core.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# 1. Import LearningMemory
if "from memory.learning import LearningMemory" not in c:
    c = c.replace(
        "from memory.manager import MemoryManager",
        "from memory.manager import MemoryManager\nfrom memory.learning import LearningMemory",
        1,
    )

# 2. Init learning in __init__
if "self.learning = LearningMemory()" not in c:
    c = c.replace(
        "        # Subsystems\n        self.memory = MemoryManager()",
        "        # Subsystems\n        self.memory = MemoryManager()\n        self.learning = LearningMemory()",
        1,
    )

# 3. Inject lessons into system prompt in ask()
old_block = """        # 3. EXECUTE via registry (with automatic fallback)
        # Merge MOROAI identity with any per-call system prompt
        if system:
            combined_system = self.identity + "\\n\\n" + system
        else:
            combined_system = self.identity"""

new_block = """        # 3. RECALL: search for relevant lessons
        lessons = self.learning.search_lessons(prompt, limit=3)
        lessons_text = ""
        if lessons:
            bullets = "\\n".join(f"- {l['rule']}" for l in lessons)
            lessons_text = (
                "\\n\\nRelevant lessons learned from past interactions:\\n"
                + bullets
            )

        # 4. EXECUTE via registry (with automatic fallback)
        # Merge MOROAI identity + lessons + any per-call system prompt
        parts = [self.identity]
        if lessons_text:
            parts.append(lessons_text.strip())
        if system:
            parts.append(system)
        combined_system = "\\n\\n".join(parts)"""

if old_block not in c:
    print("BLOCK NOT FOUND")
else:
    c = c.replace(old_block, new_block, 1)

# 4. Save episode after execution (in addition to existing _log)
old_log = """        # 4. REFLECT: save to memory
        self._log(prompt, response, content_class)

        return response"""
new_log = """        # 5. REFLECT: save to memory + learning DB
        self._log(prompt, response, content_class)
        try:
            self.learning.save_episode(
                prompt=prompt,
                response=response.text,
                success=response.success,
                provider=response.provider,
                model=response.model,
                latency_ms=response.latency_ms,
                tokens_used=response.tokens_used,
                content_class=content_class,
                error=response.error,
            )
        except Exception:
            pass

        return response"""

if old_log not in c:
    print("LOG BLOCK NOT FOUND")
else:
    c = c.replace(old_log, new_log, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("PATCH DONE")
