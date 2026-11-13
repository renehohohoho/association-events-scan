"""Weekly association + library events scan (GitHub Actions).

Usage:
    python -m scripts.scan [--date YYYY-MM-DD] [--repo-root PATH]
                           [--with-browser] [--skip-browser]

- Default: requests-only sources (ASQ, OACETT, OSPE, CTTAM, TPL,
  Mississauga author talks). With --with-browser, also runs the Playwright
  sources (Mississauga general programs, LPL online).
- Writes reports/latest.md + state/last-scan.json + scan-summary.json
  (for the workflow's issue comment).
- Never logs in anywhere; never registers for anything. Any source failure
  is recorded in the report and the summary, never silently skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.report import (  # noqa: E402
    build_state, extract_registered_section, load_prev_state,
    parse_prev_events, render_report,
)
from scripts.sources import asq, cttam, mississauga, oacett, ospe, tpl  # noqa: E402
from scripts.sources.common import Event, make_session, scan_window  # noqa: E402
from scripts.sources import lpl as lpl_mod  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="Scan date YYYY-MM-DD (default: today ET)")
    ap.add_argument("--repo-root", default=".", help="Repo root (default: cwd)")
    ap.add_argument("--with-browser", action="store_true",
                    help="Also run Playwright sources (Mississauga programs, LPL)")
    ap.add_argument("--skip-browser", action="store_true",
                    help="Skip Playwright sources even if installed")
    args = ap.parse_args()

    root = Path(args.repo_root).resolve()
    today = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else None
    start, end = scan_window(today)
    today = start
    print(f"scan window: {start} .. {end}")

    session = make_session()
    failures: list[str] = []
    notes: list[str] = []
    assoc_events: list[Event] = []
    lib_events: list[Event] = []
    excluded: list[dict] = []
    lib_excluded: list[dict] = []
    supplementary: list[dict] = []
    asq_stats: dict = {}
    asq_unpriced: list[dict] = []
    source_notes: dict = {}

    # ---- ASQ ----
    try:
        evs, exc, fails, stats, nts = asq.scan_asq(session, today, end)
        assoc_events += evs
        excluded += [{**x, "source": "ASQ"} for x in exc]
        asq_unpriced = [x for x in exc if x["reason"].startswith("詳情頁未標價")]
        failures += fails
        notes += nts
        asq_stats = stats
        print(f"ASQ: listed={stats.get('listed')} free={stats.get('free')} "
              f"paid={stats.get('paid')} unpriced={stats.get('unpriced')}")
    except Exception as e:  # noqa: BLE001 - one source must not kill the run
        failures.append(f"ASQ 掃描異常中止：{e}")
    conf_fail = asq.check_conferences(session)
    if conf_fail:
        failures.append(conf_fail)

    # ---- OACETT ----
    try:
        evs, exc, sup, fails, stats = oacett.scan_oacett(session, today, end)
        assoc_events += evs
        excluded += [{**x, "source": "OACETT"} for x in exc]
        supplementary += sup
        failures += fails
        print(f"OACETT: listed={stats.get('listed')} free={stats.get('free')} paid={stats.get('paid')}")
    except Exception as e:  # noqa: BLE001
        failures.append(f"OACETT 掃描異常中止：{e}")

    # ---- OSPE ----
    try:
        evs, exc, fails, stats, nts = ospe.scan_ospe(session, today, end)
        assoc_events += evs
        excluded += [{**x, "source": "OSPE"} for x in exc]
        failures += fails
        notes += nts
        print(f"OSPE: api={stats.get('api')} free={stats.get('free')} "
              f"member_pending={stats.get('member_pending')} paid={stats.get('paid')}")
    except Exception as e:  # noqa: BLE001
        failures.append(f"OSPE 掃描異常中止：{e}")
    try:
        source_notes["englearn"] = ospe.check_englearn(session)
    except Exception as e:  # noqa: BLE001
        failures.append(f"OSPE EngLearn 檢查失敗：{e}")

    # ---- CTTAM ----
    try:
        evs, fails = cttam.scan_cttam(session, today, end)
        assoc_events += evs
        failures += fails
        print(f"CTTAM: {len(evs)} events")
    except Exception as e:  # noqa: BLE001
        failures.append(f"CTTAM 掃描異常中止：{e}")

    # ---- TPL ----
    try:
        evs, exc, fails, stats = tpl.scan_tpl(session, today, end)
        lib_events += evs
        lib_excluded += exc
        failures += fails
        print(f"TPL: pages={stats.get('pages')} cards={stats.get('cards')} "
              f"candidates={stats.get('candidates')} listed={stats.get('listed')} full={stats.get('full')}")
    except Exception as e:  # noqa: BLE001
        failures.append(f"TPL 掃描異常中止：{e}")

    # ---- Mississauga author talks ----
    try:
        evs, exc, fails = mississauga.scan_author_talks(session, today, end)
        lib_events += evs
        lib_excluded += exc
        failures += fails
        print(f"Mississauga author talks: {len(evs)} events")
    except Exception as e:  # noqa: BLE001
        failures.append(f"Mississauga 作者講座掃描異常中止：{e}")

    # ---- Playwright sources (opt-in) ----
    use_browser = args.with_browser and not args.skip_browser
    if use_browser:
        try:
            evs, exc, fails = mississauga.scan_programs_playwright(today, end)
            lib_events += evs
            lib_excluded += exc
            failures += fails
            print(f"Mississauga programs (browser): {len(evs)} events")
        except Exception as e:  # noqa: BLE001
            failures.append(f"Mississauga 一般活動掃描異常中止：{e}")
        try:
            evs, exc, fails = lpl_mod.scan_lpl_playwright(today, end)
            lib_events += evs
            lib_excluded += exc
            failures += fails
            print(f"LPL online (browser): {len(evs)} events")
        except Exception as e:  # noqa: BLE001
            failures.append(f"LPL 掃描異常中止：{e}")
    else:
        failures.append("Mississauga 一般活動（ActiveNet）與 LPL 線上場為 JS 渲染頁面，本輪未以瀏覽器抓取（未加 --with-browser）；詳見查證限制")

    # ---- Dedupe + sort ----
    def dedupe(evs: list[Event]) -> list[Event]:
        seen: dict[str, Event] = {}
        for e in evs:
            seen.setdefault(e.key(), e)
        return sorted(seen.values(), key=lambda e: (e.start, e.title))

    assoc_events = dedupe(assoc_events)
    lib_events = dedupe(lib_events)

    # ---- Previous report (diff baseline) ----
    prev_md = ""
    prev_path = root / "reports" / "latest.md"
    if prev_path.exists():
        prev_md = prev_path.read_text(encoding="utf-8")
    registered_section = extract_registered_section(prev_md)
    state_path = root / "state" / "last-scan.json"
    prev_events = load_prev_state(str(state_path))
    if not prev_events:
        prev_events = parse_prev_events(prev_md)

    md = render_report(
        today=today, end=end,
        scan_mode="GitHub Actions 自動掃描（每週三 13:17 UTC）",
        assoc_events=assoc_events, lib_events=lib_events,
        excluded=excluded, lib_excluded=lib_excluded,
        supplementary=supplementary, asq_stats=asq_stats,
        asq_unpriced=asq_unpriced, notes=notes, failures=failures,
        prev_events=prev_events, registered_section=registered_section,
        source_notes=source_notes,
    )
    (root / "reports").mkdir(exist_ok=True)
    prev_path.write_text(md, encoding="utf-8")
    (root / "state").mkdir(exist_ok=True)
    state_path.write_text(
        json.dumps(build_state(today, assoc_events + lib_events, failures),
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    new_keys = {e.key() for e in assoc_events + lib_events} - set(prev_events)
    summary = {
        "scan_date": today.isoformat(),
        "window_end": end.isoformat(),
        "assoc_free": len(assoc_events),
        "library_free": len(lib_events),
        "new_count": len(new_keys),
        "new_titles": list(dict.fromkeys(
            e.title for e in assoc_events + lib_events if e.key() in new_keys))[:20],
        "failures": failures,
        "asq_stats": asq_stats,
    }
    (root / "scan-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"done: assoc={len(assoc_events)} library={len(lib_events)} "
          f"new={len(new_keys)} failures={len(failures)}")
    for f in failures:
        print("  FAIL:", f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
