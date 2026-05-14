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
        "marketing associate", "marketing coordinator", "marketing executive",
        "marketing officer", "marketing analyst", "brand associate",
        "brand coordinator", "digital marketing", "social media manager",
        "social media coordinator", "content marketing", "content writer",
        "campaign manager", "trade marketing", "seo specialist",
        "growth marketing", "email marketing", "media planner", "copywriter",
    ],
    "Finance & Accounting": [
        "finance associate", "finance executive", "finance officer",
        "finance analyst", "financial analyst", "financial associate",
        "accounts officer", "accounts executive", "accounts associate",
        "accountant", "audit associate", "audit officer", "tax associate",
        "treasury associate", "fp&a analyst",
    ],
    "Sales": [
        "sales associate", "sales coordinator", "sales executive",
        "sales officer", "sales analyst", "sales representative",
        "sales development", "inside sales", "field sales executive",
        "account executive", "sales trainee",
    ],
    "Supply Chain & Logistics": [
        "supply chain associate", "supply chain coordinator", "supply chain analyst",
        "supply chain officer", "logistics coordinator", "logistics associate",
        "logistics officer", "warehouse associate", "inventory associate",
        "distribution coordinator", "demand planning", "supply planning",
        "imports coordinator", "exports coordinator", "freight coordinator",
        "materials management",
    ],
    "Procurement": [
        "procurement associate", "procurement officer", "procurement executive",
        "procurement analyst", "purchasing associate", "purchasing officer",
        "sourcing associate", "sourcing specialist", "vendor management",
        "category associate", "buyer",
    ],
    "Operations": [
        "management trainee", "graduate trainee", "mto",
        "future leaders program", "trainee officer",
        "operations associate", "operations analyst", "operations coordinator",
        "operations executive", "operations officer",
        "project coordinator", "project associate",
    ],
    "Business Development": [
        "business development associate", "business development executive",
        "business development analyst", "bd associate", "bd coordinator",
        "bd executive", "growth associate", "partnerships associate",
    ],
    "Information Technology": [
        "software engineer", "software developer", "web developer",
        "mobile developer", "android developer", "ios developer",
        "frontend developer", "backend developer", "full stack developer",
        "devops engineer", "cloud engineer", "data engineer",
        "network engineer", "system administrator", "it support",
        "technical support", "qa engineer", "sqa engineer",
    ],
    "Data & Analytics": [
        "data analyst", "business analyst", "business intelligence analyst",
        "bi analyst", "data analytics", "insights analyst",
        "reporting analyst", "data associate", "analytics associate",
        "data scientist", "machine learning engineer",
    ],
    "Customer Service": [
        "customer service associate", "customer service executive",
        "customer service officer", "customer support associate",
        "customer experience associate", "customer care associate",
        "client relations associate", "client services associate",
        "customer success associate",
    ],
    "Public Relations & Communications": [
        "public relations associate", "pr associate", "pr executive",
        "corporate communications associate", "communications officer",
        "communications associate", "media relations associate",
    ],
    "Legal & Compliance": [
        "legal associate", "legal officer", "legal executive",
        "compliance associate", "compliance officer", "regulatory associate",
        "paralegal", "legal trainee",
    ],
    "Research & Development": [
        "research associate", "research analyst", "research officer",
        "r&d associate", "product development associate",
        "innovation associate", "lab associate",
    ],
    "Product Management": [
        "product associate", "product analyst", "product coordinator",
        "product executive", "product manager", "product owner",
    ],
    "Quality Assurance": [
        "quality assurance associate", "quality control associate",
        "qa analyst", "quality analyst", "quality coordinator",
        "qc analyst", "quality officer",
    ],
    "Administration": [
        "administrative associate", "administrative officer",
        "admin associate", "office coordinator", "executive assistant",
        "personal assistant", "administrative coordinator",
    ],
    "Training & Development": [
        "training coordinator", "learning & development associate",
        "l&d associate", "training associate", "learning coordinator",
        "talent development associate", "organizational development",
    ],
    "Risk Management": [
        "risk analyst", "risk associate", "risk coordinator",
        "risk officer", "risk executive",
    ],
    "Strategy & Consulting": [
        "strategy associate", "strategy analyst", "strategy consultant",
        "management consultant", "consulting associate",
        "strategic planning associate", "corporate strategy",
    ],
}

# Internship detection — use word boundary to avoid matching "international"
_INTERNSHIP_RE = re.compile(r'(?<!\w)intern(?:ship|s|ed)?\b', re.IGNORECASE)

SENIOR_TITLES = [
    "senior", "sr.", "manager", "head of", "director",
    "vice president", "principal", "chief",
    "team leader", "area manager", "regional manager", "national manager",
    "general manager",
]

_EXACT_SENIOR_RE = re.compile(r'(?<!\w)(?:ceo|cfo|coo|cto|vp|lead|sr)(?!\w)')

BYPASS_CONTEXT = [
    "year of study", "years of study", "year of coursework", "years of coursework",
    "year of undergraduate", "years of undergraduate", "year student",
    "years of college", "year of program", "years of program",
    "academic year", "year of education",
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
    # NOTE: "internship" removed — internship detection is handled by _is_internship()
    # Leaving it here caused any JD mentioning "internship" to short-circuit to "0-1"
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

def _clean(s):
    """Clean HTML entities and whitespace from a string."""
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&lt;", "<", s)
    s = re.sub(r"&gt;", ">", s)
    s = re.sub(r"&#\d+;", "", s)
    return s.strip()

def _is_internship(title):
    """Word-boundary safe internship detection. Won't match 'international'."""
    return bool(_INTERNSHIP_RE.search(title))

def _is_senior(title):
    t = title.lower()
    if _EXACT_SENIOR_RE.search(t): return True
    if any(kw in t for kw in SENIOR_TITLES): return True
    return False

def _detect_dept(title):
    """Match department from job title only — strict, no JD guessing."""
    t = title.lower()
    matched = []
    for dept, kws in TARGET_DEPTS.items():
        if any(kw in t for kw in kws):
            matched.append(dept)
    return matched or None

def _bypass_ctx(text, pos, window=40):
    snippet = text[max(0, pos - window): pos + window]
    return any(bp in snippet for bp in BYPASS_CONTEXT)

def _classify_exp(text):
    """
    Returns '0-1', '1-2', or 'unclear'.
    Jobs requiring 2+ years are returned as 'reject'.
    """
    if not text or len(text) < 100:
        return "unclear"

    # Good phrases → 0-1
    for phrase in GOOD_EXP_PHRASES:
        if phrase in text:
            return "0-1"

    # Use hi for ranges (lo for single mentions) to correctly classify:
    # "0-1 years" → hi=1 → "0-1"
    # "1-2 years" → hi=2 → "1-2"
    # "2-3 years" → hi=3 → reject
    min_hi = None   # tracks the highest year in the lowest range found

    # Range: "1-2 years", "2 to 3 years"
    for m in re.finditer(r'(\d+)\s*(?:[-–]|to)\s*(\d+)\s*year', text):
        if _bypass_ctx(text, m.start()):
            continue
        hi = int(m.group(2))
        if min_hi is None or hi < min_hi:
            min_hi = hi

    # X+ years of experience — treat as minimum = X
    for m in re.finditer(r'(\d+)\s*\+\s*years?\s+(?:of\s+)?(?:\w+\s+){0,3}experience', text):
        if _bypass_ctx(text, m.start()):
            continue
        n = int(m.group(1))
        # X+ means at least X — use X+1 as effective hi so "1+" → hi=2 → "1-2"
        hi = n + 1
        if min_hi is None or hi < min_hi:
            min_hi = hi

    # X years of experience
    for m in re.finditer(r'(\d+)\s*years?\s+(?:of\s+)?(?:\w+\s+){0,3}experience', text):
        if _bypass_ctx(text, m.start()):
            continue
        n = int(m.group(1))
        if min_hi is None or n < min_hi:
            min_hi = n

    # experience: X
    for m in re.finditer(r'experience[\s\w]{0,20}?:\s*(\d+)', text):
        if _bypass_ctx(text, m.start()):
            continue
        n = int(m.group(1))
        if min_hi is None or n < min_hi:
            min_hi = n

    if min_hi is None:
        return "unclear"
    if min_hi <= 1:
        return "0-1"
    elif min_hi <= 2:
        return "1-2"
    else:
        return "reject"   # 3+ years — skip

# ── LinkedIn ──────────────────────────────────────────────────────────────────

def _fetch_listings(keyword, max_pages=10, exp_filter="1%2C2"):
    """Fetch up to max_pages*10 LinkedIn job listings."""
    jobs = []
    for page in range(max_pages):
        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={urllib.parse.quote_plus(keyword)}"
            f"&location=Pakistan&f_E={exp_filter}&start={page*10}"
        )
        html = _curl(url)
        if not html.strip():
            break

        titles     = re.findall(r'class="sr-only">\s*(.*?)\s*</span>', html, re.DOTALL)
        # Try both company patterns and use whichever returns more results.
        # LinkedIn sometimes uses different classes on different result pages.
        companies1 = re.findall(r'class="hidden-nested-link">\s*(.*?)\s*</a>', html, re.DOTALL)
        companies2 = re.findall(r'class="base-search-card__subtitle"[^>]*>\s*(.*?)\s*</[^>]+>', html, re.DOTALL)
        companies  = companies1 if len(companies1) >= len(companies2) else companies2
        locations = re.findall(r'job-search-card__location">\s*(.*?)\s*</span>', html)
        links     = re.findall(r'href="(https://[a-z]+\.linkedin\.com/jobs/view/[^"]+)"', html)
        job_ids   = re.findall(r'data-entity-urn="urn:li:jobPosting:(\d+)"', html)

        if not titles:
            break

        for i, title in enumerate(titles):
            company = _clean(companies[i]) if i < len(companies) else ""
            jobs.append({
                "id":       job_ids[i] if i < len(job_ids) else f"li_{page}_{i}",
                "title":    _clean(title),
                "company":  company if company else "Unknown",
                "location": locations[i].strip() if i < len(locations) else "Pakistan",
                "link":     links[i].split("?")[0] if i < len(links) else "",
                "source":   "LinkedIn",
            })
    return jobs

def _get_linkedin_jobs():
    keywords_regular = [
        # General fresh grad
        "management trainee Pakistan", "graduate trainee Pakistan",
        "MTO Pakistan", "fresh graduate Pakistan", "entry level Pakistan",
        # HR
        "HR associate Pakistan", "HR coordinator Pakistan", "HR officer Pakistan",
        "talent acquisition Pakistan", "recruitment coordinator Pakistan",
        # Marketing
        "marketing associate Pakistan", "marketing coordinator Pakistan",
        "digital marketing Pakistan", "social media Pakistan", "trade marketing Pakistan",
        "brand associate Pakistan",
        # Finance
        "finance associate Pakistan", "accounts officer Pakistan",
        "financial analyst Pakistan", "audit associate Pakistan",
        # Sales
        "sales associate Pakistan", "sales executive Pakistan",
        # Supply Chain
        "supply chain associate Pakistan", "logistics coordinator Pakistan",
        "procurement associate Pakistan", "demand planning Pakistan",
        # IT & Data
        "software engineer Pakistan", "data analyst Pakistan",
        "business analyst Pakistan",
        # Operations / BD
        "business development associate Pakistan", "operations associate Pakistan",
        # Customer Service
        "customer service Pakistan", "customer support Pakistan",
        # Strategy
        "strategy associate Pakistan",
        # Top MNCs
        "Unilever Pakistan graduate", "Nestle Pakistan trainee",
        "P&G Pakistan graduate", "Engro Pakistan graduate",
        "Reckitt Pakistan trainee", "HBL Pakistan graduate",
        "Jazz Pakistan trainee", "Telenor Pakistan graduate",
        "BAT Pakistan trainee", "Colgate Pakistan", "GSK Pakistan graduate",
    ]

    keywords_internship = [
        "internship Pakistan", "intern Pakistan",
        "summer internship Pakistan", "internship 2025 Pakistan",
        "internship 2026 Pakistan", "internship Lahore",
        "internship Karachi", "internship Islamabad",
    ]

    all_jobs = {}

    # Regular entry-level jobs (f_E=1%2C2 = Internship + Entry Level)
    for kw in keywords_regular:
        for job in _fetch_listings(kw, max_pages=10, exp_filter="1%2C2"):
            all_jobs[job["id"]] = job
        time.sleep(0.5)

    # Internship-specific search (f_E=1 = Internship only)
    for kw in keywords_internship:
        for job in _fetch_listings(kw, max_pages=10, exp_filter="1"):
            all_jobs[job["id"]] = job
        time.sleep(0.5)

    return list(all_jobs.values())

# ── Nestle RSS ────────────────────────────────────────────────────────────────

def _get_nestle_jobs():
    feeds = [
        "https://jobdetails.nestle.com/services/rss/job/?locale=en_US&keywords=management+trainee+pakistan",
        "https://jobdetails.nestle.com/services/rss/job/?locale=en_US&keywords=pakistan+graduate+trainee",
        "https://jobdetails.nestle.com/services/rss/job/?locale=en_US&keywords=pakistan+intern",
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
        "https://careers.unilever.com/rss/jobs?keyword=intern&country=Pakistan",
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
      { "jobs": [...], "internships": [...], "run_at": "...", "total": N }
    Each job dict: title, company, location, link, source, departments,
                   exp_range, is_internship
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

        # Internship detection
        internship = _is_internship(title)

        # Experience check — skip if 3+ years (internships bypass this)
        exp_range = _classify_exp(jd)
        if exp_range == "reject" and not internship:
            continue

        if internship:
            exp_range = "0-1"  # internships are always 0-1

        # Department detection — title only for accuracy
        depts = _detect_dept(title)
        if not depts:
            # Fallback: check first 600 chars of JD (200 was too short for multi-word phrases)
            jd_snippet = jd[:600]
            depts = []
            for dept, kws in TARGET_DEPTS.items():
                if any(kw in jd_snippet for kw in kws):
                    depts.append(dept)
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
            "exp_range":    exp_range,
            "is_internship": internship,
        })

    internships = [j for j in passed if j["is_internship"]]
    jobs        = [j for j in passed if not j["is_internship"]]

    log(f"Jobs: {len(jobs)} | Internships: {len(internships)}")
    return {
        "jobs":        jobs,
        "internships": internships,
        "run_at":      datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total":       len(passed),
    }
