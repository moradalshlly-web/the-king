"""
brain/quota_monitor.py
======================

Smart quota monitor for Ollama Cloud.

Real API structure (as of October 2026):
    {
      "activity": {
        "cost": "0.00000",
        "period": {"type": "last_4_weeks", ...},
        "models": []
      },
      "limits": {
        "monthly": {
          "usage": 0,
          "models": [{"name": "gemma4:31b", "request_count": 1}]
        }
      }
    }

Strategy:
    - Check quota AFTER each usage (not on a timer)
    - Cache result for 30 seconds
    - Trigger auto-switch when monthly usage > 90%
"""

import os
import json
import time
import urllib.request
import urllib.error
from typing import Dict, Optional, Any, List


USAGE_URL = "https://ollama.com/api/usage"
CACHE_TTL = 30
SWITCH_THRESHOLD = 0.90


_last_fetch = 0.0
_last_data: Optional[Dict[str, Any]] = None
_last_error: Optional[str] = None


def _fetch_usage(timeout: int = 10) -> Optional[Dict[str, Any]]:
    api_key = os.getenv("OLLAMA_API_KEY", "").strip()
    if not api_key:
        return None

    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "MOROAI/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, Exception):
        return None


def _parse(data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse the real Ollama Cloud response structure."""
    result = {
        "monthly": 0.0,
        "cost": "0.00000",
        "models": [],
        "period": "",
    }
    if not data:
        return result

    # Cost
    activity = data.get("activity", {})
    result["cost"] = activity.get("cost", "0.00000")
    period = activity.get("period", {})
    result["period"] = f"{period.get('starting_at','?')[:10]} → {period.get('ending_at','?')[:10]}"

    # Limits
    limits = data.get("limits", {})
    monthly = limits.get("monthly", {})
    try:
        result["monthly"] = float(monthly.get("usage", 0))
    except (TypeError, ValueError):
        result["monthly"] = 0.0

    # Models used
    models_list = monthly.get("models", [])
    if isinstance(models_list, list):
        result["models"] = models_list

    return result


def get_usage(force: bool = False) -> Dict[str, Any]:
    """
    Get current usage, using cache if fresh.

    Returns:
        {monthly, cost, models, period, fresh, error}
    """
    global _last_fetch, _last_data, _last_error

    now = time.time()
    if not force and _last_data is not None and (now - _last_fetch) < CACHE_TTL:
        return {**_last_data, "fresh": False, "error": _last_error}

    data = _fetch_usage()
    if data is None:
        _last_error = "fetch failed"
        if _last_data:
            return {**_last_data, "fresh": False, "error": _last_error}
        return {"monthly": 0.0, "cost": "?", "models": [], "period": "",
                "fresh": False, "error": _last_error}

    parsed = _parse(data)
    _last_data = parsed
    _last_fetch = now
    _last_error = None
    return {**parsed, "fresh": True, "error": None}


def should_switch() -> bool:
    """Check if we should switch to another provider (monthly > 90%)."""
    usage = get_usage()
    return usage.get("monthly", 0.0) >= SWITCH_THRESHOLD


def total_requests() -> int:
    """Return total requests this period."""
    usage = get_usage()
    return sum(m.get("request_count", 0) for m in usage.get("models", []))


def status_line() -> str:
    """One-line status for CLI."""
    u = get_usage()
    m = u.get("monthly", 0.0)
    total = total_requests()
    return f"Ollama Cloud: monthly={m*100:.1f}%  requests={total}  cost=${u.get('cost','?')}"


if __name__ == "__main__":
    print("Quota Monitor")
    print("=" * 50)
    u = get_usage(force=True)
    print(f"Monthly usage : {u['monthly']*100:.2f}%")
    print(f"Cost          : ${u['cost']}")
    print(f"Period        : {u['period']}")
    print(f"Total requests: {total_requests()}")
    print(f"Models used:")
    for m in u.get("models", []):
        print(f"  - {m.get('name','?')}: {m.get('request_count',0)} requests")
    print()
    print(f"Fresh        : {u['fresh']}")
    print(f"Error        : {u['error']}")
    print(f"Should switch? {should_switch()}")
    print()
    print(status_line())
