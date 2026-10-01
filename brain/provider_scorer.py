"""
brain/provider_scorer.py
========================
Tracks real performance of each provider per task type.
Stores results in memory/data/provider_metrics.json

Records: success/fail counts, latency, last failure time.
Provides a 0-100 score.
"""

import os
import json
import time
from datetime import datetime
from typing import Optional, Dict, Any

try:
    from brain.core_paths import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = os.path.expanduser("~/moroai")


METRICS_FILE = os.path.join(PROJECT_ROOT, "memory", "data", "provider_metrics.json")


def _load() -> dict:
    if not os.path.exists(METRICS_FILE):
        return {}
    try:
        with open(METRICS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(METRICS_FILE), exist_ok=True)
    try:
        with open(METRICS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _key(provider: str, task_type: str) -> str:
    return f"{provider}::{task_type}"


def _default() -> dict:
    return {
        "success": 0,
        "fail": 0,
        "total_latency_ms": 0.0,
        "last_success": None,
        "last_fail": None,
        "cooldown_until": 0.0,
    }


def record_success(provider: str, task_type: str, latency_ms: float = 0) -> None:
    """Record a successful call."""
    data = _load()
    k = _key(provider, task_type)
    entry = data.get(k, _default())
    entry["success"] += 1
    try:
        entry["total_latency_ms"] += max(0.0, float(latency_ms or 0))
    except (TypeError, ValueError):
        pass
    entry["last_success"] = datetime.now().isoformat()
    entry["cooldown_until"] = 0.0  # clear cooldown on success
    data[k] = entry
    _save(data)


def record_failure(provider: str, task_type: str, cooldown_sec: int = 300) -> None:
    """Record a failed call. Apply cooldown after 2+ failures."""
    data = _load()
    k = _key(provider, task_type)
    entry = data.get(k, _default())
    entry["fail"] += 1
    entry["last_fail"] = datetime.now().isoformat()
    if entry["fail"] >= 2:
        entry["cooldown_until"] = time.time() + cooldown_sec
    data[k] = entry
    _save(data)


def in_cooldown(provider: str, task_type: str) -> bool:
    """Is this provider on cooldown for this task type?"""
    data = _load()
    entry = data.get(_key(provider, task_type))
    if not entry:
        return False
    return time.time() < entry.get("cooldown_until", 0.0)


def score(provider: str, task_type: str) -> float:
    """
    Score 0-100.
    - Unknown provider -> 50 (neutral)
    - Weighted: 70% success rate + 30% speed.
    """
    data = _load()
    entry = data.get(_key(provider, task_type))
    if not entry:
        return 50.0

    s = entry.get("success", 0)
    f = entry.get("fail", 0)
    total = s + f
    if total == 0:
        return 50.0

    success_rate = s / total
    avg_latency = entry.get("total_latency_ms", 0) / max(s, 1)
    # speed_score: 1s -> 0.83, 5s -> 0.50, 20s -> 0.20
    speed_score = 1.0 / (1.0 + avg_latency / 5000.0)

    raw = 0.7 * success_rate + 0.3 * speed_score
    return round(raw * 100, 1)


def stats(provider: Optional[str] = None, task_type: Optional[str] = None) -> dict:
    data = _load()
    if provider:
        k = _key(provider, task_type or "general")
        return {k: data.get(k, _default())}
    return data


def summary() -> str:
    """Multi-line text summary for CLI."""
    data = _load()
    if not data:
        return "(no metrics yet)"

    lines = []
    for k in sorted(data.keys()):
        provider, task_type = k.split("::", 1)
        sc = score(provider, task_type)
        v = data[k]
        s = v.get("success", 0)
        f = v.get("fail", 0)
        cd = " (cooldown)" if in_cooldown(provider, task_type) else ""
        lines.append(f"  {provider:14} | {task_type:10} | score={sc:5} | ok={s:3} fail={f:3}{cd}")
    return "\n".join(lines)


if __name__ == "__main__":
    print("Provider Scorer — current metrics")
    print("=" * 60)
    print(summary())
    print()
    print("Data file:", METRICS_FILE)
