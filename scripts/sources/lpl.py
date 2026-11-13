"""London Public Library, online events only.

programs.lpl.ca is a Communico JS widget (elements.communico.co); the
listing is not server-rendered, so this source needs a real browser.
Best effort via Playwright: render the listing, read the event cards,
keep only Virtual/Online ones. Failures are returned (never raised) so
the scan records them in 查證限制 instead of silently skipping LPL.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time

from .common import TORONTO, Event, clean_text, classify, first_sentence, parse_month_day_year

PROGRAMS_URL = "https://programs.lpl.ca/"


def scan_lpl_playwright(today: date, end: date):
    """Return (events, excluded, failures)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], [], ["LPL 線上場：本機未安裝 Playwright，跳過（Actions 環境會安裝）"]
    events: list[Event] = []
    excluded: list[dict] = []
    failures: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(PROGRAMS_URL, timeout=90000)
            page.wait_for_timeout(12000)
            text = page.inner_text("body")
            if "Virtual" not in text and "Zoom" not in text and "Online" not in text:
                failures.append("LPL 線上場：頁面已渲染但未見 Virtual／Zoom／Online 字樣，本輪無符合線上活動")
                browser.close()
                return events, excluded, failures
            cards = page.eval_on_selector_all(
                "a[href*='event'], [class*='event-card'], [class*='event-item']",
                "els => els.map(e => ({href: e.href || '', text: e.textContent.trim().slice(0, 600)}))",
            )
            seen: set[str] = set()
            for card in cards:
                href, txt = card["href"], card["text"]
                if not txt or href in seen:
                    continue
                seen.add(href)
                if not re.search(r"virtual|online|zoom|webinar", txt, re.I):
                    continue
                title = clean_text(txt.split("\n")[0])[:120]
                d = parse_month_day_year(txt)
                if not d or not (today <= d <= end):
                    continue
                include, relevance, _ = classify(title, txt)
                if not include:
                    continue
                start = datetime.combine(d, time(12, 0), tzinfo=TORONTO)
                events.append(Event(
                    source="lpl", title=title, start=start, end=None,
                    location="線上", url=href or PROGRAMS_URL,
                    price_evidence="免費（圖書館活動原則）",
                    summary=first_sentence(txt) or title, relevance=relevance,
                    relevance_reason="LPL 線上活動", status="free", topic="",
                ))
            browser.close()
    except Exception as e:  # noqa: BLE001
        failures.append(f"LPL 線上場抓取失敗：{e}")
    return events, excluded, failures
