"""Toronto Public Library events (Bibliocommons).

The list https://tpl.bibliocommons.com/v2/events is server-rendered and
paginated (?page=N, ~21 events/page, date-ascending). Each card is a
div.event-details with title, date, time, branch/online, a description
snippet and audience categories. Matching candidates get their detail
page opened to confirm free status and full/waitlist state.
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

LIST_URL = "https://tpl.bibliocommons.com/v2/events"

TOPIC_BUCKETS = [
    (r"\bai\b|artificial intelligence|machine learning|robot|chatgpt|prompt|generative ai|coding|python|data analytics|digital", "AI／科技"),
    (r"health|wellness|bone|diabetes|dementia|caregiv|mental health|nutrition|osteoporosis", "健康"),
    (r"writing|author|book club|reading|literature|poe|poetry|novel|memoir|publish", "文學／寫作／閱讀"),
    (r"career|resume|job|interview|employment|linkedin|workplace", "職涯發展"),
    (r"engineer|architecture|building|physics|space|astronom|science", "工程／建築"),
]

KID_MARKERS = ["kids", "children", "toddler", "baby", "preschool", "storytime", "after school"]


def _bucket(title: str, desc: str) -> str:
    text = f"{title} {desc}".lower()
    for pat, name in TOPIC_BUCKETS:
        if re.search(pat, text):
            return name
    return ""


def _parse_card(card) -> dict | None:
    """Parse one div.event-details card."""
    a = card.select_one("h3 a[href*='/v2/events/']")
    if not a:
        return None
    title = clean_text(a.select_one("span[aria-hidden='true']").get_text(" ", strip=True)
                       if a.select_one("span[aria-hidden='true']")
                       else a.get_text(" ", strip=True))
    url = a["href"]
    if url.startswith("/"):
        url = "https://tpl.bibliocommons.com" + url
    text = card.get_text(" | ", strip=True)
    # Date: "on November 13, 2026" screen-reader span, or "Friday, November 13"
    d = parse_month_day_year(text)
    # Time: parse from space-joined text (pipe-joined text breaks the dash)
    time_text = card.get_text(" ", strip=True)
    start_dt, end_dt = (None, None)
    if d:
        start_dt, end_dt = parse_time_range(time_text, d)
        if start_dt is None:
            start_dt = datetime.combine(d, time(12, 0), tzinfo=TORONTO)
    # Location: "Online event" or branch name (text between time and description).
    # Multi-date series show "View all dates" instead of a branch — treat as unknown.
    location = ""
    if "Online event" in text:
        location = "線上"
    else:
        m = re.search(r"\d{1,2}:\d{2}\s*[ap]m\s+to\s+\d{1,2}:\d{2}\s*[ap]m\s*\|\s*([^|]{2,60})", text)
        if m:
            branch = clean_text(m.group(1))
            if not branch.lower().startswith("view all"):
                location = "實體，" + branch
    # Description snippet: the longest text segment between the time/location
    # block and the "Register" segment.
    desc = ""
    segments = [s.strip() for s in text.split("|")]
    reg_idx = next((i for i, s in enumerate(segments)
                    if s.startswith("Register") or s == "Registration required"), None)
    if reg_idx is not None and reg_idx > 0:
        candidates = [s for s in segments[:reg_idx]
                      if len(s) > 40 and "to " not in s[:12]
                      and not re.match(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)", s)
                      and "on " not in s[:12]]
        if candidates:
            desc = max(candidates, key=len)
    audiences = " | ".join(
        el.get_text(" ", strip=True)
        for el in card.select("a[href*='audiences=']")
    )
    return {"title": title, "url": url, "date": d, "start": start_dt, "end": end_dt,
            "location": location, "desc": desc, "audiences": audiences, "text": text}


def _fetch_detail(session: requests.Session, url: str) -> dict:
    """Open a TPL detail page; detect an explicit fee + full/waitlist state."""
    r = get(session, url, timeout=60)
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    flat = re.sub(r"\s+", " ", text)
    free = bool(re.search(r"\bfree\b", flat, re.I))
    full = bool(re.search(r"waitlist|waiting list|fully booked|event is full|spots? (are )?full"
                          r"|registration full|all places have been registered|no longer register",
                          flat, re.I))
    paid = None
    amounts = [float(a) for a in re.findall(r"\$\s?(\d[\d,]*(?:\.\d{2})?)", flat)]
    positive = [a for a in amounts if a > 0]
    if positive:
        paid = f"${min(positive):,.2f}".rstrip("0").rstrip(".")
    # Prefer the detail page's full date/time if present
    d = parse_month_day_year(flat)
    start_dt, end_dt = (None, None)
    if d:
        start_dt, end_dt = parse_time_range(flat, d)
    desc = ""
    m = re.search(r"(?:About this event|Event description|Description)[:\s]*(.{60,500})", flat, re.I)
    if m:
        desc = clean_text(m.group(1))
    return {"free": free, "paid": paid, "full": full, "date": d, "start": start_dt,
            "end": end_dt, "desc": desc, "text": flat}


def scan_tpl(session: requests.Session, today: date, end: date, max_pages: int = 90):
    failures: list[str] = []
    events: list[Event] = []
    excluded: list[dict] = []
    stats = {"pages": 0, "cards": 0, "candidates": 0, "listed": 0, "full": 0}
    # Recurring weekly series (same title + branch) repeat every week; keep
    # only the earliest occurrence per series and note it, or the report
    # drowns in repeats (e.g. WRAP, Google AI Essentials).
    series_counts: dict[tuple[str, str], int] = {}
    series_seen: set[tuple[str, str]] = set()

    page = 1
    stop = False
    while page <= max_pages and not stop:
        try:
            r = get(session, f"{LIST_URL}?page={page}", timeout=90)
        except Exception as e:  # noqa: BLE001
            failures.append(f"TPL 活動清單第 {page} 頁抓取失敗：{e}")
            break
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("div.event-details")
        stats["pages"] += 1
        if not cards:
            break
        page_min_date: date | None = None
        for card in cards:
            parsed = _parse_card(card)
            if not parsed or not parsed["date"]:
                continue
            stats["cards"] += 1
            d = parsed["date"]
            page_min_date = d if page_min_date is None or d < page_min_date else page_min_date
            if d < today:
                continue
            if d > end:
                continue
            text = f"{parsed['title']} {parsed['desc']} {parsed['audiences']}".lower()
            if any(k in text for k in KID_MARKERS):
                continue
            include, relevance, _reason = classify(parsed["title"], parsed["desc"])
            if not include:
                continue
            stats["candidates"] += 1
            # TPL prefixes full events with **FULL** in the listing title.
            if parsed["title"].strip().startswith("**FULL**"):
                stats["full"] += 1
                excluded.append({"title": parsed["title"], "date": d.strftime("%m/%d"),
                                 "price": "免費", "reason": "已滿額，僅可候補"})
                continue
            # Detail page: confirm no fee + full state. TPL events are free
            # by principle; only an explicit price excludes an event.
            try:
                det = _fetch_detail(session, parsed["url"])
            except Exception as e:  # noqa: BLE001
                failures.append(f"TPL 詳情頁抓取失敗（{parsed['title'][:40]}）：{e}")
                continue
            if det.get("paid"):
                excluded.append({"title": parsed["title"], "date": d.strftime("%m/%d"),
                                 "price": det["paid"], "reason": "付費"})
                continue
            if det["full"]:
                stats["full"] += 1
                excluded.append({"title": parsed["title"], "date": d.strftime("%m/%d"),
                                 "price": "免費", "reason": "已滿額，僅可候補"})
                continue
            start = det["start"] or parsed["start"]
            if start is None:
                start = datetime.combine(d, time(12, 0), tzinfo=TORONTO)
            loc = parsed["location"] or "實體（分館待確認）"
            loc_ok = True
            if loc.startswith("實體"):
                # TPL branches are all Toronto
                loc_ok = True
            bucket = _bucket(parsed["title"], det["desc"] or parsed["desc"])
            series_key = (parsed["title"].strip().lower(), loc)
            series_counts[series_key] = series_counts.get(series_key, 0) + 1
            if series_key in series_seen:
                continue  # repeat occurrence of a weekly series; keep first only
            series_seen.add(series_key)
            stats["listed"] += 1
            events.append(Event(
                source="tpl", title=parsed["title"], start=start,
                end=det["end"] or parsed["end"], location=loc, url=parsed["url"],
                price_evidence="Free registration required" if "registration" in det["text"].lower()
                else "圖書館活動原則",
                summary=first_sentence(det["desc"] or parsed["desc"]) or parsed["title"],
                relevance=relevance, relevance_reason="TPL 活動",
                status="free", topic=bucket or "文學／寫作／閱讀",
            ))
        # Pages are date-ascending (except featured items pinned on page 1);
        # stop once a whole page past page 1 starts beyond the window.
        if page > 1 and page_min_date and page_min_date > end:
            stop = True
        page += 1
    if not stop and page > max_pages:
        failures.append("TPL 活動清單已達頁數上限（90 頁），12 月下旬場次可能未完全覆蓋")
    # Mark kept events that are weekly series with later repeats.
    for ev in events:
        key = (ev.title.strip().lower(), ev.location)
        if series_counts.get(key, 0) > 1:
            ev.note = "每週重複系列，本輪僅列首場"
    return events, excluded, failures, stats
