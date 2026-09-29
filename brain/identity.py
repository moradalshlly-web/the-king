import os

IDENTITY_FILE = os.path.join(os.path.dirname(__file__), "prompts", "identity.txt")


def load_identity() -> str:
    if not os.path.exists(IDENTITY_FILE):
        return "You are MOROAI, a private AI assistant."
    try:
        with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return "You are MOROAI, a private AI assistant."
