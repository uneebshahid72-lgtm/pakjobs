"""
monitor_core.py — Job scraping logic for the web app.
Extracted from pakistan_job_monitor.py. Returns data instead of printing.
"""

import subprocess
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
TARGET_CITIES = ["lahore", "islamabad", "karachi"]

TARGET_DEPTS = {
    "Human Resources": [
        "human resource", "human resources", "hr ", "hr coordinator", "hr associate",
        "hr officer", "hr executive", "hr analyst", "hr generalist",
        "people & culture", "people and culture", "talent acquisition", "talent management",
        "hrbp", "employee engagement", "recruitment", "recruiter",
        "learning & development", "l&d", "payroll", "workforce planning",
    ],
    "Supply Chain": [
        "supply chain", "logistics", "procurement", "warehouse", "inventory",
        "distribution", "demand planning", "imports", "exports",
        "freight", "customs", "sourcing", "vendor management", "purchasing",
        "supply planning", "materials management", "category management",
    ],
    "Marketing": [
        "marketing", "brand", "digital marketing", "social media",
        "content marketing", "content writer", "campaign", "trade marketing",
        "corporate communications", "public relations", "pr manager", "pr executive",
        "seo", "growth marketing", "advertising", "media planning",
        "copywriter", "email marketing",
    ],
    "Operations": [
        "management trainee", "graduate trainee", "management trainee officer",
        "mto", "future leaders", "trainee program", "business operations",
        "business development", "operations associate", "operations analyst",
        "operations coordinator", "operations executive", "operations officer",
        "project coordinator", "project associate",
    ],
}

SENIOR_TITLES = [
    "senior", "sr.", "manager", "head of", "director",
    "vice president", "principal", "chief",
    "team leader", "area manager", "regional manager", "national manager",
    "general manager",
]

EXCLUDED_TITLES = [
    "internship", "nesternship",
    "software", "developer", "engineer", "engineering", "coding", "programmer",
    "backend", "frontend", "full stack", "fullstack", "devops", "cloud",
    "data science", "machine learning", "artificial intelligence", "ai engineer",
    "cyber", "network", "database", "quality assurance", "sqa",
    "web developer", "information technology",
    "technical support", "tech support", "system admin", "infrastructure",
    "finance", "financial", "accounting", "accountant", "accounts", "audit",
    "auditor", "tax", "treasury", "credit", "investment", "equity", "banking",
    "risk analyst", "financial analyst", "finance associate", "fp&a",
    "user experience", "user interface", "graphic design",
    "graphic designer", "product designer", "visual design", "motion graphic",
    "ui/ux", "ux/ui", "interaction design",
    "legal", "compliance", "regulatory", "attorney", "lawyer", "paralegal",
    "doctor", "nurse", "medical", "pharmacist", "teacher", "lecturer",
    "customer service", "customer support", "call center", "bpo",
]

_EXACT_SENIOR_RE  = re.compile(r'(?<!\w)(?:ceo|cfo|coo|cto|vp|lead|sr)(?!\w)')
_EXACT_EXCLUDED_RE = re.compile(r'(?<!\w)(?:intern|qa|ux|ui|it)(?!\w)')

BAD_EXP_PHRASES = [
    "1-3 year", "1 to 3 year", "1-2 year", "1 to 2 year",
    "2-3 year", "2 to 3 year",
    "2 years", "3 years", "4 years", "5 years", "6 years", "7 years", "8 years", "10 years",
    "2+ year", "3+ year", "4+ year", "5+ year",
    "minimum 2", "minimum 3", "minimum 4", "minimum 5",
    "at least 2", "at least 3", "at least 4", "at least 5",
    "more than 1 year", "over 1 year", "above 1 year",
]

BYPASS_CONTEXT = [
    "year of study", "years of study", "year of coursework", "years of coursework",
    "year of undergraduate", "years of undergraduate", "year student", "years of college",
    "year of program", "years of program", "academic year", "year of education",
    "years ago", "year ago", "in the past", "for the past", "over the past",
    "in the last", "for the last", "over the last",
    "founded", "established", "since our", "we have been",
    "operating for", "serving for", "years of operation",
]

GOOD_EXP_PHRASES = [
    "0-1 year", "0 to 1 year", "no experience", "no prior experience",
    "fresh graduate", "fresh grad", "recent graduate", "newly graduated",
    "entry level", "entry-level", "0 year", "less than 1 year",
    "up to 1 year", "within 1 year", "management trainee",
    "graduate program", "trainee program", "final year student",
    "new graduate", "no work experience",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _curl(url):
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "20",
             "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
             url],
            capture_output=True, text=True
        )
        return result.stdout or ""
    except Exception:
        return ""

def _html_to_text(html):
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).lower()

def _is_senior(title):
    t = title.lower()
    if _EXACT_SENIOR_RE.search(t):  return True
    if _EXACT_EXCLUDED_RE.search(t): return True
    if any(kw in t for kw in SENIOR_TITLES):   return True
    if any(kw in t for kw in EXCLUDED_TITLES): return True
    return False

def _detect_dept(title, jd_snippet=""):
    t = title.lower()
    s = jd_snippet[:300].lower()
    matched = []
    for dept, kws in TARGET_DEPTS.items():
        if any(kw in t for kw in kws):
            matched.append(dept)
        elif s and any(kw in s for kw in kws):
            matched.append(dept)
    return matched or None

def _bypass_ctx(text, pos, window=40):
    snippet = text[max(0, pos - window): pos + window]
    return any(bp in snippet for bp in BYPASS_CONTEXT)

def _check_exp(text):
    if not text or len(text) < 100:
        return "unclear"
    for phrase in BAD_EXP_PHRASES:
        idx = text.find(phrase)
        while idx != -1:
            if not _bypass_ctx(text, idx):
                return "reject"
            idx = text.find(phrase, idx + 1)
    for m in re.finditer(r"(\d+)\s*(?:[-–]|to)\s*(\d+)\s*year", text):
        lo, hi = int(m.group(1)), int(m.group(2))
        if (lo >= 2 or hi >= 2) and not _bypass_ctx(text, m.start()):
            return "reject"
    for m in re.finditer(r"(\d+)\s*\+?\s*years?\s+(?:of\s+)?(?:\w+\s+){0,3}experience", text):
        if int(m.group(1)) >= 2 and not _bypass_ctx(text, m.start()):
            return "reject"
    for m in re.finditer(r"experience[\s\w]{0,20}?:\s*(\d+)", text):
        if int(m.group(1)) >= 2 and not _bypass_ctx(text, m.start()):
            return "reject"
    if any(p in text for p in GOOD_EXP_PHRASES):
        return "ok"
    return "unclear"

# ── LinkedIn ──────────────────────────────────────────────────────────────────

def _fetch_listings(keyword, max_pages=5):
    jobs = []
    for page in range(max_pages):
        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={urllib.parse.quote_plus(keyword)}&location=Pakistan&f_E=1%2C2&start={page*10}"
        )
        html = _curl(url)
        if not html.strip():
            break
        titles    = re.findall(r'class="sr-only">\s*(.*?)\s*</span>', html, re.DOTALL)
        companies = re.findall(r'class="hidden-nested-link">\s*(.*?)\s*</a>', html, re.DOTALL)
        locations = re.findall(r'job-search-card__location">\s*(.*?)\s*</span>', html)
        links     = re.findall(r'href="(https://[a-z]+\.linkedin\.com/jobs/view/[^"]+)"', html)
        job_ids   = re.findall(r'data-entity-urn="urn:li:jobPosting:(\d+)"', html)
        if not titles:
            break
        for i, title in enumerate(titles):
            jobs.append({
                "id":       job_ids[i] if i < len(job_ids) else f"li_{page}_{i}",
                "title":    re.sub(r"&amp;", "&", title.strip()),
                "company":  companies[i].strip() if i < len(companies) else "Unknown",
                "location": locations[i].strip() if i < len(locations) else "Pakistan",
                "link":     links[i].split("?")[0] if i < len(links) else "",
                "source":   "LinkedIn",
            })
    return jobs

def _get_linkedin_jobs():
    keywords = [
        "management trainee Pakistan", "graduate trainee Pakistan",
        "MTO Pakistan", "fresh graduate Pakistan", "entry level Pakistan",
        "HR associate Pakistan", "HR coordinator Pakistan", "HR officer Pakistan",
        "HR executive Pakistan", "talent acquisition Pakistan",
        "recruitment coordinator Pakistan",
        "marketing associate Pakistan", "marketing coordinator Pakistan",
        "marketing executive Pakistan", "brand associate Pakistan",
        "digital marketing Pakistan", "social media Pakistan", "trade marketing Pakistan",
        "supply chain Pakistan", "supply chain associate Pakistan",
        "logistics coordinator Pakistan", "procurement Pakistan",
        "demand planning Pakistan", "warehouse Pakistan", "sourcing Pakistan",
        "business development Pakistan", "operations associate Pakistan",
        "Unilever Pakistan graduate", "Nestle Pakistan trainee",
        "P&G Pakistan graduate", "Engro Pakistan graduate",
        "Reckitt Pakistan trainee", "HBL Pakistan graduate",
        "Jazz Pakistan trainee", "Telenor Pakistan graduate",
        "BAT Pakistan trainee", "Colgate Pakistan", "GSK Pakistan graduate",
    ]
    all_jobs = {}
    for kw in keywords:
        for job in _fetch_listings(kw, max_pages=5):
            all_jobs[job["id"]] = job
        time.sleep(0.5)
    return list(all_jobs.values())

# ── Nestle RSS ────────────────────────────────────────────────────────────────

def _get_nestle_jobs():
    feeds = [
        "https://jobdetails.nestle.com/services/rss/job/?locale=en_US&keywords=management+trainee+pakistan",
        "https://jobdetails.nestle.com/services/rss/job/?locale=en_US&keywords=pakistan+graduate+trainee",
    ]
    seen_ids, jobs = set(), []
    for url in feeds:
        xml = _curl(url)
        if not xml.strip(): continue
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            continue
        channel = root.find("channel")
        if not channel: continue
        for item in channel.findall("item"):
            title  = (item.findtext("title") or "").strip()
            link   = (item.findtext("link") or "").strip()
            job_id = link.split("/")[-2] if "/" in link else link
            if job_id and job_id not in seen_ids:
                seen_ids.add(job_id)
                jobs.append({
                    "id": job_id, "title": title,
                    "company": "Nestle Pakistan", "location": "Pakistan",
                    "link": link, "source": "Nestle",
                })
    return jobs

# ── Unilever RSS ──────────────────────────────────────────────────────────────

def _get_unilever_jobs():
    feeds = [
        "https://careers.unilever.com/rss/jobs?country=Pakistan",
        "https://careers.unilever.com/rss/jobs?keyword=trainee&country=Pakistan",
    ]
    seen_ids, jobs = set(), []
    for url in feeds:
        xml = _curl(url)
        if not xml.strip(): continue
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            continue
        channel = root.find("channel")
        if not channel: continue
        for item in channel.findall("item"):
            title  = (item.findtext("title") or "").strip()
            link   = (item.findtext("link") or "").strip()
            id_m   = re.search(r'/(\d+)/', link)
            job_id = f"ul_{id_m.group(1)}" if id_m else f"ul_{link}"
            if job_id not in seen_ids:
                seen_ids.add(job_id)
                jobs.append({
                    "id": job_id, "title": title,
                    "company": "Unilever Pakistan", "location": "Pakistan",
                    "link": link, "source": "Unilever",
                })
    return jobs

# ── Main entry point ──────────────────────────────────────────────────────────

def run_monitor(log=print):
    """
    Run the full job monitor. Returns a dict:
      { "jobs": [...], "run_at": "2026-05-14 15:30", "total": N }
    Each job dict has: title, company, location, link, source,
                       departments, exp_verified, is_new (always False here)
    """
    log("Fetching LinkedIn jobs...")
    raw = _get_linkedin_jobs()
    log(f"Fetching Nestle RSS...")
    raw += _get_nestle_jobs()
    log("Fetching Unilever RSS...")
    raw += _get_unilever_jobs()

    unique = list({j["id"]: j for j in raw}.values())
    log(f"Total unique raw: {len(unique)}")

    passed = []
    li_count = 0

    for job in unique:
        title  = job["title"]
        source = job.get("source", "LinkedIn")

        if _is_senior(title):
            continue

        # City filter for LinkedIn
        if source == "LinkedIn":
            loc = job.get("location", "").lower()
            if not any(city in loc for city in TARGET_CITIES):
                continue

        # Fetch JD
        if source == "LinkedIn":
            li_count += 1
            if li_count > 1 and li_count % 10 == 0:
                time.sleep(1)
            jd = _html_to_text(_curl(
                f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job['id']}"
            ))
        else:
            jd = _html_to_text(_curl(job["link"]))

        # City check for RSS sources
        if source in ("Nestle", "Unilever"):
            if not any(city in jd for city in TARGET_CITIES):
                continue

        verdict = _check_exp(jd)
        if verdict == "reject":
            continue

        depts = _detect_dept(title, jd)
        if not depts:
            continue

        passed.append({
            "id":           job["id"],
            "title":        title,
            "company":      job["company"],
            "location":     job["location"],
            "link":         job["link"],
            "source":       source,
            "departments":  depts,
            "exp_verified": (verdict == "ok"),
        })

    log(f"Verified jobs: {len(passed)}")
    return {
        "jobs":   passed,
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total":  len(passed),
    }
