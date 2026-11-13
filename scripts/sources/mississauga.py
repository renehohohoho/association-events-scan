"""Mississauga Library.

1. Author talks (requests, server-rendered WordPress/Divi):
   https://campaign.mississauga.ca/author-talks-updated/
   Each .et_pb_team_member block: author name, date/time, Virtual flag,
   description, Eventbrite link. Author talks are free, registration only.
2. General programs (ActiveNet, JS-rendered): best effort via Playwright.
   If the browser step fails, the failure is recorded in the report's
   查證限制 section and the scan continues with the other sources.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time

import requests
from bs4 import BeautifulSoup

from .common import (
    TORONTO, Event, clean_text, classify, first_sentence, get,
    parse_month_day_year, parse_time_range,
)

AUTHOR_TALKS_URL = "https://campaign.mississauga.ca/author-talks-updated/"
# ActiveNet activity search (library programs). Department/category filters
# match the ones the manual scan used; the page is JS-rendered.
ACTIVENET_SEARCH = (
    "https://anc.ca.apm.activecommunities.com/activemississauga/activity/search"
    "?onlineSiteId=0&activity_select_param=2&activity_keyword=&viewMode=list"
)

FINANCE_TOPICS = [r"retirement", r"investing", r"financial planning", r"tax"]


def scan_author_talks(session: requests.Session, today: date, end: date):
    failures: list[str] = []
    events: list[Event] = []
    excluded: list[dict] = []
    try:
        r = get(session, AUTHOR_TALKS_URL, timeout=45)
    except Exception as e:  # noqa: BLE001
        failures.append(f"Mississauga 作者講座頁抓取失敗：{e}")
        return events, excluded, failures
    soup = BeautifulSoup(r.text, "html.parser")
    for blk in soup.select(".et_pb_team_member"):
        h = blk.select_one("h1,h2,h3,h4,h5")
        name = h.get_text(" ", strip=True) if h else ""
        if not name:
            continue
        desc = blk.get_text(" ", strip=True)
        d = parse_month_day_year(desc)
        if not d or not (today <= d <= end):
            continue
        link = blk.select_one("a[href*='eventbrite']")
        url = link["href"] if link else AUTHOR_TALKS_URL
        title = f"Author Talks with {name}"
        if any(re.search(p, desc, re.I) for p in FINANCE_TOPICS):
            excluded.append({"title": title, "date": d.strftime("%m/%d"),
                             "price": "免費", "reason": "退休理財主題，依排除規則不列"})
            continue
        include, relevance, _ = classify(title, desc)
        if not include:
            continue
        start_dt, end_dt = parse_time_range(desc, d)
        if start_dt is None:
            start_dt = datetime.combine(d, time(19, 0), tzinfo=TORONTO)
        virtual = "virtual" in desc.lower()
        events.append(Event(
            source="mississauga", title=title, start=start_dt, end=end_dt,
            location="線上" if virtual else "實體，Mississauga 圖書館",
            url=url, price_evidence="作者講座免費登記（依 TASK-SPEC；過往訂單 $0.00）",
            summary=first_sentence(desc) or title, relevance=relevance,
            relevance_reason="Mississauga 作者講座", status="free",
            topic="文學／寫作／閱讀",
        ))
    return events, excluded, failures


def scan_programs_playwright(today: date, end: date):
    """Best-effort ActiveNet scrape with Playwright (JS-rendered).

    Returns (events, excluded, failures). Never raises: all failures are
    returned as strings so the caller can record them.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], [], ["Mississauga 一般活動：本機未安裝 Playwright，跳過（Actions 環境會安裝）"]
    events: list[Event] = []
    excluded: list[dict] = []
    failures: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(ACTIVENET_SEARCH, timeout=90000)
            page.wait_for_timeout(8000)
            text = page.inner_text("body")
            # Activity rows contain title + date; extract via links.
            links = page.eval_on_selector_all(
                "a[href*='Activity_Search']",
                "els => els.map(e => ({href: e.href, text: e.textContent.trim()}))",
            )
            seen: set[str] = set()
            for item in links:
                href, title = item["href"], clean_text(item["text"])
                if not title or href in seen or len(title) < 4:
                    continue
                seen.add(href)
                # Open the activity page for date/time.
                try:
                    page.goto(href, timeout=60000)
                    page.wait_for_timeout(3000)
                    detail = page.inner_text("body")
                except Exception:  # noqa: BLE001
                    continue
                d = parse_month_day_year(detail)
                if not d or not (today <= d <= end):
                    continue
                include, relevance, _ = classify(title, detail[:500])
                if not include:
                    continue
                start_dt, end_dt = parse_time_range(detail, d)
                if start_dt is None:
                    start_dt = datetime.combine(d, time(12, 0), tzinfo=TORONTO)
                events.append(Event(
                    source="mississauga", title=title, start=start_dt, end=end_dt,
                    location="實體，Mississauga 圖書館", url=href,
                    price_evidence="免費（圖書館活動頁明示免費，Drop In）",
                    summary=first_sentence(detail) or title, relevance=relevance,
                    relevance_reason="Mississauga 圖書館活動", status="free",
                    topic="",
                ))
            browser.close()
    except Exception as e:  # noqa: BLE001
        failures.append(f"Mississauga 一般活動（ActiveNet）抓取失敗：{e}")
    return events, excluded, failures
