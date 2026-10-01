"""
brain/vision.py
===============

Reads MOROAI's vision files from memory/vision/.
Used by /evolve to know what to build next.
"""

import os
from typing import Dict, List

try:
    from .core_paths import PROJECT_ROOT
except ImportError:
    from core_paths import PROJECT_ROOT


VISION_DIR = os.path.join(PROJECT_ROOT, "memory", "vision")

VISION_FILES = {
    "mission": "MISSION.md",
    "capabilities": "CAPABILITIES.md",
    "gaps": "GAPS.md",
    "roadmap": "ROADMAP.md",
    "roadmap_2026": "ROADMAP_2026.md",
    "smart_routing": "SMART_ROUTING.md",
    "research_topics": "RESEARCH_TOPICS.md",
}


def load_vision() -> Dict[str, str]:
    """Load all vision files as a dict {key: content}."""
    out = {}
    for key, filename in VISION_FILES.items():
        path = os.path.join(VISION_DIR, filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                out[key] = f.read()
        else:
            out[key] = ""
    return out


def vision_prompt() -> str:
    """Return a compact prompt with the vision content."""
    v = load_vision()
    parts = []
    if v["mission"]:
        parts.append("### MISSION\n" + v["mission"])
    if v["capabilities"]:
        parts.append("### CAPABILITIES\n" + v["capabilities"])
    if v["gaps"]:
        parts.append("### GAPS\n" + v["gaps"])
    if v["roadmap"]:
        parts.append("### ROADMAP\n" + v["roadmap"])
    if v.get("roadmap_2026"):
        parts.append("### ROADMAP_2026\n" + v["roadmap_2026"])
    if v.get("smart_routing"):
        parts.append("### SMART_ROUTING\n" + v["smart_routing"])
    if v.get("research_topics"):
        parts.append("### RESEARCH_TOPICS\n" + v["research_topics"])
    return "\n\n".join(parts)


def vision_summary() -> str:
    """Short summary for status display."""
    v = load_vision()
    lines = []
    for k in ["mission", "capabilities", "gaps", "roadmap", "roadmap_2026", "smart_routing", "research_topics"]:
        size = len(v.get(k, ""))
        lines.append(f"  {k:15} : {size} chars")
    return "\n".join(lines)


if __name__ == "__main__":
    print("Vision directory:", VISION_DIR)
    print()
    v = load_vision()
    for key, content in v.items():
        print(f"[{key}] {len(content)} chars")
        print(content[:200])
        print("---")
