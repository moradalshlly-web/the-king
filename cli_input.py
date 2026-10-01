"""
cli_input.py
============
Enhanced CLI input using prompt_toolkit.

Features:
    - Tab completion for /commands
    - Command history (up/down arrows)
    - Colored command highlighting
    - Fish-style auto-suggestions
"""

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings

import os

HISTORY_FILE = os.path.expanduser("~/.moroai_cli_history")


# All slash commands MOROAI supports
COMMANDS = [
    "/help", "/status", "/clear", "/history", "/export", "/time",
    "/provider", "/model", "/content", "/tools", "/search",
    "/ls", "/cat", "/run", "/build", "/vision", "/evolve",
    "/sessions", "/resume", "/checkpoint", "/checkpoints",
    "/accept", "/reject", "/memory", "/reflect", "/lessons",
    "/exit", "/quit",
]


_STYLE = Style.from_dict({
    "prompt": "ansimagenta bold",
    "": "ansiwhite",
})


_completer = WordCompleter(COMMANDS, ignore_case=True, sentence=True)


# Enter sends, Ctrl+J = newline, Tab completes
_kb = KeyBindings()


_session = None


def _get_session():
    """Lazy-init a single shared prompt session."""
    global _session
    if _session is None:
        try:
            _session = PromptSession(
                history=FileHistory(HISTORY_FILE),
                completer=_completer,
                auto_suggest=AutoSuggestFromHistory(),
                key_bindings=_kb,
                complete_while_typing=True,
            )
        except Exception:
            _session = None
    return _session


def ask_user(prompt_str: str = "> ") -> str:
    """
    Read one line from the user with full prompt_toolkit features.
    Falls back to input() if prompt_toolkit is unavailable.
    """
    session = _get_session()
    if session is None:
        return input(prompt_str)

    try:
        # ANSI prompt is supported by prompt_toolkit
        return session.prompt(ANSI(prompt_str))
    except (EOFError, KeyboardInterrupt):
        # Propagate — cli.py handles these
        raise
    except Exception:
        # Any error -> plain input fallback
        return input(prompt_str)


if __name__ == "__main__":
    print("Type /help and press Tab to see suggestions.")
    print("Press Ctrl+C to exit.\n")
    while True:
        try:
            line = ask_user("MOROAI> ")
            if line.strip() == "/exit":
                break
            print(f"  → {line}")
        except (EOFError, KeyboardInterrupt):
            print()
            break
