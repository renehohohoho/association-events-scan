"""Render reports/latest.md in the established format and diff against the
previous report (state file preferred, previous markdown as fallback).

Format mirrors the watchdog-maintained report: header, 本輪新增／變動,
只看免費 (ASQ + OSPE), 圖書館活動 (TPL / Mississauga / LPL), 圖書館已排除,
補充資源, ASQ 行事曆深度掃描, 已排除, CTTAM, 已報名 (verbatim preserved),
查證限制.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime

from .sources.common import Event, TORONTO

WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]


def fmt_dt(start: datetime, end: datetime | None) -> str:
    wd = WEEKDAYS[start.weekday()]
    s = f"{start.month}/{start.day}（{wd}）{start.strftime('%H:%M')}"
    if end:
        s += f"–{end.strftime('%H:%M')}"
    return s


def fmt_date(d: date) -> str:
    return f"{d.month}/{d.day}（{WEEKDAYS[d.weekday()]}）"


# ---------------------------------------------------------------------------
# Previous report parsing (fallback when no state file exists)
# ---------------------------------------------------------------------------

def extract_registered_section(md: str) -> str:
    """Return the '## 已報名' section verbatim (without its heading)."""
    m = re.search(r"^## 已報名\s*\n(.*?)(?=^##\s|\Z)", md, re.S | re.M)
    return m.group(1).rstrip("\n") if m else ""


def parse_prev_events(md: str) -> dict[str, dict]:
    """Map event URL -> {title, date} for events in the previous report's
    main list and library sections (paired heading + 連結： lines, in order).
    """
    events: dict[str, dict] = {}
    # Walk top-level sections.
    sections = re.split(r"(?m)^(##\s+.*)$", md)
    # sections: [pre, h1, body1, h2, body2, ...]
    current_top = ""
    for i in range(1, len(sections), 2):
        heading = sections[i]
        body = sections[i + 1] if i + 1 < len(sections) else ""
        title_m = re.match(r"##\s+(.+)", heading)
        current_top = title_m.group(1).strip() if title_m else ""
        if not (current_top.startswith("只看免費") or current_top.startswith("圖書館活動")):
            continue
        # Split into subsections (### ...) and skip excluded/supplementary.
        subs = re.split(r"(?m)^(###\s+.*)$", body)
        for j in range(1, len(subs), 2):
            sub_h = subs[j]
            sub_b = subs[j + 1] if j + 1 < len(subs) else ""
            sub_t = re.match(r"###\s+(.+)", sub_h).group(1).strip()
            if any(k in sub_t for k in ("已排除", "補充資源", "深度掃描")):
                continue
            # Event blocks: "#### N. 「Title」" or "##### N. 「Title」"
            blocks = re.split(r"(?m)^#{4,5}\s+\d+\.\s+", sub_b)
            for block in blocks[1:]:
                title_m = re.match(r"「([^」]+)」", block)
                if not title_m:
                    continue
                title = title_m.group(1)
                url_m = re.search(r"連結：\s*(https?://\S+)", block)
                if not url_m:
                    # bare URL line
                    url_m = re.search(r"(https?://\S+)", block)
                if not url_m:
                    continue
                url = url_m.group(1).rstrip(")")
                date_m = re.search(r"時間：\s*([^\n]+)", block)
                events[url] = {"title": title,
                               "date": date_m.group(1).strip() if date_m else ""}
    return events


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _event_block(ev: Event, num: int) -> str:
    lines = [
        f"#### {num}. 「{ev.title}」",
        "",
        f"- 時間：{fmt_dt(ev.start, ev.end)} 美東",
        f"- 費用：{'免費' if ev.status == 'free' else '會員免費待登入確認'}"
        + (f"（詳情頁逐字：「{ev.price_evidence}」）" if ev.price_evidence else ""),
        f"- 地點：{ev.location}",
        f"- 一句話說明：{ev.summary}",
        f"- 連結：{ev.url}",
        f"- 為什麼相關：{ev.relevance_reason}；相關性{ev.relevance}。",
    ]
    if ev.note:
        lines.append(f"- 備註：{ev.note}")
    return "\n".join(lines)


def _lib_block(ev: Event, num: int) -> str:
    lines = [
        f"##### {num}. 「{ev.title}」",
        "",
        f"- 時間：{fmt_dt(ev.start, ev.end)}",
        f"- 費用：免費" + (f"（{ev.price_evidence}）" if ev.price_evidence else ""),
        f"- 地點：{ev.location}",
        f"- 一句話說明：{ev.summary}",
        f"- 連結：{ev.url}",
    ]
    if ev.note:
        lines.append(f"- 備註：{ev.note}")
    return "\n".join(lines)


def render_report(*, today: date, end: date, scan_mode: str,
                  assoc_events: list[Event], lib_events: list[Event],
                  excluded: list[dict], lib_excluded: list[dict],
                  supplementary: list[dict], asq_stats: dict,
                  asq_unpriced: list[dict], notes: list[str],
                  failures: list[str], prev_events: dict[str, dict],
                  registered_section: str, source_notes: dict) -> str:
    prev_keys = set(prev_events)
    cur_keys = {e.key() for e in assoc_events + lib_events}
    new_events = [e for e in assoc_events + lib_events if e.key() not in prev_keys]
    ended = [v for k, v in prev_events.items() if k not in cur_keys]
    asq_list = [e for e in assoc_events if e.source == "asq"]
    ospe_list = [e for e in assoc_events if e.source == "ospe"]
    oacett_list = [e for e in assoc_events if e.source == "oacett"]
    cttam_list = [e for e in assoc_events if e.source == "cttam"]
    tpl_list = [e for e in lib_events if e.source == "tpl"]
    miss_list = [e for e in lib_events if e.source == "mississauga"]
    lpl_list = [e for e in lib_events if e.source == "lpl"]

    L = []

    L.append("# 專業協會活動報告：2026 年 11–12 月可參加場次")
    L.append("")
    L.append(f"- 掃描日期：{today.isoformat()}（{WEEKDAYS[today.weekday()]}，多倫多時間）")
    L.append(f"- 涵蓋區間：{today.isoformat()}（{WEEKDAYS[today.weekday()]}）～ {end.isoformat()}（{WEEKDAYS[end.weekday()]}），未來 6 週")
    L.append(f"- 掃描模式：{scan_mode}")
    L.append("- 來源：協會＝GitHub Actions 自動掃描（ASQ 行事曆、OACETT、OSPE、CTTAM 公開頁）；圖書館＝同流程直掃（TPL 活動清單、Mississauga 圖書館作者講座＋活動頁、LPL 線上場）")
    L.append("- 篩選方向：MedTech／品質管理／ISO 13485、工程技術認證（C.Tech.）、AI／R&D、工程相關（工程實務、工程職涯、工程技術主題；優先製造／製程／生醫／系統／可靠度／品質工程）、多倫多／安大略實體或線上活動")
    L.append("- 費用偏好：只列免費活動（付費一律不列，僅在「備查」提及相關但付費者）")
    L.append("- 使用者背景：多倫多 MedTech 產業 Disposable Device Technician；ASQ CSSGB 持證人；OACETT、OSPE、CTTAM 會員；考取 OACETT C.Tech. 中；P.Eng（PEO）路徑規劃中；職涯目標轉往 MedTech R&D 或 AI engineering")
    L.append("")

    # ---- 本輪新增／變動 ----
    L.append(f"## 本輪新增／變動（{today.isoformat()}，GitHub Actions 自動掃描）")
    L.append("")
    if new_events:
        L.append("- 新增免費：")
        for e in new_events:
            L.append(f"  - 「{e.title}」（{fmt_date(e.start.date())}，{e.source}，{e.location}）")
    else:
        L.append("- 新增免費：無")
    if ended:
        L.append("- 已結束（移出待參加清單）：")
        for v in ended:
            L.append(f"  - {v['title']}（{v['date']}）")
    else:
        L.append("- 已結束：無")
    full_items = [x for x in lib_excluded if x.get("reason") == "已滿額，僅可候補"]
    if full_items:
        L.append("- 已滿額：")
        for x in full_items:
            L.append(f"  - 「{x['title']}」（{x['date']}，僅可候補）")
    if notes:
        L.append("- 待確認：")
        for n in notes:
            L.append(f"  - {n}")
    L.append(f"- 本輪確認免費場次：ASQ {len(asq_list)} 場、OSPE {len(ospe_list)} 場、OACETT {len(oacett_list)} 場；圖書館 TPL {len(tpl_list)} 場、Mississauga {len(miss_list)} 場、LPL {len(lpl_list)} 場。")
    L.append("")

    # ---- 只看免費 ----
    total_free = len(assoc_events)
    L.append(f"## 只看免費：{len(asq_list)} 場 ASQ ＋ {len(ospe_list)} 場 OSPE ＋ {len(oacett_list)} 場 OACETT ＋ {len(cttam_list)} 場 CTTAM ＋ 1 項補充資源")
    L.append("")
    L.append("### ASQ")
    L.append("")
    if asq_list:
        for i, ev in enumerate(asq_list, 1):
            L.append(_event_block(ev, i))
            L.append("")
    else:
        L.append("本週無免費場次。")
        L.append("")
    L.append("### OSPE")
    L.append("")
    if ospe_list:
        for i, ev in enumerate(ospe_list, 1):
            L.append(_event_block(ev, i))
            L.append("")
    else:
        L.append("本週無免費場次。")
        L.append("")
    if oacett_list:
        L.append("### OACETT")
        L.append("")
        for i, ev in enumerate(oacett_list, 1):
            L.append(_event_block(ev, i))
            L.append("")
    if cttam_list:
        L.append("### CTTAM")
        L.append("")
        for i, ev in enumerate(cttam_list, 1):
            L.append(_event_block(ev, i))
            L.append("")

    # ---- 圖書館 ----
    L.append("## 圖書館活動（GitHub Actions 本輪直掃）")
    L.append("")
    L.append("TPL、Mississauga、LPL 三來源皆已掃描。TPL 活動皆免費（圖書館活動原則；詳情頁多未顯示費用，其中明文標示免費者附逐字證據）。名額數字為查詢當下，隨時可能變動。")
    L.append("")
    L.append("### TPL")
    L.append("")
    buckets = ["AI／科技", "健康", "文學／寫作／閱讀", "職涯發展", "工程／建築"]
    n = 0
    for b in buckets:
        blist = [e for e in tpl_list if (e.topic or "文學／寫作／閱讀") == b]
        if not blist:
            continue
        L.append(f"#### {b}")
        L.append("")
        for ev in blist:
            n += 1
            L.append(_lib_block(ev, n))
            L.append("")
    if not tpl_list:
        L.append("本週無符合活動。")
        L.append("")
    L.append("### Mississauga 圖書館")
    L.append("")
    if miss_list:
        for i, ev in enumerate(miss_list, 1):
            L.append(_lib_block(ev, i))
            L.append("")
    else:
        L.append("本週無符合活動。")
        L.append("")
    L.append("### London 公共圖書館（線上）")
    L.append("")
    if lpl_list:
        for i, ev in enumerate(lpl_list, 1):
            L.append(_lib_block(ev, i))
            L.append("")
    else:
        L.append("本週無符合線上活動。")
        L.append("")

    # ---- 圖書館已排除 ----
    L.append("### 圖書館已排除（僅列備查）")
    L.append("")
    if lib_excluded:
        for x in lib_excluded:
            L.append(f"- 「{x['title']}」（{x['date']}）：{x['reason']}。")
    else:
        L.append("- 無。")
    L.append("")

    # ---- 補充資源 ----
    L.append("### 補充資源（非排定活動）")
    L.append("")
    L.append("#### 1. CSA「Foundations of Standards Literacy」（沿用，OACETT 自學區仍標示免費無限存取）")
    L.append("")
    L.append("- 費用：免費，無限存取（OACETT 自學課程區，CSA Group 提供）")
    L.append("- 地點：線上自學，無排定日期")
    L.append("- 一句話說明：標準識讀基礎課，教如何解讀與應用技術標準文件，對讀懂 ISO 13485 等醫材法規標準的思維有幫助。")
    L.append("- 報名連結：https://oacett.org/professional-development/cpd-workshops-webinars（Self Study Courses 區）")
    L.append("- 為什麼相關：中低。非 MedTech 專屬，但「讀標準」是品管與醫材法規工作的通用能力；零成本自學。")
    L.append("")
    for i, s in enumerate(supplementary, 2):
        L.append(f"#### {i}. {s['title']}（OACETT 自學）")
        L.append("")
        L.append(f"- 費用：{s['price']}")
        L.append("- 地點：線上自學，無排定日期")
        L.append(f"- 連結：{s['url']}")
        L.append("")

    # ---- ASQ 深度掃描 ----
    L.append("### ASQ 會員行事曆深度掃描（GitHub Actions 本輪直掃）")
    L.append("")
    L.append(f"以瀏覽器任務完成 my.asq.org/events/calendar 全量掃描：全程免登入（僅頁首 Log in 連結，未出現登入牆）；最終 {asq_stats.get('listed', 0)} 筆刊登；主題相關去重後 {asq_stats.get('detail_checked', 0)} 場逐場開啟詳情頁核價——{asq_stats.get('free', 0)} 場確認免費、{asq_stats.get('paid', 0)} 場付費、{asq_stats.get('unpriced', 0)} 場未標示價格（未標示者不列入免費清單，見查證限制）。確認免費並列入上方清單者：第 1–{len(asq_list)} 項。以下為同次掃描中確認付費或未標示價格的代表性項目，僅列備查：")
    L.append("")
    if asq_unpriced:
        L.append("- 價格未標示、無法確認免費（故不列入；其中最相關者）：")
        for x in asq_unpriced[:16]:
            L.append(f"  - 「{x['title']}」（{x['date']}）")
        if len(asq_unpriced) > 16:
            L.append(f"  - 另有 {len(asq_unpriced) - 16} 場主題相關活動詳情頁未標示價格，完整清單見本輪 run log。")
    L.append("")

    # ---- 已排除 ----
    L.append("## 已排除（僅列備查，不計入免費）")
    L.append("")
    if excluded:
        for x in excluded:
            L.append(f"- 「{x['title']}」（{x['date']}，{x['price']}）——{x['reason']}。")
    else:
        L.append("- 無。")
    L.append("")

    # ---- CTTAM ----
    L.append("## CTTAM：本週無新活動" if not cttam_list else "## CTTAM")
    L.append("")
    if cttam_list:
        L.append("本輪列入主清單，見上。")
    else:
        L.append("cttam.com 公開網站無活動公告；課程頁僅領導力課（付費）。該協會活動多半直接用 email 通知會員，公開網站更新慢。")
    L.append("")

    # ---- 已報名 (verbatim) ----
    L.append("## 已報名")
    L.append("")
    if registered_section.strip():
        L.append(registered_section.strip())
    else:
        L.append("- ASQ Toronto × Hamilton 合辦 HIRA 工作坊「Hazard Identification and Risk Analysis (HIRA) in Quality Risk Management」：10/24（六）9:30–15:30 美東，Rene 已於 2026-10-16 自行報名；費用 $10。已於 10/24 舉行結束。")
    L.append("")

    # ---- 查證限制 ----
    L.append("## 查證限制")
    L.append("")
    for f in failures:
        L.append(f"- {f}")
    L.append("- ASQ 會員活動行事曆在 https://my.asq.org/events/calendar，本輪已驗證不需登入即可瀏覽；報名才需登入（Rene 自行報名）。行事曆清單本身不顯示價格，本輪主題相關活動已逐場開詳情頁核價：未標示者一律不列入免費清單。myportal.asq.org 自動登入在 2026-10-01 與 2026-10-16 兩次嘗試皆失敗（同一驗證錯誤；表單從未送出，與密碼無關），掃描不嘗試登入。")
    L.append("- asq.org/conferences 未覆蓋（Cloudflare 403；每週重試，失敗即註明）。")
    L.append("- OSPE 部分活動頁未註明時區，時間以頁面標示為準，報名前請以官網為準；標示「Please log in to see Member pricing」的會員免費主張需 Rene 登入購物車確認。OSPE REST API 回傳可能截斷，已以活動清單頁交叉核對。")
    L.append("- OACETT 個別課程報名需登入會員 Portal；活動頁未標示時區，時間以美東推定，報名時以官網為準。")
    L.append("- CPD：OACETT 三年週期需 30 小時（Active 至少 15、Passive 最多 15），每項活動至少 1 小時；即時 webinar（有即時講者、1 小時以上）屬 Active。ASQ CSSGB 為終身證書，不需 RU。")
    L.append("- 圖書館：TPL 活動清單逐頁爬取未來 6 週全部場次（每週重複系列僅列首場）；Mississauga 一般活動（ActiveNet）與 LPL 線上場為 JS 渲染頁面，以 Playwright 渲染抓取，失敗時如實註明。TPL 報名需 TPL 帳號，未代為報名；名額數字為查詢當下。")
    L.append("- 各協會行事曆為動態內容，掃描日之後新增的活動未包含在內。")
    L.append("- 報告位置：本報告存放於 repo reports/latest.md（每週覆寫）；看門狗另存一份於 Muse 工作區。")
    L.append("")
    return "\n".join(L)


def build_state(today: date, events: list[Event], failures: list[str]) -> dict:
    return {
        "scan_date": today.isoformat(),
        "events": [e.to_dict() for e in events],
        "failures": failures,
    }


def load_prev_state(state_path: str) -> dict[str, dict]:
    try:
        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)
        out = {}
        for e in data.get("events", []):
            out[e["url"] or f"{e['source']}|{e['title']}"] = {
                "title": e["title"],
                "date": e["start"][:10],
            }
        return out
    except (OSError, ValueError, KeyError):
        return {}
