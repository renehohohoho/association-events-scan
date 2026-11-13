"""Shared helpers for the weekly association + library events scan.

All sources are public; no login is ever attempted and nothing is ever
registered for. See docs/TASK-SPEC.md for the full spec.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

TORONTO = ZoneInfo("America/Toronto")
UTC = ZoneInfo("UTC")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Event model
# ---------------------------------------------------------------------------

@dataclass
class Event:
    source: str            # asq | oacett | ospe | cttam | tpl | mississauga | lpl
    title: str
    start: datetime        # timezone-aware, America/Toronto
    end: datetime | None = None
    location: str = ""     # e.g. "線上 (Zoom)" / "實體，Toronto Reference Library"
    url: str = ""
    price_evidence: str = ""   # verbatim price text from the detail page
    summary: str = ""      # one-line description
    relevance: str = "medium"  # high | medium | low
    relevance_reason: str = ""
    status: str = "free"   # free | member_pending | paid | unpriced
    note: str = ""         # extra note (deadline, registration cutoff, ...)
    topic: str = ""        # library topic bucket: AI／科技 | 健康 | 文學／寫作／閱讀 | 職涯發展 | 工程／建築

    def key(self) -> str:
        return self.url or f"{self.source}|{self.title}|{self.start.date().isoformat()}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start"] = self.start.isoformat()
        d["end"] = self.end.isoformat() if self.end else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        d = dict(d)
        d["start"] = datetime.fromisoformat(d["start"])
        d["end"] = datetime.fromisoformat(d["end"]) if d.get("end") else None
        return cls(**d)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    return s


def get(session: requests.Session, url: str, timeout: int = 30, tries: int = 3, **kwargs):
    """GET with retries on transient failures. Raises on final failure."""
    last = None
    for i in range(tries):
        try:
            r = session.get(url, timeout=timeout, **kwargs)
            r.raise_for_status()
            return r
        except requests.RequestException as e:  # noqa: BLE001 - re-raised after retries
            last = e
            time.sleep(2 * (i + 1))
    raise last


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

def scan_window(today: date | None = None) -> tuple[date, date]:
    """6-week window: today .. today + 42 days."""
    today = today or datetime.now(TORONTO).date()
    return today, today + timedelta(days=42)


TZ_ABBR = {
    "ET": "America/Toronto", "EST": "America/Toronto", "EDT": "America/Toronto",
    "CT": "America/Chicago", "CST": "America/Chicago", "CDT": "America/Chicago",
    "MT": "America/Denver", "MST": "America/Denver", "MDT": "America/Denver",
    "PT": "America/Los_Angeles", "PST": "America/Los_Angeles", "PDT": "America/Los_Angeles",
    "AT": "America/Halifax", "AST": "America/Halifax", "ADT": "America/Halifax",
    "UTC": "UTC", "GMT": "UTC",
}


def parse_asq_when(text: str) -> tuple[datetime, datetime | None] | None:
    """Parse 'When: Thu, Nov 12, 2026 from 06:00 PM to 08:00 PM (MT)'.

    Returns (start, end) converted to America/Toronto, or None.
    """
    m = re.search(
        r"(?:When:\s*)?([A-Za-z]{3}),?\s+([A-Za-z]{3})\.?\s+(\d{1,2}),\s+(\d{4})"
        r"\s+from\s+(\d{1,2}:\d{2}\s*[AP]M)\s+to\s+(\d{1,2}:\d{2}\s*[AP]M)"
        r"(?:\s*\(([A-Za-z]{2,4})\))?",
        text,
    )
    if not m:
        return None
    _dow, mon, day, year, t1, t2, abbr = m.groups()
    tzname = TZ_ABBR.get((abbr or "ET").upper(), "America/Toronto")
    tz = ZoneInfo(tzname)
    fmt = "%b %d %Y %I:%M %p"
    try:
        start = datetime.strptime(f"{mon} {day} {year} {t1}", fmt).replace(tzinfo=tz)
        end = datetime.strptime(f"{mon} {day} {year} {t2}", fmt).replace(tzinfo=tz)
    except ValueError:
        return None
    if end <= start:  # crosses midnight
        end += timedelta(days=1)
    return start.astimezone(TORONTO), end.astimezone(TORONTO)


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_month_day_year(text: str, default_year: int | None = None) -> date | None:
    """Parse 'Nov. 28, 2026' / 'November 25, 2026' / 'Nov 13'."""
    m = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})(?:\s*,\s*(\d{4}))?",
        text,
        re.I,
    )
    if not m:
        return None
    mon = _MONTHS[m.group(1).lower()[:3]]
    day = int(m.group(2))
    year = int(m.group(3)) if m.group(3) else (default_year or datetime.now(TORONTO).year)
    try:
        return date(year, mon, day)
    except ValueError:
        return None


def parse_time_range(text: str, day: date, tz: ZoneInfo = TORONTO):
    """Parse '09:00 am - 12:00 pm' / '6:00pm - 8:00pm' / '12:00pm to 1:00pm' on a given day."""
    m = re.search(
        r"(\d{1,2}:\d{2}\s*[ap]\.?m\.?)\s*(?:[–—-]|\bto\b)\s*(\d{1,2}:\d{2}\s*[ap]\.?m\.?)",
        text,
        re.I,
    )
    if not m:
        m = re.search(r"(\d{1,2}\s*[ap]\.?m\.?)\s*(?:[–—-]|\bto\b)\s*(\d{1,2}\s*[ap]\.?m\.?)", text, re.I)
    if not m:
        return None, None

    def _to_time(s: str):
        s = s.replace(".", "").strip().upper()
        s = re.sub(r"(\d)\s*([AP])M$", r"\1 \2M", s)  # "6:00PM" -> "6:00 PM"
        for fmt in ("%I:%M %p", "%I %p"):
            try:
                return datetime.strptime(s, fmt).time()
            except ValueError:
                continue
        return None

    t1, t2 = _to_time(m.group(1)), _to_time(m.group(2))
    if not t1 or not t2:
        return None, None
    start = datetime.combine(day, t1, tzinfo=tz)
    end = datetime.combine(day, t2, tzinfo=tz)
    if end <= start:
        end += timedelta(days=1)
    return start, end


# ---------------------------------------------------------------------------
# Price evidence
# ---------------------------------------------------------------------------

FREE_PATTERNS = [
    r"cost:\s*free",
    r"free and open to all",
    r"free to everyone",
    r"free to attend",
    r"free registration",
    r"\bfree\b.{0,20}registration",
    r"no charge",
    r"no cost",
    r"there is no charge",
    r"web-based connection\s*[-–]\s*\$0",
    r"cost:\s*\$0",
    r"\$0\.00",
]
PAID_PATTERN = re.compile(r"\$\s?(\d[\d,]*(?:\.\d{2})?)")


def extract_price_evidence(text: str) -> tuple[str, str, str]:
    """Return (status, evidence, paid_amount).

    status: 'free' | 'paid' | 'unpriced'. evidence is a verbatim snippet.
    Member-free with a non-member price counts as free (Rene is a member
    of ASQ/OACETT/OSPE/CTTAM); the evidence notes that.
    """
    flat = re.sub(r"\s+", " ", text)
    # free evidence first (verbatim snippet around the match)
    for pat in FREE_PATTERNS:
        m = re.search(pat, flat, re.I)
        if m:
            s = max(0, m.start() - 40)
            e = min(len(flat), m.end() + 60)
            return "free", flat[s:e].strip(), ""
    # any dollar amount?
    amounts = []
    for m in PAID_PATTERN.finditer(flat):
        try:
            amounts.append(float(m.group(1).replace(",", "")))
        except ValueError:
            continue
    positive = [a for a in amounts if a > 0]
    if positive:
        m = PAID_PATTERN.search(flat)
        s = max(0, m.start() - 40)
        e = min(len(flat), m.end() + 60)
        return "paid", flat[s:e].strip(), f"${min(positive):,.2f}".rstrip("0").rstrip(".")
    if amounts:  # only $0 amounts seen
        return "free", "$0", ""
    return "unpriced", "", ""


# ---------------------------------------------------------------------------
# Relevance filtering (TASK-SPEC.md 篩選條件)
# ---------------------------------------------------------------------------

# Always exclude: civil/structural/water, children's activities, basic finance.
EXCLUDE_PATTERNS = [
    r"\bcivil\b.{0,20}(engineering|infrastructure|design)",
    r"\bstructural\b",
    r"\bwater\s*(treatment|resources|wastewater|well)",
    r"\bwastewater\b",
    r"\bpavement\b",
    r"\bbridge\b.{0,15}(design|engineering|inspection)",
    r"\broadway\b",
    r"children|kids?\b.{0,10}(program|story|craft|activity|club)",
    r"\btoddler\b",
    r"\bbaby\b",
    r"\bpreschool\b",
    r"\bstorytime\b",
    r"retirement (planning|reset|income)",
    r"\binvesting 101\b",
    r"\btax basics\b",
    r"\bbudgeting basics\b",
    r"\bcomic expo\b",
    r"\bmovie (night|screening)\b",
    r"after school",
    r"\bteens?\b",
    r"\byouth\b",
    r"land development",
    r"distribution network",
    r"resilient infrastructure",
    r"climate.{0,25}infrastructure",
    r"\bcities\b",
    r"geotechnical",
    r"\bmunicipal\b",
    r"stormwater",
    r"\bsewer",
    r"transportation",
    r"land use",
    r"water.{0,15}(distribution|quality)",
]

HIGH_PATTERNS = [
    r"medical device", r"medtech", r"biomed", r"iso 13485", r"iso 9001",
    r"quality management", r"\bqms\b", r"reliability engineer", r"six sigma",
    r"\bcapa\b", r"clinical (research|data|trial)", r"health data",
    r"ai governance", r"quality 4\.0", r"hira", r"risk management",
    r"fda|health canada|regulatory.{0,15}medical",
]
MEDIUM_PATTERNS = [
    r"\bai\b", r"artificial intelligence", r"machine learning", r"deep learning",
    r"\bdata\b", r"robot", r"automat", r"engineer", r"manufacturing",
    r"\bprocess\b", r"systems?", r"leadership", r"career", r"resume|résumé",
    r"job search", r"interview", r"writing", r"author", r"book club",
    r"reading", r"literature", r"health", r"wellness", r"science",
    r"diabetes", r"dementia", r"quality", r"iso\b", r"audit", r"metrology",
    r"calibration", r"lean\b", r"phishing", r"cyber", r"research",
    r"innovation", r"python", r"programming", r"coding",
    r"p\.?eng\b", r"\bpeo\b", r"\bcba\b", r"licen[cs]e",
    r"antimicrobial", r"antibiotic", r"microbi", r"\bamr\b",
    r"monte carlo", r"operational readiness",
]
SOCIAL_ONLY_PATTERNS = [
    r"coffee talk", r"networking (event|mixer|night)", r"holiday party",
    r"trivia night", r"gala\b", r"awards gala", r"social\b.{0,10}event",
]

ONLINE_MARKERS = ["online", "virtual", "webex", "zoom", "web-based", "livestream", "live stream",
                  "線上", "虛擬", "網上"]
ONTARIO_PLACES = [
    "toronto", "mississauga", "oakville", "hamilton", "ottawa", "london",
    "waterloo", "kitchener", "markham", "vaughan", "brampton", "oshawa",
    "burlington", "milton", "etobicoke", "scarborough", "north york",
    "ontario", "gta",
]


def classify(title: str, desc: str = "") -> tuple[bool, str, str]:
    """Return (include, relevance, reason)."""
    text = f"{title} {desc}".lower()
    # Generic unnamed book clubs ("Book Club", "Afternoon Book Club",
    # "Mimico Book Club") name no book or theme; only themed clubs
    # (usually with a ":" subtitle naming the book) are listed.
    if re.match(r"^(?:\w+\s+){0,2}book clubs?\s*$", title.strip().lower()):
        return False, "", "排除：未指名書籍的一般讀書會"
    for pat in EXCLUDE_PATTERNS:
        if re.search(pat, text):
            return False, "", f"排除：{pat}"
    for pat in SOCIAL_ONLY_PATTERNS:
        if re.search(pat, text):
            return False, "", "排除：社交／聯誼性質"
    for pat in HIGH_PATTERNS:
        if re.search(pat, text):
            return True, "high", "高相關"
    for pat in MEDIUM_PATTERNS:
        if re.search(pat, text):
            return True, "medium", "主題相關"
    return False, "", "主題不符"


def location_ok(location: str) -> tuple[bool, str]:
    """Online, or in-person in Toronto/Ontario, qualifies for the main list."""
    loc = location.lower()
    if any(m in loc for m in ONLINE_MARKERS):
        return True, "線上"
    if any(p in loc for p in ONTARIO_PLACES):
        return True, "安大略實體"
    if loc.strip() == "":
        return True, ""  # unknown: let the caller decide (usually online)
    return False, "實體在外州／外省"


def clean_text(s: str) -> str:
    s = re.sub(r"\\n|\\t|\\r", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def first_sentence(text: str, limit: int = 120) -> str:
    """One-line summary from a description: first sentence, truncated."""
    text = clean_text(text)
    # strip leading boilerplate
    m = re.search(r"[.!?。]\s", text)
    s = text[: m.end()].strip() if m and m.end() > 20 else text[:limit]
    if len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0] + "…"
    return s
