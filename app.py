"""
app.py — Flask web app for Pakistan Fresh Graduate Job Board.
Job data is pushed from your local Mac via /api/push (LinkedIn blocks server IPs).
"""

import os
import threading
import logging
from datetime import datetime
from flask import Flask, jsonify, render_template, request

# APScheduler only imported if not in push-only mode
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from monitor_core import run_monitor
    _HAS_SCHEDULER = True
except Exception:
    _HAS_SCHEDULER = False

PUSH_SECRET = os.environ.get("PUSH_SECRET", "pakjobs-secret")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = Flask(__name__)

# ── Shared state ──────────────────────────────────────────────────────────────
_lock       = threading.Lock()
_data       = {"jobs": [], "run_at": None, "total": 0}
_status     = "loading"   # "loading" | "ready" | "error"
_log_lines  = []          # last N log lines for /api/status

MAX_LOG_LINES = 100

def _log_fn(msg):
    log.info(msg)
    with _lock:
        _log_lines.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        if len(_log_lines) > MAX_LOG_LINES:
            _log_lines.pop(0)

def _run_job():
    global _data, _status
    _log_fn("Monitor run starting...")
    try:
        result = run_monitor(log=_log_fn)
        with _lock:
            _data   = result
            _status = "ready"
        _log_fn(f"Monitor run complete — {result['total']} jobs found.")
    except Exception as exc:
        _log_fn(f"Monitor run FAILED: {exc}")
        with _lock:
            _status = "error"

# ── Scheduler (only runs locally where LinkedIn works) ────────────────────────
if _HAS_SCHEDULER and os.environ.get("DISABLE_SCRAPER") != "1":
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(_run_job, "interval", hours=6, id="monitor",
                      next_run_time=datetime.now())
    scheduler.start()
else:
    # On Render: start in ready state (waiting for push)
    with _lock:
        _status = "ready"

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/jobs")
def api_jobs():
    with _lock:
        payload = {
            "status":  _status,
            "run_at":  _data["run_at"],
            "total":   _data["total"],
            "jobs":    _data["jobs"],
        }
    return jsonify(payload)


@app.route("/api/status")
def api_status():
    with _lock:
        payload = {
            "status": _status,
            "run_at": _data["run_at"],
            "total":  _data["total"],
            "log":    list(_log_lines[-30:]),
        }
    return jsonify(payload)


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Trigger an immediate monitor re-run (admin use)."""
    t = threading.Thread(target=_run_job, daemon=True)
    t.start()
    return jsonify({"message": "Refresh triggered."})


@app.route("/api/push", methods=["POST"])
def api_push():
    """
    Receive job data pushed from your local Mac.
    Requires header: X-Secret: <PUSH_SECRET>
    Body: JSON with {"jobs": [...], "run_at": "...", "total": N}
    """
    global _data, _status
    secret = request.headers.get("X-Secret", "")
    if secret != PUSH_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    body = request.get_json(silent=True)
    if not body or "jobs" not in body:
        return jsonify({"error": "Invalid payload"}), 400
    with _lock:
        _data   = body
        _status = "ready"
    log.info(f"Push received — {body.get('total', 0)} jobs updated.")
    return jsonify({"ok": True, "total": body.get("total", 0)})


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
