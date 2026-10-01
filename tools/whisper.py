"""
tools/whisper.py
================

Speech-to-Text tool for MOROAI via Groq Whisper.

Groq provides Whisper Large v3 / v3-turbo for free.
Supports: Arabic, English, and 90+ languages.

Endpoint: POST https://api.groq.com/openai/v1/audio/transcriptions
Auth: Bearer GROQ_API_KEY
"""

import os
import json
import uuid
import urllib.request
import urllib.error
from typing import Optional, Dict, Any


API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
USER_AGENT = "MOROAI/0.1"

VALID_MODELS = [
    "whisper-large-v3",
    "whisper-large-v3-turbo",
    "distil-whisper-large-v3-en",
]


def transcribe(
    audio_path: str,
    model: str = "whisper-large-v3",
    language: Optional[str] = None,
    prompt: Optional[str] = None,
    response_format: str = "json",
    timeout: int = 120,
) -> Dict[str, Any]:
    """
    Transcribe an audio file to text.

    Args:
        audio_path : path to audio file (mp3, wav, m4a, ogg, flac, mp4, webm)
        model      : whisper model to use
        language   : optional ISO-639-1 code (ar, en, ...)
        prompt     : optional hint for style/vocabulary
        response_format : json | text | verbose_json

    Returns:
        {success, text, language, duration, model, error, latency_ms}
    """
    import time
    start = time.time()

    if not os.path.exists(audio_path):
        return {"success": False, "text": "", "error": f"File not found: {audio_path}"}

    if model not in VALID_MODELS:
        model = "whisper-large-v3"

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return {"success": False, "text": "", "error": "GROQ_API_KEY not set"}

    # Build multipart/form-data manually
    boundary = "----MOROAIBoundary" + uuid.uuid4().hex[:16]
    with open(audio_path, "rb") as f:
        file_data = f.read()

    filename = os.path.basename(audio_path)

    def _field(name: str, value: str) -> bytes:
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode("utf-8")

    body = b""
    body += (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    body += file_data
    body += b"\r\n"
    body += _field("model", model)
    body += _field("response_format", response_format)
    if language:
        body += _field("language", language)
    if prompt:
        body += _field("prompt", prompt)
    body += f"--{boundary}--\r\n".encode("utf-8")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": USER_AGENT,
    }

    req = urllib.request.Request(
        API_URL, data=body, headers=headers, method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")

        if response_format == "text":
            text = raw.strip()
            data = {}
        else:
            data = json.loads(raw)
            text = data.get("text", "").strip()

        elapsed = round((time.time() - start) * 1000, 2)
        return {
            "success": True,
            "text": text,
            "language": data.get("language", language or "auto"),
            "duration": data.get("duration"),
            "model": model,
            "latency_ms": elapsed,
            "error": None,
        }

    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            pass
        return {"success": False, "text": "", "error": f"HTTP {e.code}: {e.reason} | {err_body[:200]}"}
    except urllib.error.URLError as e:
        return {"success": False, "text": "", "error": f"Network: {e.reason}"}
    except Exception as e:
        return {"success": False, "text": "", "error": f"{type(e).__name__}: {e}"}


def list_models() -> list:
    return list(VALID_MODELS)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m tools.whisper <audio_file> [language]")
        print(f"Models: {VALID_MODELS}")
        sys.exit(1)

    path = sys.argv[1]
    lang = sys.argv[2] if len(sys.argv) > 2 else None
    print(f"Transcribing: {path}")
    if lang:
        print(f"Language   : {lang}")
    print()

    r = transcribe(path, language=lang)
    if r["success"]:
        print(f"✅ Success ({r['latency_ms']}ms)")
        print(f"Language: {r['language']}")
        if r.get("duration"):
            print(f"Duration: {r['duration']}s")
        print()
        print("--- Text ---")
        print(r["text"])
    else:
        print(f"❌ Failed: {r['error']}")
