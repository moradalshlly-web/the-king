"""
tools/youtube.py
================

YouTube search tool for MOROAI.

Uses yt-dlp (installed via pip) to search YouTube and extract video info.
No API key required.

Inspiration (no code copied):
    - yt-dlp official docs
    - youtube-search-python pattern
"""

import json
import subprocess
from typing import List, Dict


def search_youtube(query: str, limit: int = 5) -> List[Dict[str, str]]:
    """
    Search YouTube via yt-dlp.

    Returns list of {title, url, video_id, duration, channel}
    """
    if not query.strip():
        return []

    limit = max(1, min(int(limit), 20))

    # yt-dlp search syntax: ytsearchN:query
    search_term = f"ytsearch{limit}:{query}"

    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--dump-json",
                "--skip-download",
                "--no-warnings",
                "--flat-playlist",
                search_term,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return [{"title": "ERROR", "url": "", "video_id": "", "duration": "", "channel": "yt-dlp not installed"}]
    except subprocess.TimeoutExpired:
        return [{"title": "ERROR", "url": "", "video_id": "", "duration": "", "channel": "timeout"}]
    except Exception as e:
        return [{"title": "ERROR", "url": "", "video_id": "", "duration": "", "channel": str(e)}]

    if result.returncode != 0:
        return [{"title": "ERROR", "url": "", "video_id": "", "duration": "", "channel": result.stderr[:200]}]

    videos = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        vid_id = data.get("id", "")
        videos.append({
            "title": data.get("title", ""),
            "url": f"https://www.youtube.com/watch?v={vid_id}",
            "video_id": vid_id,
            "duration": str(data.get("duration", "") or ""),
            "channel": data.get("uploader", "") or data.get("channel", ""),
        })

    return videos


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "python tutorial"
    print(f"Searching YouTube: {q}\n")
    results = search_youtube(q, limit=3)
    for i, r in enumerate(results, 1):
        print(f"[{i}] {r['title']}")
        print(f"    {r['url']}")
        print(f"    Channel: {r['channel']}  Duration: {r['duration']}s")
        print()
    print(f"Found {len(results)} videos")
