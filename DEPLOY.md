# PakJobs — Deploy to Render (Free)

## Files in this folder
```
jobboard/
├── app.py            ← Flask app + APScheduler (runs every 6 hrs)
├── monitor_core.py   ← Scraping engine (returns data, no prints)
├── templates/
│   └── index.html    ← Frontend (dark mode, filters, job cards)
├── requirements.txt  ← flask, apscheduler, gunicorn
├── Procfile          ← gunicorn command for Render
└── DEPLOY.md         ← this file
```

---

## Step 1 — Push to GitHub

```bash
# In Terminal, navigate here and init a repo
cd ~/Downloads/jobboard
git init
git add .
git commit -m "Initial commit: PakJobs web app"

# Create a new repo on github.com (name: pakjobs)
# Then push:
git remote add origin https://github.com/YOUR_USERNAME/pakjobs.git
git branch -M main
git push -u origin main
```

---

## Step 2 — Deploy on Render

1. Go to https://render.com → Sign up free (use GitHub login)
2. Dashboard → **New** → **Web Service**
3. Connect your GitHub repo (`pakjobs`)
4. Fill in:
   - **Name**: pakjobs
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --timeout 120 --workers 1`
   - **Instance Type**: Free
5. Click **Create Web Service**

Render will build and deploy. Your app will be live at:
`https://pakjobs.onrender.com` (or similar)

---

## How it works

- On startup the app **immediately** starts a background scrape of LinkedIn, Nestle, and Unilever
- The frontend shows a loading spinner while the first run completes (~3–5 min)
- Once done, jobs appear instantly — no page reload needed (auto-polls every 5s while loading, 60s after)
- Every **6 hours** the monitor re-runs automatically in the background
- Users can filter by **Department** and **City** with zero page reloads

---

## Run locally (for testing)

```bash
cd ~/Downloads/jobboard
python3 app.py
# Open: http://localhost:5000
```

---

## Notes

- Render free tier spins down after 15 min of inactivity — first request after sleep takes ~30s to wake up, then the monitor starts. This is normal.
- The app uses 1 Gunicorn worker (required because the job data lives in memory — multiple workers would each have their own state).
- No database needed — jobs are stored in memory and refreshed every 6 hours.
