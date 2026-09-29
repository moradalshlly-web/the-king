"""
memory/manager.py
=================

Simple memory manager for MOROAI.

Responsibilities:
    - Save every interaction (prompt, response, provider, model, timing)
    - Load recent interactions for context
    - Store as JSONL (one JSON object per line) for easy append

Storage:
    ~/moroai/memory/data/interactions.jsonl

Inspiration (no code copied):
    - ScratchAgent (MIT): JSONL session storage pattern
    - Nexus Memory (MIT): memory layer separation
    - GPS AI Agent: chat session state pattern
"""

import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any


MEMORY_DIR = os.path.join(os.path.dirname(__file__), "data")
INTERACTIONS_FILE = os.path.join(MEMORY_DIR, "interactions.jsonl")


class MemoryManager:
    """Persistent memory for MOROAI interactions."""

    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path or INTERACTIONS_FILE
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

    # -------- Write --------

    def save_interaction(
        self,
        prompt: str,
        response_text: str,
        provider: str,
        model: str,
        success: bool,
        error: Optional[str] = None,
        tokens_used: Optional[int] = None,
        latency_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prompt": prompt,
            "response": response_text,
            "provider": provider,
            "model": model,
            "success": success,
            "error": error,
            "tokens_used": tokens_used,
            "latency_ms": latency_ms,
            "metadata": metadata or {},
        }
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # -------- Read --------

    def load_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        if not os.path.exists(self.file_path):
            return []
        records = []
        with open(self.file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records[-limit:]

    def count(self) -> int:
        if not os.path.exists(self.file_path):
            return 0
        with open(self.file_path, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    def clear(self) -> None:
        if os.path.exists(self.file_path):
            os.remove(self.file_path)

    def find_by_keyword(self, keyword: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not os.path.exists(self.file_path):
            return []
        kw = keyword.lower()
        matches = []
        with open(self.file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if kw in rec.get("prompt", "").lower() or kw in rec.get("response", "").lower():
                    matches.append(rec)
        return matches[-limit:]


if __name__ == "__main__":
    m = MemoryManager()
    print(f"Memory file : {m.file_path}")
    print(f"Count       : {m.count()}")
    m.save_interaction(
        prompt="test",
        response_text="ok",
        provider="test",
        model="test",
        success=True,
    )
    print(f"After write : {m.count()}")
    recent = m.load_recent(1)
    if recent:
        print(f"Last        : {recent[-1]['prompt']} -> {recent[-1]['response']}")
    print("✅ memory/manager.py self-test done.")
