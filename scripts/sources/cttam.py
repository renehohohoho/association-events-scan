"""CTTAM: homepage + /event + news category. Usually nothing is listed
(the association announces events mostly by email)."""

from __future__ import annotations

import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from .common import TORONTO, Event, clean_text, classify, get, parse_month_day_year

URLS = [
    "https://cttam.com/",
    "https://cttam.com/event",
    "https://cttam.com/archives/category/news",
]


def scan_cttam(session: requests.Session, today: date, end: date):
    failures: list[str] = []
    events: list[Event] = []
    found_any = False
    for url in URLS:
        try:
            r = get(session, url, timeout=30)
        except Exception as e:  # noqa: BLE001
            failures.append(f"CTTAM {url} 抓取失敗：{e}")
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        # Look for event links with a date in the window.
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not href or "event" not in href.lower() and "news" not in href.lower():
                continue
            title = clean_text(a.get_text(" ", strip=True))
            if len(title) < 8:
                continue
            d = parse_month_day_year(title + " " + a.parent.get_text(" ", strip=True)[:200])
            if d and today <= d <= end:
                include, relevance, _ = classify(title)
                if include:
                    found_any = True
                    events.append(Event(
                        source="cttam", title=title,
                        start=datetime.combine(d, time(12, 0), tzinfo=TORONTO),
                        location="待確認",
                        url=href if href.startswith("http") else "https://cttam.com" + href,
                        price_evidence="", summary=title, relevance=relevance,
                        relevance_reason="CTTAM 活動", status="unpriced",
                        note="CTTAM 頁面未標價，需人工確認是否免費",
                    ))
    if not found_any and not failures:
        failures.append("CTTAM 公開網站無活動公告（僅供備查，非抓取失敗）")
    return events, failures
