"""Builds the event calendar files the KC Prime bot downloads (event-calendar-<year>.txt): the jobs-report (NFP) days and the
FOMC eves (first day of each scheduled two-day Fed meeting) of each year.

Sources, all official:
  jobs reports: BLS Employment Situation archive (past releases) + BLS release schedule (upcoming, about 14 months ahead);
                the BLS iCalendar feed is a cross-check only.
  FOMC eves:    the Federal Reserve's FOMC calendar page, read year by year from its "<year> FOMC Meetings" panels.

A year is published only when its dates pass the checks (count, weekdays, year). A year that passed is saved in verified/ and
committed by the workflow; when a later download fails or looks wrong, that saved copy is published again and the run is
marked as needing attention (warnings.txt), so the bot never gets a partial or invented list. There are no typed-in dates.
"""
from __future__ import annotations

import argparse
import re
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 KCPrimeCalendarService/1.0", "Accept": "*/*"}
BLS_SCHEDULE = "https://www.bls.gov/schedule/news_release/empsit.htm"
BLS_ARCHIVE = "https://www.bls.gov/bls/news-release/empsit.htm"
BLS_ICS = "https://www.bls.gov/schedule/news_release/bls.ics"
FED_FOMC = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
HERE = Path(__file__).resolve().parent


def get(url: str) -> str:
    # BLS answers Python's own urllib with this plain agent; it refuses the requests library and browser-like agents
    # (403, checked 2026-11-02), so the service uses urllib on purpose.
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def month_no(name: str) -> int:
    return MONTHS[name.strip().lower()[:3]]


def bls_nfp_dates() -> set[date]:
    """Every Employment Situation release date the BLS lists: the archive's file names (empsit_MMDDYYYY.htm) for past
    releases and the schedule table (Release Date column, e.g. "Jan. 08, 2027") for upcoming ones."""
    found: set[date] = set()
    for m in re.finditer(r"empsit_(\d{2})(\d{2})(\d{4})\.htm", get(BLS_ARCHIVE)):
        found.add(date(int(m.group(3)), int(m.group(1)), int(m.group(2))))
    archive = len(found)
    soup = BeautifulSoup(get(BLS_SCHEDULE), "html.parser")
    for row in soup.select("table.release-list tbody tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
        m = re.match(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),\s+(\d{4})", cells[1]) if len(cells) >= 2 else None
        if m:
            found.add(date(int(m.group(3)), month_no(m.group(1)), int(m.group(2))))
    if archive == 0 or len(found) == archive:
        raise ValueError(f"BLS pages gave {archive} archived and {len(found) - archive} scheduled releases")
    return found


def bls_ics_nfp_dates() -> set[date]:
    """Cross-check: the BLS iCalendar feed's "Employment Situation" events (exact title; "... of Veterans" is a different release)."""
    out: set[date] = set()
    for ev in get(BLS_ICS).split("BEGIN:VEVENT")[1:]:
        s = re.search(r"^SUMMARY:(.*)$", ev, re.M)
        d = re.search(r"^DTSTART[^:]*:(\d{8})", ev, re.M)
        if s and d and s.group(1).strip() == "Employment Situation":
            out.add(datetime.strptime(d.group(1), "%Y%m%d").date())
    return out


def fed_fomc_eves() -> dict[int, list[date]]:
    """First day of each scheduled meeting, per "<year> FOMC Meetings" panel. A date cell like "26-27" or "31-1" with a month
    cell like "January" or "Jan/Feb"; single-day entries (notation votes, unscheduled calls) are not two-day meetings."""
    soup = BeautifulSoup(get(FED_FOMC), "html.parser")
    out: dict[int, list[date]] = {}
    for panel in soup.select("div.panel"):
        head = panel.select_one(".panel-heading")
        m = re.search(r"(\d{4}) FOMC Meetings", head.get_text(" ", strip=True)) if head else None
        if not m:
            continue
        year = int(m.group(1))
        days = []
        for meeting in panel.select("div.fomc-meeting"):
            mo, dd = meeting.select_one(".fomc-meeting__month"), meeting.select_one(".fomc-meeting__date")
            if not mo or not dd:
                continue
            r = re.match(r"\s*(\d{1,2})\s*[-–]\s*(\d{1,2})\b", dd.get_text(" ", strip=True))
            if not r:
                continue
            days.append(date(year, month_no(mo.get_text(" ", strip=True).split("/")[0]), int(r.group(1))))
        out[year] = sorted(set(days))
    if not out:
        raise ValueError("no FOMC year panels found on the Fed page")
    return out


def check_year(year: int, nfp: list[date], eves: list[date]) -> str | None:
    """None when the dates look like a real year, else the reason."""
    if not 10 <= len(nfp) <= 13:
        return f"{len(nfp)} jobs-report dates (expected 10 to 13)"
    if not 7 <= len(eves) <= 9:
        return f"{len(eves)} FOMC eves (expected 7 to 9)"
    for d in nfp + eves:
        if d.year != year or d.weekday() >= 5:
            return f"date {d} is outside {year} or on a weekend"
    return None


def file_text(year: int, nfp: list[date], eves: list[date], source: str) -> str:
    return "\n".join([f"LastUpdatedUtc={datetime.now(timezone.utc).isoformat()}", f"Year={year}",
                      f"NFP={','.join(d.isoformat() for d in nfp)}", f"FOMC_EVE={','.join(d.isoformat() for d in eves)}",
                      f"Source={source}", ""])


def dates_line(text: str, key: str) -> str:
    m = re.search(rf"^{key}=(.*)$", text, re.M)
    return m.group(1).strip() if m else ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2025)
    ap.add_argument("--future-years", type=int, default=2)
    ap.add_argument("--output-dir", type=Path, default=Path("public"))
    ap.add_argument("--verified-dir", type=Path, default=HERE / "verified")
    a = ap.parse_args()
    today = datetime.now(timezone.utc).date()
    years = range(a.start_year, today.year + a.future_years + 1)
    a.output_dir.mkdir(parents=True, exist_ok=True)
    a.verified_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    nfp_all = eves_all = None
    try:
        nfp_all = bls_nfp_dates()
    except Exception as exc:
        warnings.append(f"BLS download failed: {type(exc).__name__}: {exc}")
    try:
        eves_all = fed_fomc_eves()
    except Exception as exc:
        warnings.append(f"Fed download failed: {type(exc).__name__}: {exc}")
    try:
        ics = bls_ics_nfp_dates()
        if nfp_all is not None and ics:
            lo, hi = min(ics), max(ics)                           # the feed covers only about two years
            for d in sorted(ics ^ nfp_all):
                if d.year in years and lo <= d <= hi:
                    warnings.append(f"BLS feed and BLS pages disagree on {d} ({'feed only' if d in ics else 'pages only'})")
    except Exception as exc:
        print(f"note: BLS feed cross-check skipped ({type(exc).__name__})")

    published = 0
    for year in years:
        out, saved = a.output_dir / f"event-calendar-{year}.txt", a.verified_dir / f"event-calendar-{year}.txt"
        nfp = sorted(d for d in (nfp_all or ()) if d.year == year)
        eves = (eves_all or {}).get(year, [])
        problem = "download failed" if nfp_all is None or eves_all is None else check_year(year, nfp, eves)
        if problem is None:
            text = file_text(year, nfp, eves, "NFP:BLS;FOMC:FED")
            old = saved.read_text(encoding="utf-8") if saved.exists() else ""
            if dates_line(old, "NFP") != dates_line(text, "NFP") or dates_line(old, "FOMC_EVE") != dates_line(text, "FOMC_EVE"):
                saved.write_text(text, encoding="utf-8")          # committed by the workflow; only when the dates change
                print(f"{year}: dates {'changed' if old else 'verified for the first time'}")
            out.write_text(text, encoding="utf-8")
        elif saved.exists():
            old = saved.read_text(encoding="utf-8")
            out.write_text(old, encoding="utf-8")
            if year <= today.year or year == today.year + 1 and today.month >= 10:
                warnings.append(f"{year}: {problem}; published the last verified copy")
        elif year > today.year:
            print(f"{year}: not published yet ({problem})")             # next year's dates are not all out yet
            if year == today.year + 1 and today.month >= 11:
                warnings.append(f"{year}: still not complete in {today:%B} ({problem}); the bot needs it by January")
            continue
        else:
            warnings.append(f"{year}: {problem} and no verified copy; NOT published")
            continue
        published += 1
        print(f"{year}: {out.read_text(encoding='utf-8').splitlines()[2]} | {out.read_text(encoding='utf-8').splitlines()[3]}")

    (a.output_dir.parent / "warnings.txt").write_text("\n".join(warnings) + ("\n" if warnings else ""), encoding="utf-8")
    for w in warnings:
        print("WARNING:", w)
    if published == 0:
        raise SystemExit("No calendar years were published")


if __name__ == "__main__":
    main()
