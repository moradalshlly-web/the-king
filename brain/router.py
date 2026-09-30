"""
brain/router.py
===============

Smart task router for MOROAI.
Detects task type and picks the best provider/model.
"""

import re
from typing import Optional, List, Dict, Any


TASK_PATTERNS = {
    "code": [r"\bكود\b", r"\bبرمج\b", r"\bبايثون\b", r"\bدالة\b",
             r"\bcode\b", r"\bprogram\b", r"\bdebug\b", r"\.py\b"],
    "story": [r"\bرواية\b", r"\bقصة\b", r"\bشخصيات\b", r"\bمشهد\b",
              r"\bnovel\b", r"\bstory\b", r"\bcharacters?\b"],
    "reasoning": [r"\bحلل\b", r"\bخطط\b", r"\bفكر\b",
                  r"\banalyze\b", r"\bplan\b", r"\breason\b"],
    "translate": [r"\bترجم\b", r"\btranslate\b"],
    "quick": [r"^\s*(مرحبا|أهلا|السلام|hello|hi)\b",
              r"^\s*(نعم|لا|yes|no)\s*$"],
}


def detect_task_type(message: str) -> str:
    if not message:
        return "general"
    msg = message.strip()
    msg_lower = msg.lower()

    # Priority: story keywords check first (Arabic \b doesn't work well)
    for kw in ["رواية", "قصة", "شخصيات", "مشهد", "novel", "story"]:
        if kw in msg_lower:
            return "story"

    for task_type, patterns in TASK_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, msg_lower, re.IGNORECASE):
                return task_type
    arabic_chars = sum(1 for c in msg if '\u0600' <= c <= '\u06FF')
    if arabic_chars > len(msg) * 0.3:
        return "arabic"
    return "general"


PREFERENCES = {
    "arabic":    ["falcon", "qwen", "gemini", "groq", "ollama"],
    "code":      ["deepseek", "qwen", "groq", "openrouter", "ollama"],
    "reasoning": ["kimi", "glm", "gemini", "groq", "ollama"],
    "story":     ["kimi", "gemini", "groq", "ollama"],
    "translate": ["aya", "gemini", "qwen", "groq"],
    "quick":     ["groq", "cerebras", "gemini"],
    "general":   ["groq", "gemini", "openrouter", "ollama"],
}


MODEL_PREFERENCES = {
    "arabic":    {"ollama": "qwen2.5:7b", "groq": "qwen/qwen3.8-27b"},
    "code":      {"groq": "qwen/qwen3.8-27b", "ollama": "qwen2.5:7b"},
    "reasoning": {"gemini": "gemini-3.8-flash", "groq": "qwen/qwen3.8-27b"},
    "story":     {"gemini": "gemini-3.8-flash", "groq": "qwen/qwen3.8-27b"},
    "translate": {"gemini": "gemini-3.8-flash", "groq": "qwen/qwen3.8-27b"},
    "quick":     {"groq": "llama-3.1-8b-instant"},
    "general":   {},
}


def pick_provider(task_type, available):
    prefs = PREFERENCES.get(task_type, PREFERENCES["general"])
    for name in prefs:
        if name in available:
            return name
    return available[0] if available else None


def pick_model(task_type, provider):
    return MODEL_PREFERENCES.get(task_type, {}).get(provider)


def analyze(message, available):
    task_type = detect_task_type(message)
    provider = pick_provider(task_type, available)
    model = pick_model(task_type, provider) if provider else None
    return {
        "task_type": task_type,
        "provider": provider,
        "model": model,
        "reason": f"task='{task_type}' -> provider='{provider}' -> model='{model}'",
    }


if __name__ == "__main__":
    available = ["groq", "gemini", "openrouter", "ollama"]
    tests = [
        "اكتب لي دالة بايثون",
        "حلل لي هذه الرواية",
        "ترجم هذه الفقرة",
        "مرحبا كيف حالك",
        "خطط لبناء تطبيق",
    ]
    for t in tests:
        r = analyze(t, available)
        print(f"Input : {t}")
        print(f"Type  : {r['task_type']}")
        print(f"Choice: {r['provider']} / {r['model']}")
        print()
