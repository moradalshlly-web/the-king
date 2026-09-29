"""
web/server.py
=============

Flask web server for MOROAI.
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

from brain.core import MOROAI
from brain.tool_loop import run_with_tools

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["JSON_AS_ASCII"] = False
CORS(app, resources={r"/api/*": {"origins": "*"}})

_brain = None


def get_brain():
    global _brain
    if _brain is None:
        _brain = MOROAI()
    return _brain


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    try:
        data = request.get_json(force=True, silent=True) or {}
        message = (data.get("message") or "").strip()
        use_tools = bool(data.get("tools", True))
        content_class = (data.get("content_class") or "standard").strip()

        if not message:
            return jsonify({"ok": False, "error": "Empty message"}), 400

        brain = get_brain()

        if use_tools:
            resp = run_with_tools(brain, message, content_class=content_class)
        else:
            resp = brain.ask(prompt=message, content_class=content_class)

        if resp.success:
            return jsonify({
                "ok": True,
                "reply": resp.text,
                "provider": resp.provider,
                "model": resp.model,
                "latency_ms": resp.latency_ms,
                "tokens": resp.tokens_used,
            })
        return jsonify({"ok": False, "error": resp.error or "Unknown error"}), 200

    except Exception as e:
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/status")
def api_status():
    try:
        brain = get_brain()
        providers = brain.available_providers()
        return jsonify({
            "ok": True,
            "owner": brain.owner.age_mode if brain.owner else None,
            "banned": brain.banned,
            "providers": providers,
            "episodes": brain.learning.count().get("episodes", 0),
            "lessons": brain.learning.count().get("lessons", 0),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/history")
def api_history():
    try:
        brain = get_brain()
        recent = brain.memory.load_recent(20)
        return jsonify({"ok": True, "history": recent})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    print()
    print("=" * 50)
    print("  MOROAI Web Interface")
    print("  Open in browser: http://localhost:5000")
    print("=" * 50)
    print()
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
