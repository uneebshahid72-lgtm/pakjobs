#!/usr/bin/env python3
"""
push_jobs.py — Run the monitor locally and push results to Render.
Run this on your Mac whenever you want fresh jobs on the website.

Usage:
  python3 ~/Downloads/jobboard/push_jobs.py
"""

import json
import urllib.request
import urllib.error
from monitor_core import run_monitor

RENDER_URL  = "https://pakjobs.onrender.com/api/push"
PUSH_SECRET = "pakjobs-secret"   # must match PUSH_SECRET env var on Render

def push(data):
    body = json.dumps(data).encode("utf-8")
    req  = urllib.request.Request(
        RENDER_URL,
        data    = body,
        method  = "POST",
        headers = {
            "Content-Type": "application/json",
            "X-Secret":     PUSH_SECRET,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            print(f"\n  Pushed {result.get('total', 0)} jobs to {RENDER_URL}")
            print("  Website is now updated!\n")
    except urllib.error.HTTPError as e:
        print(f"\n  Push failed: HTTP {e.code} — {e.read().decode()}\n")
    except Exception as e:
        print(f"\n  Push failed: {e}\n")

if __name__ == "__main__":
    print("\n  Running monitor locally...")
    data = run_monitor()
    print(f"\n  Scan complete — {data['total']} jobs found.")
    print("  Pushing to website...")
    push(data)
