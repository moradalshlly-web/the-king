"""
brain/history_updater.py
========================

Automatic refresher for stale search history entries.

Runs when MOROAI starts (or via CLI command).
Refreshes up to 3 stale entries per run (protects phone).
"""

import time
from typing import Dict

from brain import search_history
from brain import search_cache


MAX_REFRESHES_PER_RUN = 3


def refresh_stale(limit: int = MAX_REFRESHES_PER_RUN,
                  verbose: bool = False) -> Dict[str, int]:
    """Refresh oldest stale entries."""
    stats = {"checked": 0, "refreshed": 0, "failed": 0, "skipped": 0}

    stale_ids = search_history.entries_to_refresh(limit=limit)
    if not stale_ids:
        return stats

    # Clear cache so we fetch fresh data
    try:
        search_cache.clear()
    except Exception:
        pass

    # Import here to avoid circular import
    from brain.preprocessor import execute_preempt

    for entry_id in stale_ids:
        stats["checked"] += 1
        item = search_history.get_entry(entry_id)
        if not item:
            stats["skipped"] += 1
            continue

        tool = item.get("tool", "")
        args = item.get("args", {})

        if verbose:
            print(f"  Refreshing {entry_id} ({tool}: {args.get('query','?')})...")

        try:
            call = {"tool": tool, "args": args}
            result = execute_preempt(call)
            if result.get("success"):
                stats["refreshed"] += 1
            else:
                stats["failed"] += 1
        except Exception as e:
            if verbose:
                print(f"    ERROR: {e}")
            stats["failed"] += 1

        time.sleep(1)

    return stats


def status() -> Dict[str, int]:
    return search_history.stats()


if __name__ == "__main__":
    print("History Updater")
    print("=" * 40)
    st = status()
    print(f"Total entries : {st['total']}")
    print(f"Stale (>12h)  : {st['stale']}")
    print()

    if st["stale"] == 0:
        print("Nothing to refresh.")
    else:
        print(f"Refreshing up to {MAX_REFRESHES_PER_RUN} stale entries...")
        result = refresh_stale(verbose=True)
        print()
        print(f"Checked  : {result['checked']}")
        print(f"Refreshed: {result['refreshed']}")
        print(f"Failed   : {result['failed']}")
