"""
tools/hakim_tts.py
==================

Hakim AI Text-to-Speech tool for MOROAI.

Free tier, no credit card. OpenAI-compatible.
Arabic-first with 14 Arabic voices.

Note:
    Voice quality is good (non-metallic), but some pronunciation
    issues remain in Arabic (diacritics, ambiguous words).
    A dedicated Arabic Proofreader Agent will be built later to
    pre-process text before sending to TTS.

Models available: hakim-fast-v1, hakim-flash-v1
    (hakim-v2 and hakim-v3 are private preview)
"""

import os
import json
import uuid
import time
import urllib.request
import urllib.error
from datetime import datetime
from typing import Optional, Dict, Any


API_URL = "https://api.tryhakim.ai/v1/audio/speech"
USER_AGENT = "MOROAI/0.1"

# Recommended Arabic voices (verified working)
ARABIC_VOICES = {
    "cmok1nvqz000n10ar5pzc4569": {"name": "Amir",  "gender": "male"},
    "cmokbc1r70001vu39tnmjj9v7": {"name": "Nadia", "gender": "female"},
    "cmok1nvqg000h10arx9tcawir": {"name": "Reem",  "gender": "female"},
    "cmok1nvr9000r10armgbk0vc2": {"name": "Salma", "gender": "female"},
    "cmokbc1rs0007vu39x8tcgyty": {"name": "Ali",   "gender": "male"},
    "cmok1nvqa000f10ar8rpvncj4": {"name": "Khalid","gender": "male"},
    "cmokbc1rj0005vu3915vh4ehn": {"name": "Layan", "gender": "female"},
    "cmok1nvnk000310art55tbjch": {"name": "Layla", "gender": "female"},
    "cmokbc1rd0003vu39gqr7pps1": {"name": "Mahmoud","gender": "male"},
    "cmok1nvly000110ar7nni5zek": {"name": "Omar",  "gender": "male"},
    "cmok1nvqn000j10ar8ljluapq": {"name": "Yusuf", "gender": "male"},
}

DEFAULT_VOICE = "cmokbc1r70001vu39tnmjj9v7"  # Nadia
DEFAULT_MODEL = "hakim-fast-v1"

try:
    from ..brain.core_paths import PROJECT_ROOT
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from brain.core_paths import PROJECT_ROOT
    except ImportError:
        PROJECT_ROOT = os.path.expanduser("~/moroai")


AUDIO_DIR = os.path.join(PROJECT_ROOT, "output", "hakim")


def synthesize(
    text: str,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    output_dir: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """Convert Arabic text to MP3 using Hakim AI."""
    start = time.time()

    if not text.strip():
        return {"success": False, "error": "Empty text"}

    api_key = os.getenv("HAKIM_API_KEY", "").strip()
    if not api_key:
        return {"success": False, "error": "HAKIM_API_KEY not set"}

    if voice not in ARABIC_VOICES:
        voice = DEFAULT_VOICE

    target_dir = output_dir or AUDIO_DIR
    os.makedirs(target_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    short = uuid.uuid4().hex[:6]
    vname = ARABIC_VOICES.get(voice, {}).get("name", "voice")
    filename = f"hakim-{vname}-{ts}-{short}.mp3"
    filepath = os.path.join(target_dir, filename)

    payload = json.dumps({
        "model": model,
        "input": text[:5000],
        "voice": voice,
        "response_format": "mp3",
    }).encode("utf-8")

    req = urllib.request.Request(API_URL, data=payload, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
        "User-Agent": USER_AGENT,
    })

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if len(data) < 100:
            return {"success": False, "error": f"Audio too small: {len(data)} bytes"}
        with open(filepath, "wb") as f:
            f.write(data)
        return {
            "success": True,
            "path": filepath,
            "voice": ARABIC_VOICES.get(voice, {}).get("name", voice),
            "model": model,
            "bytes": len(data),
            "latency_ms": round((time.time() - start) * 1000, 2),
            "error": None,
        }
    except urllib.error.HTTPError as e:
        err = ""
        try:
            err = e.read().decode("utf-8")[:200]
        except Exception:
            pass
        return {"success": False, "error": f"HTTP {e.code}: {e.reason} | {err}"}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"Network: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def list_voices() -> Dict[str, Dict[str, str]]:
    """Return available Arabic voices."""
    return dict(ARABIC_VOICES)


if __name__ == "__main__":
    import sys
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "نحن لن نستسلم ننتصر أو نموت."
    voice = DEFAULT_VOICE

    print(f"Text  : {text}")
    print(f"Voice : {ARABIC_VOICES[voice]['name']} ({voice})")
    print()

    r = synthesize(text, voice=voice)
    if r["success"]:
        print(f"✅ Success")
        print(f"   Path    : {r['path']}")
        print(f"   Bytes   : {r['bytes']}")
        print(f"   Latency : {r['latency_ms']}ms")
    else:
        print(f"❌ Failed: {r['error']}")
