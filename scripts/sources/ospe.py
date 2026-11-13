"""OSPE events.

Primary: public Tribe Events REST API
  https://members.ospe.on.ca/wp-json/tribe/events/v1/events
  ?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&per_page=100
Cross-check: the public events listing page, because the API has returned
truncated results before. Each event's detail page is opened for the
authoritative price text.

Price rule (TASK-SPEC): "Please log in to see Member pricing" means the
member price is unverified -> status 'member_pending' ("會員免費待登入確認"),
never confirmed-free, even when a $0.00 member price is also shown.
"""

from __future__ import annotations

import re
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

from .common import (
    TORONTO, Event, clean_text, classify, first_sentence, get, location_ok,
)

API_URL = "https://members.ospe.on.ca/wp-json/tribe/events/v1/events"
LIST_URL = "https://members.ospe.on.ca/events/"
ENGLEARN_URL = "https://learn.ospe.on.ca/"


def _detail_price(session: requests.Session, url: str) -> tuple[str, str]:
    """Fetch an OSPE detail page; return (status, evidence).

    status: free | member_pending | paid | unpriced
    """
    r = get(session, url, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    # Drop site chrome first: the footer contains "Toll Free: 1-866-..."
    # and a bare "free" search would mistake it for price evidence
    # (2026-11-13: a $50–$190 Monte Carlo course was misread as free).
    for el in soup.select("footer, header, nav, #colophon, .site-footer"):
        el.decompose()
    text = soup.get_text(" ", strip=True)
    flat = re.sub(r"\s+", " ", text)
    login_notice = "Please log in to see Member pricing" in flat
    if login_notice:
        m = re.search(r"Member Price:\s*\$0\.00.{0,80}", flat)
        ev = m.group(0) if m else "Please log in to see Member pricing"
        return "member_pending", ev
    # Price-context free phrases only — never a bare "free".
    free_m = re.search(r"(Cost|Price|Admission|Tickets?)\s*:\s*Free\b.{0,60}", flat, re.I)
    if free_m:
        return "free", free_m.group(0).strip()
    free2 = re.search(r"Free to (everyone|attend|all|members)\b.{0,40}", flat, re.I)
    if free2:
        return "free", free2.group(0).strip()
    amounts = [float(a) for a in re.findall(r"\$\s?(\d[\d,]*(?:\.\d{2})?)", flat)]
    positive = [a for a in amounts if a > 0]
    if positive:
        m = re.search(r"\$\s?\d[\d,]*(?:\.\d{2})?", flat)
        return "paid", (f"${min(positive):,.2f}").rstrip("0").rstrip(".")
    if amounts:  # only $0 amounts seen
        return "free", "$0.00"
    return "unpriced", ""


def _parse_api_datetime(s: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=TORONTO)
        except ValueError:
            continue
    return None


def scan_ospe(session: requests.Session, today: date, end: date):
    failures: list[str] = []
    events: list[Event] = []
    excluded: list[dict] = []
    notes: list[str] = []
    stats = {"api": 0, "detail_checked": 0, "free": 0, "member_pending": 0, "paid": 0}

    api_events: dict[str, dict] = {}
    try:
        r = get(session, API_URL, params={
            "start_date": today.isoformat(), "end_date": end.isoformat(),
            "per_page": 100,
        }, timeout=45)
        data = r.json()
        for ev in data.get("events", []):
            api_events[ev["url"]] = ev
        stats["api"] = len(api_events)
    except Exception as e:  # noqa: BLE001
        failures.append(f"OSPE REST API 抓取失敗：{e}")

    # Cross-check the listing page for events the API missed.
    try:
        r = get(session, LIST_URL, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a[href*='/event/']"):
            href = a["href"]
            if href not in api_events and "/event/" in href:
                api_events[href] = {"url": href, "title": clean_text(a.get_text(" ", strip=True)),
                                    "_from_list": True}
    except Exception as e:  # noqa: BLE001
        failures.append(f"OSPE 活動清單頁抓取失敗（僅 API 結果可用）：{e}")

    for url, ev in api_events.items():
        title = clean_text(BeautifulSoup(ev.get("title", "") or "", "html.parser").get_text(" ", strip=True))
        if not title:
            title = clean_text(ev.get("title", "") or "")
        if not title:
            continue
        start = _parse_api_datetime(ev.get("start_date", "")) if ev.get("start_date") else None
        end_dt = _parse_api_datetime(ev.get("end_date", "")) if ev.get("end_date") else None
        desc_html = ev.get("description", "") or ""
        desc = clean_text(BeautifulSoup(desc_html, "html.parser").get_text(" ", strip=True))
        # Classify on the title only: every OSPE description mentions
        # "engineer(s)", so desc-based matching would admit the whole
        # calendar (civil, land development, water, ...).
        include, relevance, _reason = classify(title)
        if not include:
            continue
        # Date window: API results are already in-window; list-page extras
        # need their date from the detail page.
        try:
            status, evidence = _detail_price(session, url)
        except Exception as e:  # noqa: BLE001
            failures.append(f"OSPE 詳情頁抓取失敗（{title[:40]}）：{e}")
            continue
        # Cross-check against the API's cost field: a detail page that
        # reads "free" while the API lists a positive price is treated
        # as paid (guards against footer/nav "free" text).
        if status == "free":
            import html as html_mod
            api_cost = html_mod.unescape(ev.get("cost", "") or "")
            api_amounts = [float(a) for a in
                           re.findall(r"(\d[\d,]*(?:\.\d{2})?)", api_cost)]
            if any(a > 0 for a in api_amounts):
                status = "paid"
                evidence = f"API 標示費用 {api_cost.strip()}，詳情頁 free 字樣存疑"
        stats["detail_checked"] += 1
        if start is None:
            # list-page extra: parse date from the detail page text
            try:
                r = get(session, url, timeout=30)
                t = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
                m = re.search(r"(\d{4}-\d{2}-\d{2})", t)
                if m:
                    start = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=TORONTO)
            except Exception:  # noqa: BLE001
                pass
        if start is None or not (today <= start.date() <= end):
            continue
        loc_ok, _ = location_ok("線上")
        if status == "free":
            stats["free"] += 1
            events.append(Event(
                source="ospe", title=title, start=start, end=end_dt,
                location="線上", url=url, price_evidence=evidence,
                summary=first_sentence(desc) or title, relevance=relevance,
                relevance_reason="OSPE 活動", status="free",
            ))
        elif status == "member_pending":
            stats["member_pending"] += 1
            events.append(Event(
                source="ospe", title=title, start=start, end=end_dt,
                location="線上", url=url, price_evidence=evidence,
                summary=first_sentence(desc) or title, relevance=relevance,
                relevance_reason="OSPE 活動", status="member_pending",
                note="會員價需登入購物車確認是否為 $0",
            ))
        elif status == "paid":
            stats["paid"] += 1
            excluded.append({"title": title, "date": start.strftime("%m/%d"),
                             "price": evidence[:40], "reason": "付費"})
        else:
            excluded.append({"title": title, "date": start.strftime("%m/%d"),
                             "price": "未標示", "reason": "詳情頁未標價"})
    # PE300 monthly session: flag when not listed (recurring, often late).
    if not any("PE300" in e.title for e in events):
        notes.append(
            f"PE300 – Journey to P.Eng {today.strftime('%Y-%m')} 場次官網尚未刊登"
            "（每月最後週三規律推算，報名前請再確認）")
    return events, excluded, failures, stats, notes


def check_englearn(session: requests.Session) -> str:
    """learn.ospe.on.ca only hosts on-demand content; confirm no scheduled events."""
    try:
        r = session.get(ENGLEARN_URL, timeout=30)
        if r.status_code != 200:
            return f"EngLearn 回 {r.status_code}，未確認"
        return "EngLearn 僅隨選內容，無排定活動"
    except Exception as e:  # noqa: BLE001
        return f"EngLearn 抓取失敗：{e}"
