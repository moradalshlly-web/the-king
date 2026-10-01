"""
tools/pollinations.py
=====================

Image generation tool for MOROAI via Pollinations.ai.

Fully free, no API key required (anonymous tier).
Rate limit: 1 request per 15 seconds.
Endpoint: GET https://image.pollinations.ai/prompt/{prompt}

Models: flux (best), turbo (fast), stable-diffusion, kontext.
"""

import os
import uuid
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from typing import Optional, Dict, Any


API_BASE = "https://image.pollinations.ai/prompt"
USER_AGENT = "MOROAI/0.1"

try:
    from ..brain.core_paths import PROJECT_ROOT
except ImportError:
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from brain.core_paths import PROJECT_ROOT
    except ImportError:
        PROJECT_ROOT = os.path.expanduser("~/moroai")


IMAGES_DIR = os.path.join(PROJECT_ROOT, "output", "images")

VALID_MODELS = ["flux", "turbo", "stable-diffusion", "kontext"]


def generate_image(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    model: str = "flux",
    seed: Optional[int] = None,
    save_dir: Optional[str] = None,
    timeout: int = 120,
) -> Dict[str, Any]:
    """
    Generate an image from a text prompt.

    Returns:
        {success, path, url, model, width, height, error, latency_ms}
    """
    start = time.time()

    if not prompt.strip():
        return {"success": False, "error": "Empty prompt"}

    if model not in VALID_MODELS:
        model = "flux"

    # Clamp dimensions
    width = max(256, min(int(width), 2048))
    height = max(256, min(int(height), 2048))

    params = {
        "width": str(width),
        "height": str(height),
        "model": model,
        "nologo": "true",
    }
    if seed is not None:
        params["seed"] = str(seed)

    encoded = urllib.parse.quote(prompt, safe="")
    url = f"{API_BASE}/{encoded}?{urllib.parse.urlencode(params)}"

    target_dir = save_dir or IMAGES_DIR
    os.makedirs(target_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    short = uuid.uuid4().hex[:6]
    filename = f"img-{ts}-{short}.jpg"
    filepath = os.path.join(target_dir, filename)

    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "image/jpeg,image/png,*/*"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            content_type = resp.headers.get("Content-Type", "image/jpeg")

            if "image" not in content_type:
                body = data.decode("utf-8", errors="replace")[:300]
                return {
                    "success": False,
                    "error": f"Unexpected content type: {content_type} | {body}",
                }

        with open(filepath, "wb") as f:
            f.write(data)

        elapsed = round((time.time() - start) * 1000, 2)
        return {
            "success": True,
            "path": filepath,
            "url": url,
            "model": model,
            "width": width,
            "height": height,
            "bytes": len(data),
            "latency_ms": elapsed,
            "error": None,
        }

    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"Network: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def list_models() -> list:
    """Return available models."""
    return list(VALID_MODELS)


if __name__ == "__main__":
    import sys
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "a serene sunset over mountains"

    print(f"Generating: {prompt}")
    print(f"Target dir: {IMAGES_DIR}")
    print()

    result = generate_image(prompt)
    if result["success"]:
        print(f"✅ Success")
        print(f"   Path     : {result['path']}")
        print(f"   Model    : {result['model']}")
        print(f"   Size     : {result['width']}x{result['height']}")
        print(f"   Bytes    : {result['bytes']}")
        print(f"   Latency  : {result['latency_ms']}ms")
    else:
        print(f"❌ Failed: {result['error']}")
