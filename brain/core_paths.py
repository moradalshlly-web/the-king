"""
brain/core_paths.py
===================

Central path definitions for MOROAI.

Keeping paths in one place makes it easy to:
    - Move the project later
    - Change storage locations
    - Migrate to cloud without touching feature code
"""

import os

# Project root = two levels up from this file (brain/ -> project/)
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

# Session state file (tracks last close/start info)
SESSION_STATE_FILE = ".moroai/session_state.json"

# Conversation log (append-only JSONL)
CONVERSATION_LOG = "memory/data/conversations.jsonl"

# Workspace root (isolated background sessions)
WORKSPACE_ROOT = ".moroai/workspace"
