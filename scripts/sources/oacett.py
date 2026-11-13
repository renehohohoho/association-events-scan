"""OACETT CPD workshops/webinars page (plain HTML, curl-able).

Each course block: Title / Presented By / Dates / Time / Cost / Format.
Self-study items (no fixed date) go to supplementary resources when free.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup

from .common import (
    TORONTO, Event, clean_text, classify, first_sentence, get,
    parse_month_day_year, parse_time_range,
)

URL = "https://oacett.org/professional-development/cpd-workshops-webinars"

# Dates like "Nov. 28 - 29, 2026" or "Dec. 8, 2026" or "Jan. 01, 2026"
DATE_RANGE_RE = re.compile(
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+"
    r"(\d{1,2})(?:\s*[–—-]\s*(\d{1,2}))?\s*,?\s*(\d{4})?",
    re.I,
)


def _parse_dates(dates_raw: str, today: date) -> tuple[date | None, date | None, bool]:
    """Return (start, end, is_self_study)."""
    m = DATE_RANGE_RE.search(dates_raw)
    if not m:
        return None, None, True
    mon_s, d1, d2, year_s = m.groups()
    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
              "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    mon = months[mon_s.lower()[:3]]
    year = int(year_s) if year_s else today.year
    try:
        start = date(year, mon, int(d1))
    except ValueError:
        return None, None, True
    end = None
    if d2:
        try:
            end = date(year, mon, int(d2))
        except ValueError:
            end = None
    return start, end, False


def _parse_cost(cost_raw: str) -> tuple[str, str]:
    """Return (status, price_text). status: free | paid | unknown."""
    t = cost_raw.lower()
    if "free" in t or re.search(r"\$0(\.00)?\b", t):
        return "free", cost_raw.strip()
    m = re.search(r"\$[\d,]+(?:\.\d{2})?", cost_raw)
    if m:
        return "paid", m.group(0)
    return "unknown", cost_raw.strip()


def scan_oacett(session: requests.Session, today: date, end: date):
    failures: list[str] = []
    events: list[Event] = []
    excluded: list[dict] = []
    supplementary: list[dict] = []
    stats = {"listed": 0, "free": 0, "paid": 0}

    try:
        r = get(session, URL, timeout=45)
    except Exception as e:  # noqa: BLE001
        failures.append(f"OACETT 頁面抓取失敗：{e}")
        return events, excluded, supplementary, failures, stats

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text("\n", strip=True)
    # Split into course blocks on "Presented By:"; the title is the last
    # non-empty line of the preceding chunk.
    parts = re.split(r"\nPresented By:\n", text)
    stats["listed"] = len(parts) - 1
    for i, block in enumerate(parts[1:], start=1):
        prev_lines = [ln.strip() for ln in parts[i - 1].split("\n") if ln.strip()]
        title = prev_lines[-1] if prev_lines else ""
        # drop trailing category headers (e.g. "Technology Report Writing Workshops")
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        fields: dict[str, str] = {}
        key = None
        for ln in lines:
            if ln in ("Dates:", "Time:", "Cost:", "Format:"):
                key = ln[:-1].lower()
                fields[key] = ""
            elif key:
                fields[key] = (fields[key] + " " + ln).strip()
                key = None
        dates_raw = fields.get("dates", "")
        start_d, end_d, self_study = _parse_dates(dates_raw, today)
        cost_raw = fields.get("cost", "")
        status, price = _parse_cost(cost_raw)
        fmt = fields.get("format", "")
        include, relevance, _reason = classify(title, fields.get("dates", "") + " " + fmt)
        # Self-study / no-date items: supplementary only when free & relevant
        if self_study or start_d is None:
            if status == "free" and include:
                supplementary.append({"title": title, "price": price or "免費",
                                      "url": URL, "note": "自學課程，無排定日期"})
            continue
        if not (today <= start_d <= end):
            continue
        if status == "free":
            if not include:
                continue
            stats["free"] += 1
            start_dt, end_dt = parse_time_range(fields.get("time", ""), start_d)
            events.append(Event(
                source="oacett", title=title,
                start=start_dt or datetime.combine(start_d, datetime.min.time(), tzinfo=TORONTO),
                end=end_dt, location="線上" if "virtual" in fmt.lower() else fmt,
                url=URL, price_evidence=f"Cost: {cost_raw}",
                summary=first_sentence(title), relevance=relevance,
                relevance_reason="OACETT 課程", status="free",
            ))
        elif status == "paid":
            stats["paid"] += 1
            if include:
                excluded.append({"title": title, "date": start_d.strftime("%m/%d"),
                                 "price": price, "reason": "付費"})
        # unknown cost: not listed (cannot confirm free)
    return events, excluded, supplementary, failures, stats
