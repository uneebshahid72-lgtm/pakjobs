"""
monitor_core.py — Job scraping logic for the web app.
Returns data instead of printing.
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
        "human resource", "human resources", "hr coordinator", "hr associate",
        "hr officer", "hr executive", "hr analyst", "hr generalist",
        "people & culture", "people and culture", "talent acquisition",
        "talent management", "hrbp", "employee engagement", "recruitment",
        "recruiter", "payroll", "workforce planning",
    ],
    "Marketing": [
        "marketing", "brand", "digital marketing", "social media",
        "content marketing", "content writer", "campaign", "trade marketing",
        "corporate communications", "seo", "growth marketing", "advertising",
        "media planning", "copywriter", "email marketing",
    ],
    "Finance & Accounting": [
        "finance", "financial", "accounting", "accountant", "accounts",
        "audit", "auditor", "tax", "treasury", "credit", "fp&a",
        "financial analyst", "financial associate", "financial officer",
        "accounts officer", "accounts executive", "finance executive",
    ],
    "Sales": [
        "sales", "account executive", "sales coordinator", "sales associate",
        "sales executive", "sales officer", "sales analyst", "sales representative",
        "sales development", "inside sales", "field sales",
    ],
    "Supply Chain & Logistics": [
        "supply chain", "logistics", "warehouse", "inventory", "distribution",
        "demand planning", "imports", "exports", "freight", "customs",
        "supply planning", "materials management",
    ],
    "Procurement": [
        "procurement", "purchasing", "sourcing", "vendor management",
        "category management", "buyer", "procurement associate",
        "procurement officer", "procurement executive",
    ],
    "Operations": [
        "management trainee", "graduate trainee", "mto", "future leaders",
        "trainee program", "business operations", "operations associate",
        "operations analyst", "operations coordinator", "operations executive",
        "operations officer", "project coordinator", "project associate",
    ],
    "Business Development": [
        "business development", "partnerships", "alliances",
        "bd associate", "bd coordinator", "bd executive", "bd analyst",
        "growth associate", "expansion",
    ],
    "Information Technology": [
        "software", "developer", "engineer", "devops", "cloud",
        "database", "network", "cyber", "mobile app", "web developer",
        "system admin", "infrastructure", "it support", "technical support",
        "qa engineer", "sqa", "data engineer",
    ],
    "Data & Analytics": [
        "data analyst", "business intelligence", "bi analyst",
        "data analytics", "insights analyst", "reporting analyst",
        "data associate", "analytics associate", "data science",
        "machine learning", "ai analyst",
    ],
    "Customer Service": [
        "customer service", "customer support", "customer experience",
        "customer care", "client relations", "client services",
        "customer success", "customer relations",
    ],
    "Public Relations & Communications": [
        "public relations", "pr manager", "pr executive", "pr associate",
        "corporate communications", "media relations", "communications officer",
        "communications associate", "press",
    ],
    "Legal & Compliance": [
        "legal", "compliance", "regulatory", "attorney", "lawyer",
        "paralegal", "legal associate", "legal officer", "legal executive",
        "compliance officer", "compliance associate",
    ],
    "Research & Development": [
        "research", "r&d", "product development", "innovation",
        "research analyst", "research associate", "research officer",
        "lab", "clinical",
    ],
    "Product Management": [
        "product manager", "product associate", "product analyst",
        "product coordinator", "product owner", "product executive",
    ],
    "Quality Assurance": [
        "quality assurance", "quality control", "qa analyst",
        "quality analyst", "quality coordinator", "qc analyst",
        "quality officer", "quality executive",
    ],
    "Administration": [
        "admin", "administration", "administrative", "office manager",
        "executive assistant", "personal assistant", "secretary",
        "administrative officer", "administrative associate",
    ],
    "Training & Development": [
        "training", "learning & development", "l&d",
        "organizational development", "talent development",
        "learning coordinator", "training coordinator",
    ],
    "Risk Management": [
        "risk analyst", "risk associate", "risk coordinator",
        "risk management", "risk officer", "risk executive",
    ],
    "Strategy & Consulting": [
        "strategy", "consultant", "consulting", "strategic planning",
        "corporate strategy", "management consultant",
        "strategy associate", "strategy analyst",
    ],
}

SENIOR_TITLES = [
    "senior", "sr.", "manager", "head of", "director",
    "vice president", "principal", "chief",
    "team leader", "area manager", "regional manager", "national manager",
    "general manager",
]

_EXACT_SENIOR_RE = re.compile(r'(?<!\w)(?:ceo|cfo|coo|cto|vp|lead|sr)(?!\w)')

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
    if _EXACT_SENIOR_RE.search(t): return True
    if any(kw in t for kw in SENIOR_TITLES): return True
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

def _classify_exp(text):
    """
    Returns one of: '0-1', '1-2', '2-3', '3-4', '4+', 'unclear'
    based on the lowest experience requirement found in the JD.
    """
    if not text or len(text) < 100:
        return "unclear"

    # Good phrases → 0-1
    for phrase in GOOD_EXP_PHRASES:
        if phrase in text:
            return "0-1"

    min_lo = None

    # Range: "1-2 years", "2 to 3 years"
    for m in re.finditer(r'(\d+)\s*(?:[-–]|to)\s*(\d+)\s*year', text):
        if _bypass_ctx(text, m.start()):
            continue
        lo = int(m.group(1))
        if min_lo is None or lo < min_lo:
            min_lo = lo

    # X+ years of experience
    for m in re.finditer(r'(\d+)\s*\+\s*years?\s+(?:of\s+)?(?:\w+\s+){0,3}experience', text):
        if _bypass_ctx(text, m.start()):
            continue
        n = int(m.group(1))
        if min_lo is None or n < min_lo:
            min_lo = n

    # X years of experience
    for m in re.finditer(r'(\d+)\s*years?\s+(?:of\s+)?(?:\w+\s+){0,3}experience', text):
        if _bypass_ctx(text, m.start()):
            continue
        n = int(m.group(1))
        if min_lo is None or n < min_lo:
            min_lo = n

    # experience: X
    for m in re.finditer(r'experience[\s\w]{0,20}?:\s*(\d+)', text):
        if _bypass_ctx(text, m.start()):
            continue
        n = int(m.group(1))
        if min_lo is None or n < min_lo:
            min_lo = n

    if min_lo is None:
        return "unclear"
    if min_lo <= 1:
        return "0-1"
    elif min_lo == 2:
        return "1-2"
    elif min_lo == 3:
        return "2-3"
    elif min_lo == 4:
        return "3-4"
    else:
        return "4+"

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
        # General fresh grad
        "management trainee Pakistan", "graduate trainee Pakistan",
        "MTO Pakistan", "fresh graduate Pakistan", "entry level Pakistan",
        # HR
        "HR associate Pakistan", "HR coordinator Pakistan", "HR officer Pakistan",
        "talent acquisition Pakistan", "recruitment coordinator Pakistan",
        # Marketing
        "marketing associate Pakistan", "marketing coordinator Pakistan",
        "digital marketing Pakistan", "social media Pakistan", "trade marketing Pakistan",
        # Finance
        "finance associate Pakistan", "accounts officer Pakistan",
        "financial analyst Pakistan", "audit associate Pakistan",
        # Sales
        "sales associate Pakistan", "sales coordinator Pakistan",
        "sales executive Pakistan",
        # Supply Chain
        "supply chain Pakistan", "logistics coordinator Pakistan",
        "procurement Pakistan", "demand planning Pakistan",
        # IT & Data
        "software engineer Pakistan", "data analyst Pakistan",
        "business analyst Pakistan", "it associate Pakistan",
        # Operations / Business Development
        "business development Pakistan", "operations associate Pakistan",
        # Customer Service
        "customer service Pakistan", "customer support Pakistan",
        # Strategy / Consulting
        "strategy associate Pakistan", "consultant Pakistan",
        # Top MNCs
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
                       departments, exp_range
    """
    log("Fetching LinkedIn jobs...")
    raw = _get_linkedin_jobs()
    log("Fetching Nestle RSS...")
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

        depts = _detect_dept(title, jd)
        if not depts:
            continue

        exp_range = _classify_exp(jd)

        passed.append({
            "id":          job["id"],
            "title":       title,
            "company":     job["company"],
            "location":    job["location"],
            "link":        job["link"],
            "source":      source,
            "departments": depts,
            "exp_range":   exp_range,
        })

    log(f"Verified jobs: {len(passed)}")
    return {
        "jobs":   passed,
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total":  len(passed),
    }
