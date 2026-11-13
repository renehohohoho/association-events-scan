"""ASQ sources.

1. Member calendar https://my.asq.org/events/calendar — ASP.NET WebForms page.
   The list is server-rendered; the "All" page-size option is selected with a
   __doPostBack (full form fields incl. __VIEWSTATE + anti-forgery token),
   which returns every upcoming event (Nov + Dec groups) in one page.
   Each relevant event's detail page is then fetched and price-checked
   verbatim. No login is ever attempted.
2. https://asq.org/conferences — usually Cloudflare 403; retried weekly and
   the failure is recorded, never silently skipped.
"""

from __future__ import annotations

import re
from datetime import date

import requests
from bs4 import BeautifulSoup

from .common import (
    TORONTO, Event, clean_text, classify, extract_price_evidence,
    first_sentence, get, location_ok, parse_asq_when, scan_window,
)

CALENDAR_URL = "https://my.asq.org/events/calendar"
CONFERENCES_URL = "https://asq.org/conferences"
DETAIL_BASE = "https://my.asq.org"


def _form_fields(soup: BeautifulSoup) -> dict:
    form = soup.find("form")
    data: dict[str, str] = {}
    if not form:
        return data
    for el in form.find_all(["input", "select", "textarea"]):
        name = el.get("name")
        if not name:
            continue
        if el.name == "select":
            opt = el.find("option", selected=True)
            data[name] = opt["value"] if opt and opt.has_attr("value") else ""
        else:
            data[name] = el.get("value", "")
    return data


def fetch_calendar_list(session: requests.Session) -> list[dict]:
    """Return all upcoming calendar entries: title, url, when_raw, where_raw."""
    r = get(session, CALENDAR_URL, timeout=60)
    soup = BeautifulSoup(r.text, "html.parser")
    data = _form_fields(soup)
    if "__VIEWSTATE" not in data:
        raise RuntimeError("ASQ 行事曆：找不到 __VIEWSTATE，頁面結構可能已變")
    data["__EVENTTARGET"] = "ctl00$MainCopy$ctl06$ddlResultsPerPage"
    data["__EVENTARGUMENT"] = ""
    data["ctl00$MainCopy$ctl06$ddlResultsPerPage"] = "9999999"
    r2 = session.post(CALENDAR_URL, data=data, timeout=180)
    r2.raise_for_status()
    soup2 = BeautifulSoup(r2.text, "html.parser")
    count_m = re.search(r"1 to \d+ of (\d+) Events", soup2.get_text(" ", strip=True))
    total = int(count_m.group(1)) if count_m else None

    entries: list[dict] = []
    seen: set[str] = set()
    for a in soup2.select("a[href*='event-description']"):
        href = a["href"].replace("&amp;", "&")
        url = href if href.startswith("http") else DETAIL_BASE + href
        if url in seen:
            continue
        seen.add(url)
        # The item block holds When:/Where: lines; walk up to the item div.
        node = a
        block_text = ""
        for _ in range(10):
            node = node.parent
            if node is None:
                break
            t = node.get_text(" ", strip=True)
            if "When:" in t:
                block_text = t
                break
        when_m = re.search(r"When:\s*(.+?)(?:\s+Where:|\s+Community:|\s*$)", block_text)
        where_m = re.search(r"Where:\s*(.+?)(?:\s+Community:|\s*$)", block_text)
        entries.append({
            "title": clean_text(a.get_text(" ", strip=True)),
            "url": url,
            "when_raw": when_m.group(1).strip() if when_m else "",
            "where_raw": where_m.group(1).strip() if where_m else "",
        })
    if total is not None and len(entries) < total * 0.9:
        raise RuntimeError(f"ASQ 行事曆：標示 {total} 場，只讀到 {len(entries)} 場")
    return entries


def fetch_detail(session: requests.Session, url: str) -> dict:
    """Fetch one ASQ detail page; return parsed fields."""
    import html as html_mod

    r = get(session, url, timeout=45)
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    # The event description is embedded as an escaped HTML string inside
    # the page: strip tags from the unescaped raw HTML so price phrases
    # like "COST: Free. Open to all." become adjacent text again.
    clean = html_mod.unescape(r.text)
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = re.sub(r"\\[\"'nrt]", " ", clean)
    clean = re.sub(r"\s+", " ", clean)
    combined = text + " " + clean
    # "When:" line (also present in raw HTML as escaped text)
    when = parse_asq_when(combined)
    # Price evidence from the description area
    status, evidence, amount = extract_price_evidence(combined)
    # Description: text after the Topic/DESCRIPTION header, first sentences.
    # (ASQ detail pages label the body "Topic:" rather than "Description".)
    summary = ""
    desc_head = ""
    m = re.search(r"(?:Topic|DESCRIPTION|Description|About this event)[:\s]*(.{40,400})", text, re.I)
    if m:
        desc_head = m.group(1)
        summary = first_sentence(m.group(1))
    if not summary:
        # fall back: longest sentence-like chunk mentioning the topic
        summary = first_sentence(text)
    # Detail-page title (h1) + its own Location field. Listing titles are
    # often truncated or renamed ("online meeting: ..."), so the detail
    # title/description is the second chance for relevance classification.
    # The detail Location field is authoritative for online vs physical:
    # listing Where: is often blank or a placeholder section address.
    h1 = soup.find("h1")
    detail_title = clean_text(h1.get_text(" ", strip=True)) if h1 else ""
    loc_m = re.search(r"Location\s*:?\s*(.{0,200})", text)
    detail_location = clean_text(loc_m.group(1)) if loc_m else ""
    virtual = bool(re.search(r"online|virtual|zoom|webex|livestream", detail_location, re.I))
    return {"when": when, "status": status, "evidence": evidence,
            "amount": amount, "summary": summary, "text": text,
            "detail_title": detail_title, "detail_location": detail_location,
            "virtual": virtual, "desc_head": desc_head}


def scan_asq(session: requests.Session, today: date, end: date):
    """Return (events, excluded, failures, stats, notes)."""
    failures: list[str] = []
    events: list[Event] = []
    excluded: list[dict] = []  # {title, date, price, reason}
    notes: list[str] = []
    stats = {"listed": 0, "detail_checked": 0, "free": 0, "paid": 0, "unpriced": 0}
    seen_asq: set = set()

    try:
        entries = fetch_calendar_list(session)
    except Exception as e:  # noqa: BLE001 - recorded, scan continues
        failures.append(f"ASQ 行事曆抓取失敗：{e}")
        return events, excluded, failures, stats, notes
    stats["listed"] = len(entries)

    for entry in entries:
        when = parse_asq_when(entry["when_raw"]) if entry["when_raw"] else None
        if when:
            start, end_dt = when
        else:
            start, end_dt = None, None
        # Window filter (skip if we know the date and it is outside)
        if start and not (today <= start.date() <= end):
            continue
        include, relevance, reason = classify(entry["title"])
        detail = None
        if not include:
            # Listing titles are often truncated or renamed
            # ("online meeting: Build the Same Report..."), so re-check
            # relevance against the detail page's title + description head
            # before discarding. A failed fetch here just means "cannot
            # establish relevance" — skip silently.
            try:
                detail = fetch_detail(session, entry["url"])
                stats["detail_checked"] += 1
            except Exception:  # noqa: BLE001
                continue
            include, relevance, reason = classify(detail["detail_title"], detail["desc_head"])
            if not include:
                continue
        # Detail page: price verification (mandatory for the main list)
        if detail is None:
            try:
                detail = fetch_detail(session, entry["url"])
                stats["detail_checked"] += 1
            except Exception as e:  # noqa: BLE001
                failures.append(f"ASQ 詳情頁抓取失敗（{entry['title'][:40]}）：{e}")
                excluded.append({"title": entry["title"], "date": entry["when_raw"],
                                 "price": "詳情頁抓取失敗", "reason": "未標價／無法確認"})
                stats["unpriced"] += 1
                continue
        d_start = detail["when"][0] if detail["when"] else start
        d_end = detail["when"][1] if detail["when"] else end_dt
        if d_start and not (today <= d_start.date() <= end):
            excluded.append({"title": entry["title"],
                             "date": d_start.strftime("%m/%d") if d_start else entry["when_raw"],
                             "price": detail["amount"] or "未標示",
                             "reason": "詳情頁日期超出本輪區間"})
            continue
        if not d_start:
            failures.append(f"ASQ 詳情頁無可解析日期（{entry['title'][:40]}），不列入")
            stats["unpriced"] += 1
            continue
        # Organizer-delayed events stay listed but flagged (QMS 11/20 case).
        # The note is only surfaced for events that actually make the list.
        delayed = bool(re.search(r"delay|postpon", detail["text"], re.I))
        # Same virtual session cross-listed by two sections (e.g. Santa 12/3):
        # keep the first listing only.
        dup_key = (entry["title"].strip().lower(), d_start.date())
        if dup_key in seen_asq:
            continue
        seen_asq.add(dup_key)
        # Location: listing Where: first; the detail page's Location field
        # overrides it (listing Where: is often blank or a placeholder
        # section address, e.g. QMS 11/20's Oklahoma City address for a
        # Webex session). Empty Where: means online in practice.
        where = entry["where_raw"]
        loc_ok, _ = location_ok(where)
        if detail["virtual"]:
            loc_ok = True
        if detail["virtual"] or not where:
            ev_location = "線上"
        elif "線上" in where:
            ev_location = "線上"
        else:
            ev_location = where
        status = detail["status"]
        if status == "free":
            if not loc_ok:
                excluded.append({"title": entry["title"],
                                 "date": d_start.strftime("%m/%d") if d_start else entry["when_raw"],
                                 "price": "免費", "reason": "免費但實體在外州／外省"})
                continue
            stats["free"] += 1
            if delayed:
                notes.append(f"{entry['title'][:60]}：主辦單位註明延期中，待更新後再辦")
            # Listing titles sometimes carry a generic prefix
            # ("online meeting: ..."); drop it for display.
            display_title = re.sub(r"^(online meeting|webinar|web meeting):\s*",
                                   "", entry["title"], flags=re.I)
            events.append(Event(
                source="asq", title=display_title,
                start=d_start, end=d_end,
                location=ev_location,
                url=entry["url"], price_evidence=detail["evidence"],
                summary=detail["summary"] or entry["title"],
                relevance=relevance, relevance_reason=reason, status="free",
                note="主辦單位註明暫時延期、將盡快更新，待更新後再辦" if delayed else "",
            ))
        elif status == "paid":
            stats["paid"] += 1
            excluded.append({"title": entry["title"],
                             "date": d_start.strftime("%m/%d") if d_start else entry["when_raw"],
                             "price": detail["amount"] or detail["evidence"][:40],
                             "reason": "付費"})
        else:
            stats["unpriced"] += 1
            excluded.append({"title": entry["title"],
                             "date": d_start.strftime("%m/%d") if d_start else entry["when_raw"],
                             "price": "未標示", "reason": "詳情頁未標價，依規則不列為免費"})
    return events, excluded, failures, stats, notes


def check_conferences(session: requests.Session) -> str | None:
    """Retry asq.org/conferences; return a failure note or None on success."""
    try:
        r = session.get(CONFERENCES_URL, timeout=30)
        if r.status_code == 403:
            return "asq.org/conferences 回 403（Cloudflare），本輪未覆蓋"
        r.raise_for_status()
        return None
    except requests.RequestException as e:  # noqa: BLE001
        return f"asq.org/conferences 抓取失敗：{e}"
