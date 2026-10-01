"""
tools/edge_tts.py
=================

Text-to-Speech tool for MOROAI via edge-tts.

Uses Microsoft Edge's neural voices (free, no API key).
Supports 100+ languages including Arabic (EG, SA, and more).

Requires: pip install edge-tts
"""

import os
import uuid
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

try:
    import edge_tts
except ImportError:
    edge_tts = None


try:
    from ..brain.core_paths import PROJECT_ROOT
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from brain.core_paths import PROJECT_ROOT
    except ImportError:
        PROJECT_ROOT = os.path.expanduser("~/moroai")


AUDIO_DIR = os.path.join(PROJECT_ROOT, "output", "audio")

# Recommended Arabic voices
ARABIC_VOICES = {
    "ar-EG-SalmaNeural":   "مصرية - أنثى",
    "ar-EG-ShakirNeural":  "مصري - ذكر",
    "ar-SA-ZariyahNeural": "سعودية - أنثى",
    "ar-SA-HamedNeural":   "سعودي - ذكر",
    "ar-SY-AmanyNeural":   "سورية - أنثى",
    "ar-SY-LaithNeural":   "سوري - ذكر",
}

DEFAULT_VOICE = "ar-EG-SalmaNeural"


async def _synthesize(text: str, voice: str, rate: str, volume: str, output_path: str):
    """Run the async synthesis."""
    communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
    await communicate.save(output_path)


def text_to_speech(
    text: str,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    volume: str = "+0%",
    output_dir: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """
    Convert text to speech (MP3).

    Args:
        text        : the text to speak
        voice       : voice ID (e.g., "ar-EG-SalmaNeural")
        rate        : "+10%" or "-10%" (speed)
        volume      : "+0%" or "+50%" (volume)
        output_dir  : where to save MP3 (default: output/audio/)

    Returns:
        {success, path, voice, bytes, latency_ms, error}
    """
    import time
    start = time.time()

    if edge_tts is None:
        return {"success": False, "error": "edge-tts not installed. Run: pip install edge-tts"}

    if not text.strip():
        return {"success": False, "error": "Empty text"}

    # Limit text length to avoid huge files
    if len(text) > 5000:
        text = text[:5000]

    target_dir = output_dir or AUDIO_DIR
    os.makedirs(target_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    short = uuid.uuid4().hex[:6]
    filename = f"tts-{ts}-{short}.mp3"
    filepath = os.path.join(target_dir, filename)

    try:
        asyncio.run(_synthesize(text, voice, rate, volume, filepath))
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    if not os.path.exists(filepath):
        return {"success": False, "error": "File not created"}

    size = os.path.getsize(filepath)
    elapsed = round((time.time() - start) * 1000, 2)

    return {
        "success": True,
        "path": filepath,
        "voice": voice,
        "bytes": size,
        "latency_ms": elapsed,
        "error": None,
    }


def list_voices(language_filter: Optional[str] = None) -> list:
    """Return available voices (optionally filtered by language prefix)."""
    try:
        voices = asyncio.run(edge_tts.list_voices())
        if language_filter:
            voices = [v for v in voices if v.get("Locale", "").startswith(language_filter)]
        return voices
    except Exception:
        return []


if __name__ == "__main__":
    import sys
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "مرحبا، أنا مورواي، مساعدك الذكي."
    voice = DEFAULT_VOICE

    print(f"Text   : {text[:80]}")
    print(f"Voice  : {voice}")
    print(f"Target : {AUDIO_DIR}")
    print()

    r = text_to_speech(text, voice=voice)
    if r["success"]:
        print(f"✅ Success")
        print(f"   Path    : {r['path']}")
        print(f"   Bytes   : {r['bytes']}")
        print(f"   Latency : {r['latency_ms']}ms")
    else:
        print(f"❌ Failed: {r['error']}")
