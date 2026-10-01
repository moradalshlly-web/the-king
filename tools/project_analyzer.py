"""
tools/project_analyzer.py
=========================
Open Source Project Analyzer for MOROAI.

What it does (3 steps):
    1. SEARCH   : finds top GitHub projects for a topic (from RESEARCH_TOPICS.md)
    2. ANALYZE  : fetches project description + file structure
    3. COMPARE  : compares it against MOROAI's own manifest
    4. REPORT   : saves a report to memory/workspace/analyzer/

Isolation Mode:
    When the user stops using MOROAI, it enters ISOLATION MODE:
    - Picks a topic from RESEARCH_TOPICS.md
    - Imports the best project into its workspace
    - Studies it, learns from it, tries to replicate it
    - Notifies the owner when 90%+ match is achieved

This file never modifies other project files. It only reads and reports.
"""

import os
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

try:
    from ..brain.core_paths import PROJECT_ROOT
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from brain.core_paths import PROJECT_ROOT
    except ImportError:
        PROJECT_ROOT = os.path.expanduser("~/moroai")


# ═══════════════════════════════════════════════════════════
# Paths
# ═══════════════════════════════════════════════════════════

VISION_DIR = os.path.join(PROJECT_ROOT, "memory", "vision")
TOPICS_FILE = os.path.join(VISION_DIR, "RESEARCH_TOPICS.md")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "memory", "workspace", "analyzer")
ISOLATION_DIR = os.path.join(PROJECT_ROOT, "memory", "workspace", "isolation")
NOTIFICATIONS_FILE = os.path.join(PROJECT_ROOT, "memory", "notifications.jsonl")


# ═══════════════════════════════════════════════════════════
# 1. Read topics from RESEARCH_TOPICS.md
# ═══════════════════════════════════════════════════════════

def read_topics() -> List[Dict[str, str]]:
    """
    Read the topics list from RESEARCH_TOPICS.md.
    Returns list of {number, title, keywords}.
    """
    topics = []
    if not os.path.exists(TOPICS_FILE):
        return topics

    try:
        with open(TOPICS_FILE, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return topics

    # Look for lines like: ### 1. self-improving ai systems
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("### "):
            title_part = line[4:].strip()
            # Remove numbering like "1. " or "1) "
            if ". " in title_part[:4]:
                title_part = title_part.split(". ", 1)[1]
            topics.append({
                "title": title_part,
                "keywords": title_part,  # simple: use title as keywords
            })

    return topics


# ═══════════════════════════════════════════════════════════
# 2. Search GitHub for a topic
# ═══════════════════════════════════════════════════════════

def search_github(query: str, limit: int = 5, min_stars: int = 100) -> List[Dict[str, Any]]:
    """
    Search GitHub for repositories matching the query.
    Filters by minimum stars to get serious projects only.
    Uses MOROAI's existing github_search tool.
    """
    try:
        from tools.github import search_repos
        # GitHub filter: stars:>=N
        enhanced = query if min_stars <= 0 else f"{query} stars:>={min_stars}"
        results = search_repos(enhanced, limit=limit)
        if isinstance(results, list):
            return results
        return []
    except Exception as e:
        return [{"error": str(e)}]


# ═══════════════════════════════════════════════════════════
# 3. Analyze a single project (from GitHub search result)
# ═══════════════════════════════════════════════════════════

def analyze_project(project: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract the key info from a GitHub search result.
    Returns a structured dict.
    """
    return {
        "name": project.get("name") or project.get("full_name", "unknown"),
        "url": project.get("html_url") or project.get("url", ""),
        "description": project.get("description", ""),
        "stars": project.get("stars") or project.get("stargazers_count", 0),
        "language": project.get("language", "unknown"),
        "license": (
            project.get("license", {}).get("spdx_id")
            if isinstance(project.get("license"), dict)
            else project.get("license", "unknown")
        ),
        "topics": project.get("topics", []),
        "updated_at": project.get("updated_at", ""),
    }


# ═══════════════════════════════════════════════════════════
# 4. Compare a project against MOROAI's manifest
# ═══════════════════════════════════════════════════════════

def compare_with_moroai(project: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare a project's capabilities against MOROAI's own manifest.
    Simple check: does MOROAI have the same language? similar topics?
    """
    try:
        from brain.project_scanner import scan_project
        manifest = scan_project()
    except Exception:
        manifest = {"total_files": 0, "directories": {}}

    comparison = {
        "project_name": project.get("name", "?"),
        "morai_total_files": manifest.get("total_files", 0),
        "morai_directories": list(manifest.get("directories", {}).keys()),
        "language_match": project.get("language", "").lower() == "python",
        "license_ok": project.get("license", "").lower() in ("mit", "apache-2.0", "bsd-3-clause"),
        "gap_suggested": [],
    }

    # Simple gap suggestions
    desc = (project.get("description") or "").lower()
    if "agent" in desc and "agent" not in str(manifest.get("directories", {})):
        comparison["gap_suggested"].append("agent architecture")
    if "nlp" in desc and "arabic" in desc:
        comparison["gap_suggested"].append("arabic nlp")
    if "self" in desc and "improv" in desc:
        comparison["gap_suggested"].append("self-improvement loop")

    return comparison


# ═══════════════════════════════════════════════════════════
# 5. Save a report
# ═══════════════════════════════════════════════════════════

def save_report(topic: str, projects: List[Dict], comparisons: List[Dict]) -> str:
    """
    Save a report to memory/workspace/analyzer/.
    Returns the report file path.
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_topic = "".join(c if c.isalnum() or c in "-_" else "_" for c in topic)[:40]
    filename = f"report-{ts}-{safe_topic}.md"
    filepath = os.path.join(REPORTS_DIR, filename)

    lines = []
    lines.append(f"# تقرير تحليل: {topic}")
    lines.append(f"")
    lines.append(f"**التاريخ:** {datetime.now().isoformat()}")
    lines.append(f"**عدد المشاريع:** {len(projects)}")
    lines.append(f"")
    lines.append("---")
    lines.append("")

    for proj, comp in zip(projects, comparisons):
        lines.append(f"## {proj.get('name', '?')}")
        lines.append(f"- **URL:** {proj.get('url', '')}")
        lines.append(f"- **الوصف:** {proj.get('description', '')}")
        lines.append(f"- **النجوم:** {proj.get('stars', 0)}")
        lines.append(f"- **اللغة:** {proj.get('language', '?')}")
        lines.append(f"- **الرخصة:** {proj.get('license', '?')}")
        lines.append(f"- **تحديث:** {proj.get('updated_at', '?')}")
        lines.append(f"")
        lines.append(f"**المقارنة مع MOROAI:**")
        lines.append(f"- لغات متطابقة: {comp.get('language_match', False)}")
        lines.append(f"- رخصة مقبولة: {comp.get('license_ok', False)}")
        gaps = comp.get("gap_suggested", [])
        if gaps:
            lines.append(f"- فجوات مقترحة: {', '.join(gaps)}")
        else:
            lines.append(f"- فجوات مقترحة: (لا شيء)")
        lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


# ═══════════════════════════════════════════════════════════
# 6. Main entry: analyze a single topic
# ═══════════════════════════════════════════════════════════

def analyze_topic(topic: str, limit: int = 3) -> Dict[str, Any]:
    """
    Full pipeline for one topic:
        search -> analyze -> compare -> save report
    """
    raw = search_github(topic, limit=limit)
    if not raw:
        return {"success": False, "error": "No results", "topic": topic}

    analyzed = [analyze_project(p) for p in raw if isinstance(p, dict)]
    comparisons = [compare_with_moroai(p) for p in analyzed]

    report_path = save_report(topic, analyzed, comparisons)

    # ─── Cloud upload (best-effort, never blocks) ───
    cloud_result = None
    try:
        from tools.cloud_memory import upload_report
        cloud_result = upload_report(report_path)
    except Exception as e:
        cloud_result = {"success": False, "error": str(e)}

    return {
        "success": True,
        "topic": topic,
        "projects_found": len(analyzed),
        "report_path": report_path,
        "cloud": cloud_result,
        "projects": analyzed,
    }


# ═══════════════════════════════════════════════════════════
# 7. ISOLATION MODE
# ═══════════════════════════════════════════════════════════

def notify_owner(message: str, kind: str = "info") -> None:
    """
    Save a notification to memory/notifications.jsonl.
    The user will see it next time they open MOROAI.
    """
    try:
        os.makedirs(os.path.dirname(NOTIFICATIONS_FILE), exist_ok=True)
        entry = {
            "time": datetime.now().isoformat(),
            "kind": kind,
            "message": message,
            "read": False,
        }
        with open(NOTIFICATIONS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def enter_isolation_mode(max_topics: int = 3) -> Dict[str, Any]:
    """
    When the user stops using MOROAI, this is called.

    MOROAI enters its workspace, picks topics one by one,
    searches GitHub, analyzes projects, and saves reports.

    It ALSO saves a notification for the owner:
        "أثناء عزلتك، تعلّمت من مشروع X."

    This does NOT modify MOROAI itself. It only:
        - searches
        - analyzes
        - saves reports
        - notifies the owner
    """
    os.makedirs(ISOLATION_DIR, exist_ok=True)

    topics = read_topics()
    if not topics:
        return {"success": False, "error": "No topics in RESEARCH_TOPICS.md"}

    topics = topics[:max_topics]
    results = []
    started = time.time()

    notify_owner(
        f"بدأت العزلة: سأدرس {len(topics)} مواضيع في الـ workspace.",
        kind="isolation_start",
    )

    for t in topics:
        try:
            r = analyze_topic(t["title"], limit=3)
            results.append(r)
            if r.get("success"):
                notify_owner(
                    f"تعلّمت من {r['projects_found']} مشاريع حول: {t['title']}",
                    kind="isolation_learned",
                )
                # Cloud already uploaded inside analyze_topic
        except Exception as e:
            results.append({"success": False, "topic": t["title"], "error": str(e)})

    elapsed = round(time.time() - started, 1)
    summary = {
        "success": True,
        "topics_analyzed": len(results),
        "elapsed_seconds": elapsed,
        "results": results,
    }

    # Save summary
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    summary_path = os.path.join(ISOLATION_DIR, f"session-{ts}.json")
    try:
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    notify_owner(
        f"انتهت العزلة: درست {len(results)} مواضيع في {elapsed} ثانية.",
        kind="isolation_end",
    )

    summary["summary_path"] = summary_path
    return summary


# ═══════════════════════════════════════════════════════════
# Self-test
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=== Project Analyzer ===")
    print()

    print("1) المواضيع الموجودة:")
    topics = read_topics()
    for i, t in enumerate(topics, 1):
        print(f"   {i}. {t['title']}")
    print()

    if topics:
        print(f"2) تحليل موضوع تجريبي: '{topics[0]['title']}'")
        print("   (سيستغرق بضع ثوانٍ)")
        r = analyze_topic(topics[0]["title"], limit=2)
        if r.get("success"):
            print(f"   ✅ مشاريع: {r['projects_found']}")
            print(f"   📄 التقرير: {r['report_path']}")
        else:
            print(f"   ❌ فشل: {r.get('error')}")
    else:
        print("   ⚠️ لا توجد مواضيع — أضف مواضيع في RESEARCH_TOPICS.md")
