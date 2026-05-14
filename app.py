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

# Database (optional — disabled if DATABASE_URL not set)
try:
    import db as _db
    _db.init_db()
    _HAS_DB = True
    log_startup = logging.getLogger(__name__)
    log_startup.info("Database initialised.")
except Exception as _db_err:
    _HAS_DB = False

PUSH_SECRET = os.environ.get("PUSH_SECRET", "pakjobs-secret")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = Flask(__name__)

# ── Shared state ──────────────────────────────────────────────────────────────
_lock       = threading.Lock()
_data       = {"jobs": [], "internships": [], "run_at": None, "total": 0}
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
            "status":      _status,
            "run_at":      _data["run_at"],
            "total":       _data["total"],
            "jobs":        _data["jobs"],
            "internships": _data["internships"],
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
        # Normalise keys so /api/jobs never gets a KeyError regardless of payload shape
        _data = {
            "jobs":        body.get("jobs", []),
            "internships": body.get("internships", []),
            "run_at":      body.get("run_at"),
            "total":       body.get("total", 0),
        }
        _status = "ready"
    log.info(f"Push received — {body.get('total', 0)} jobs updated.")
    return jsonify({"ok": True, "total": body.get("total", 0)})


@app.route("/api/subscribe", methods=["POST"])
def api_subscribe():
    """Store a subscriber's email and preferences."""
    if not _HAS_DB:
        return jsonify({"error": "Database not configured"}), 503

    body = request.get_json(silent=True) or {}
    email      = (body.get("email") or "").strip().lower()
    cities     = body.get("cities", [])
    depts      = body.get("depts", [])
    exp_ranges = body.get("exp_ranges", [])

    if not email or "@" not in email:
        return jsonify({"error": "Invalid email"}), 400
    if not cities and not depts and not exp_ranges:
        return jsonify({"error": "Select at least one preference"}), 400

    try:
        _db.add_subscriber(email, cities, depts, exp_ranges)
        return jsonify({"ok": True})
    except Exception as e:
        log.error(f"Subscribe error: {e}")
        return jsonify({"error": "Something went wrong"}), 500


@app.route("/api/subscriber-count")
def api_subscriber_count():
    if not _HAS_DB:
        return jsonify({"count": 0})
    try:
        return jsonify({"count": _db.subscriber_count()})
    except Exception:
        return jsonify({"count": 0})


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
