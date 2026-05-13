"""
app.py — Flask web app for Pakistan Fresh Graduate Job Board.
Runs monitor_core.run_monitor() on startup and every 6 hours via APScheduler.
"""

import threading
import logging
from datetime import datetime
from flask import Flask, jsonify, render_template
from apscheduler.schedulers.background import BackgroundScheduler

from monitor_core import run_monitor

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

# ── Scheduler ─────────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(_run_job, "interval", hours=6, id="monitor",
                  next_run_time=datetime.now())   # run immediately on startup
scheduler.start()

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


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
