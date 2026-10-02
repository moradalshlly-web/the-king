"""
brain/task_classifier.py
========================
Classifies a user message as "chat" or "build".

Mixed strategy (cheap + accurate):
    1. Question words present?  -> chat
    2. Build verbs present?     -> build
    3. Otherwise                -> ask LLM (one tiny call)

Returned dict:
    {"mode": "chat" | "build", "confidence": 0.0-1.0, "reason": "..."}
"""

import re
from typing import Dict, Any


# ─── Question markers (chat even if build verbs present) ───
QUESTION_MARKERS = [
    "كيف", "لماذا", "ليه", "ليش", "ماذا", "ماهي", "ما هي", "ما هو",
    "هل ", "هل؟", "هل يمكن", "ممكن", "متى", "أين", "وين",
    "وش ", "شن ", "شنو", "وضح", "اشرح", "فسر",
    "how ", "why ", "what ", "when ", "where ",
    "?", "؟",
]

# ─── Build verbs (imperative, action-oriented) ───
BUILD_VERBS = [
    # creation
    "أنشئ", "انشئ", "أنشا", "ابنِ", "ابني", "بناء", "صمّم", "صمم",
    "ولّد", "ولد", "اعمل", "انشيء", "انشأ",
    # writing / coding
    "اكتب لي", "اكتب ", "برمج", "كود", "شغّل", "أنجز",
    "اكتب",  # imperative "write"
    # "أريد ..." (intention with target)"
    "اريد", "أريد", "نبي", "نريد",
    # modification
    "أضف", "اضف", "ضيف", "عدّل", "عدل", "غيّر", "غير",
    "احذف", "امسح", "استبدل", "بدل",
    # modification (english)
    "create ", "build ", "make ", "generate ", "add ", "modify ",
    "edit ", "delete ", "remove ", "replace ",
]

# ─── Reference targets (implies concrete output) ───
BUILD_TARGETS = [
    "ملف", "file", "مجلد", "folder", "أداة", "tool", "module",
    "دالة", "function", "class", "css", "html", "javascript",
    ".py", ".js", ".html", ".css", ".json", ".md",
    "web_new", "tools/", "brain/", "providers/",
]

# ─── Site-related markers (implies site_edit) ───
SITE_TARGETS = [
    "الموقع", "موقع", "الصفحة", "صفحة", "الشات", "الشاشة",
    "مربع البحث", "زر الإرسال", "القائمة", "الهيدر", "الفوتر",
    "الدرج", "الشعار", "اللوجو", "اللون", "الألوان", "الثيم",
    "الخلفية", "الواجهة", "العنوان",
    "moroai.com", "web_new", "index.html",
]

SITE_VERBS = [
    "غيّر", "غير", "عدّل", "عدل", "أضف", "اضف", "ضيف",
    "احذف", "امسح", "خلي", "اجعل", "خليه", "خليها",
    "بدّل", "بدل", "استبدل", "حرّك", "حرك", "انقل",
]


def _contains_any(text: str, items) -> str:
    for item in items:
        if item in text:
            return item
    return ""


def _contains_any_in(text: str, items) -> str:
    for item in items:
        if item in text:
            return item
    return ""


def detect_site_edit(message: str) -> bool:
    """
    Return True if the message is an instruction to modify the website.
    Requires: site target + action verb.
    """
    if not message:
        return False
    msg = message.strip()
    target = _contains_any_in(msg, SITE_TARGETS)
    verb = _contains_any_in(msg, SITE_VERBS)
    return bool(target and verb)


def classify_keywords(message: str) -> Dict[str, Any]:
    """Pure keyword-based classification (no LLM)."""
    if not message:
        return {"mode": "chat", "confidence": 0.5, "reason": "empty"}

    msg = message.strip()
    lower = msg.lower()

    # 1. Questions -> chat (unless explicit command followed by target)
    q = _contains_any(lower, [q.lower() for q in QUESTION_MARKERS])
    b = _contains_any(msg, BUILD_VERBS)
    t = _contains_any(lower, [x.lower() for x in BUILD_TARGETS])

    # Site edit takes priority over generic build
    if detect_site_edit(msg):
        return {"mode": "site_edit", "confidence": 0.9,
                "reason": "site target + modification verb"}

    if q and not b:
        return {"mode": "chat", "confidence": 0.9,
                "reason": f"question marker: '{q}'"}

    if q and b:
        # Ambiguous: "كيف أنشئ ملف؟" -> chat (question wins)
        return {"mode": "chat", "confidence": 0.7,
                "reason": f"both question & verb ('{q}', '{b}')"}

    if b and t:
        # Strong: build verb + concrete target
        return {"mode": "build", "confidence": 0.95,
                "reason": f"verb='{b}' + target='{t}'"}

    if b:
        # Verb only -> likely build, but not certain
        return {"mode": "build", "confidence": 0.7,
                "reason": f"verb='{b}' only"}

    return {"mode": "unknown", "confidence": 0.4,
            "reason": "no clear marker"}


# ─── LLM fallback (tiny, cheap) ───

LLM_SYSTEM = """You are a binary classifier.

Read the user's message and answer with ONE word only:
    CHAT  — if the message is a question, greeting, explanation request, or conversation.
    BUILD — if the message is an imperative request to create/modify/delete files or code.

Answer with only CHAT or BUILD. Nothing else."""


def classify_llm(brain, message: str) -> Dict[str, Any]:
    """Ask the LLM for a definitive answer (used only when unsure)."""
    try:
        resp = brain.ask(
            prompt=message[:500],
            content_class="standard",
            system=LLM_SYSTEM,
            temperature=0.0,
            model=None,
        )
        if not resp.success:
            return {"mode": "chat", "confidence": 0.5,
                    "reason": "llm failed -> default chat"}

        text = (resp.text or "").strip().upper()
        if "BUILD" in text:
            return {"mode": "build", "confidence": 0.85,
                    "reason": "llm said BUILD"}
        return {"mode": "chat", "confidence": 0.85,
                "reason": "llm said CHAT"}

    except Exception as e:
        return {"mode": "chat", "confidence": 0.5,
                "reason": f"llm error: {e}"}


def classify(brain, message: str, use_llm: bool = True) -> Dict[str, Any]:
    """
    Main entry: classify a message.
    Uses keywords first; LLM only if confidence is low.
    """
    kw = classify_keywords(message)

    if kw["confidence"] >= 0.7:
        return kw

    if use_llm:
        llm = classify_llm(brain, message)
        llm["fallback_from"] = kw
        return llm

    return kw


# ═══════════════════════════════════════════════
# Self-test (no LLM)
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print("Task Classifier — keyword self-test")
    print("=" * 60)

    samples = [
        "مرحبا كيف حالك؟",
        "أنشئ ملف greeting.py في tools",
        "كيف أنشئ ملفاً في بايثون؟",
        "أضف زر تسجيل دخول للموقع",
        "ما هو Python؟",
        "عدّل ملف index.html وأضف شعاراً",
        "هل يمكنك مساعدتي؟",
        "اكتب لي دالة تحسب المجموع",
        "اشرح لي كيف يعمل الموقع",
        "احذف ملف test.py",
    ]

    for s in samples:
        r = classify_keywords(s)
        print(f"  [{r['mode']:5}] {r['confidence']:.2f}  ← \"{s}\"")
        print(f"          {r['reason']}")
