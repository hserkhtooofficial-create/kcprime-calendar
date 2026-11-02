"""Builds the event calendar files the KC Prime bot downloads (event-calendar-<year>.txt): the jobs-report (NFP) days and the
FOMC eves (first day of each scheduled two-day Fed meeting) of each year, plus status.txt for the team's daily check.

Two official sources for each kind of date, from two different places:
  jobs reports: main   BLS Employment Situation archive (past releases) + BLS release schedule (about 14 months ahead)
                second FRED's release calendar (St. Louis Fed; release 50 = Employment Situation; current year)
  FOMC eves:    main   the Fed's FOMC calendar page, read from each "<year> FOMC Meetings" panel (the panels are not in year order)
                second the Fed's calendar feed (json/calendar.json): the weekday before each "FOMC Meeting" (decision) day
A kind of date is used from the main source when it looks like a real year, else from the second one; when both have the year
and disagree, the run warns (a date may have moved). The BLS iCalendar feed is a further cross-check for jobs reports.

override/event-calendar-<year>.txt (same NFP= / FOMC_EVE= lines), when present, is published as it is: the team's emergency
fix when a date moves while the sources are broken. It warns as long as the sources show other dates, so it is not forgotten.

A year that passed is kept in verified/ (committed by the workflow). When neither source gives a real year, the last verified
copy is published again. Any warning is written to status.txt (read by the license server's daily check: team phone alert)
and fails the run (GitHub email). There are no typed-in dates.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 KCPrimeCalendarService/1.0", "Accept": "*/*"}
BLS_SCHEDULE = "https://www.bls.gov/schedule/news_release/empsit.htm"
BLS_ARCHIVE = "https://www.bls.gov/bls/news-release/empsit.htm"
BLS_ICS = "https://www.bls.gov/schedule/news_release/bls.ics"
FRED_NFP = "https://fred.stlouisfed.org/releases/calendar?rid=50&view=year&vs={y}-01-01&ve={y}-12-31&od=asc"
FED_FOMC = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FED_FEED = "https://www.federalreserve.gov/json/calendar.json"
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
MONTH_NAMES = "January|February|March|April|May|June|July|August|September|October|November|December"
HERE = Path(__file__).resolve().parent


def get(url: str) -> str:
    # BLS answers Python's own urllib with this plain agent; it refuses the requests library and browser-like agents
    # (403, checked 2026-11-02), so the service uses urllib on purpose.
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def month_no(name: str) -> int:
    return MONTHS[name.strip().lower()[:3]]


# ---------------- jobs reports ----------------
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


def fred_nfp_dates(year: int) -> set[date]:
    """FRED's Employment Situation release days for one year ("Friday January 09, 2026"); empty when FRED has none yet."""
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", get(FRED_NFP.format(y=year))))
    return {date(year, month_no(m), int(d)) for m, d in
            re.findall(rf"(?:Monday|Tuesday|Wednesday|Thursday|Friday) ({MONTH_NAMES}) (\d{{1,2}}), {year}", text)}


def bls_ics_nfp_dates() -> set[date]:
    """Cross-check: the BLS iCalendar feed's "Employment Situation" events (exact title; "... of Veterans" is a different release)."""
    out: set[date] = set()
    for ev in get(BLS_ICS).split("BEGIN:VEVENT")[1:]:
        s = re.search(r"^SUMMARY:(.*)$", ev, re.M)
        d = re.search(r"^DTSTART[^:]*:(\d{8})", ev, re.M)
        if s and d and s.group(1).strip() == "Employment Situation":
            out.add(datetime.strptime(d.group(1), "%Y%m%d").date())
    return out


# ---------------- FOMC eves ----------------
def fed_fomc_eves() -> dict[int, set[date]]:
    """First day of each scheduled meeting, per "<year> FOMC Meetings" panel. A date cell like "26-27" or "31-1" with a month
    cell like "January" or "Jan/Feb"; single-day entries (notation votes, unscheduled calls) are not two-day meetings."""
    soup = BeautifulSoup(get(FED_FOMC), "html.parser")
    out: dict[int, set[date]] = {}
    for panel in soup.select("div.panel"):
        head = panel.select_one(".panel-heading")
        m = re.search(r"(\d{4}) FOMC Meetings", head.get_text(" ", strip=True)) if head else None
        if not m:
            continue
        year, days = int(m.group(1)), set()
        for meeting in panel.select("div.fomc-meeting"):
            mo, dd = meeting.select_one(".fomc-meeting__month"), meeting.select_one(".fomc-meeting__date")
            r = re.match(r"\s*(\d{1,2})\s*[-–]\s*(\d{1,2})\b", dd.get_text(" ", strip=True)) if mo and dd else None
            if r:
                days.add(date(year, month_no(mo.get_text(" ", strip=True).split("/")[0]), int(r.group(1))))
        out[year] = days
    if not out:
        raise ValueError("no FOMC year panels found on the Fed page")
    return out


def fed_feed_eves() -> dict[int, set[date]]:
    """The Fed's calendar feed lists each scheduled meeting's decision day ("FOMC Meeting"); the eve is the weekday before."""
    raw = json.loads(get(FED_FEED).lstrip("﻿"))
    out: dict[int, set[date]] = {}
    for e in raw.get("events", raw) if isinstance(raw, dict) else raw:
        if e.get("type") != "FOMC" or str(e.get("title", "")).strip().lower() != "fomc meeting":
            continue
        y, mo = int(e["month"][:4]), int(e["month"][5:7])
        last = re.findall(r"\d{1,2}", str(e.get("days", "")))
        if not last:
            continue
        eve = date(y, mo, int(last[-1])) - timedelta(days=1)
        while eve.weekday() >= 5:
            eve -= timedelta(days=1)
        out.setdefault(eve.year, set()).add(eve)
    return out


# ---------------- checks and files ----------------
LIMITS = {"NFP": (10, 13, "jobs-report dates"), "FOMC_EVE": (7, 9, "FOMC eves")}


def problem(year: int, kind: str, dates) -> str | None:
    """None when the dates look like a real year of this kind, else why not."""
    lo, hi, what = LIMITS[kind]
    if dates is None:
        return "download failed"
    if not lo <= len(dates) <= hi:
        return f"{len(dates)} {what} (expected {lo} to {hi})"
    for d in dates:
        if d.year != year or d.weekday() >= 5:
            return f"date {d} is outside {year} or on a weekend"
    return None


def file_text(year: int, nfp, eves, source: str) -> str:
    return "\n".join([f"LastUpdatedUtc={datetime.now(timezone.utc).isoformat()}", f"Year={year}",
                      f"NFP={','.join(d.isoformat() for d in sorted(nfp))}", f"FOMC_EVE={','.join(d.isoformat() for d in sorted(eves))}",
                      f"Source={source}", ""])


def read_dates(text: str, key: str) -> set[date]:
    m = re.search(rf"^{key}=(.*)$", text, re.M)
    return {date.fromisoformat(x.strip()) for x in (m.group(1).split(",") if m else []) if x.strip()}


def show(ds) -> str:
    return ", ".join(d.strftime("%b %d") for d in sorted(ds)) or "none"


def choose(year: int, kind: str, main, second, warnings: list[str]):
    """The dates to use for one kind and their source name, or (None, why) when neither source has a real year."""
    pm, ps = problem(year, kind, main), problem(year, kind, second)
    names = {"NFP": ("BLS", "FRED"), "FOMC_EVE": ("FED", "FED_FEED")}[kind]
    if pm is None:
        if ps is None and main != second:
            warnings.append(f"{year} {kind}: the two sources disagree ({names[0]} only: {show(main - second)}; {names[1]} only: {show(second - main)}). "
                            f"Published {names[0]}; check which is right")
        return main, names[0]
    if ps is None:
        warnings.append(f"{year} {kind}: {names[0]} failed ({pm}); published {names[1]}")
        return second, names[1]
    return None, f"{names[0]}: {pm}; {names[1]}: {ps}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2025)
    ap.add_argument("--future-years", type=int, default=2)
    ap.add_argument("--output-dir", type=Path, default=Path("public"))
    ap.add_argument("--verified-dir", type=Path, default=HERE / "verified")
    ap.add_argument("--override-dir", type=Path, default=HERE / "override")
    a = ap.parse_args()
    today = datetime.now(timezone.utc).date()
    years = range(a.start_year, today.year + a.future_years + 1)
    a.output_dir.mkdir(parents=True, exist_ok=True)
    a.verified_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    def attempt(what, fn, main_source=True):
        try:
            return fn()
        except Exception as exc:
            msg = f"{what} download failed: {type(exc).__name__}: {str(exc)[:120]}"
            if main_source:
                warnings.append(msg)
            else:
                print("note:", msg)                            # a second source: see failing_since below
            return None

    bls = attempt("BLS", bls_nfp_dates)
    fed = attempt("Fed page", fed_fomc_eves)
    feed = attempt("Fed feed", fed_feed_eves, False)
    fred = {}
    for y in years:
        if y <= today.year:                                    # FRED lists the current year (and the past) only
            fred[y] = attempt(f"FRED {y}", lambda y=y: fred_nfp_dates(y), False)
    # A second source that keeps failing while the main one works sends no alert each day, only once it has failed for a week,
    # so the backup is not lost unnoticed. First failure days are kept in verified/second-sources.txt (committed).
    health_file, health = a.verified_dir / "second-sources.txt", {}
    if health_file.exists():
        health = dict(l.split("=", 1) for l in health_file.read_text(encoding="utf-8").splitlines() if "=" in l)
    for name, ok in (("FRED", all(v is not None for v in fred.values())), ("FED_FEED", feed is not None)):
        if ok:
            health.pop(name, None)
        else:
            since = health.setdefault(name, today.isoformat())
            if (today - date.fromisoformat(since)).days >= 7:
                warnings.append(f"second source {name} has failed every day since {since}; the main source still works")
    health_file.write_text("".join(f"{k}={v}\n" for k, v in sorted(health.items())), encoding="utf-8")
    try:
        ics = bls_ics_nfp_dates()
        if bls is not None and ics:
            lo, hi = min(ics), max(ics)                        # the feed covers only about two years
            for d in sorted(ics ^ bls):
                if d.year in years and lo <= d <= hi:
                    warnings.append(f"BLS feed and BLS pages disagree on {d} ({'feed only' if d in ics else 'pages only'})")
    except Exception as exc:
        print(f"note: BLS feed cross-check skipped ({type(exc).__name__})")

    published = 0
    for year in years:
        out, saved, over = (a.output_dir / f"event-calendar-{year}.txt", a.verified_dir / f"event-calendar-{year}.txt",
                            a.override_dir / f"event-calendar-{year}.txt")
        nfp, nfp_src = choose(year, "NFP", None if bls is None else {d for d in bls if d.year == year},
                              (fred.get(year) or None) if year in fred else None, warnings)
        eves, eve_src = choose(year, "FOMC_EVE", None if fed is None else fed.get(year, set()),
                               None if feed is None else (feed.get(year) or None), warnings)
        fetched_ok = nfp is not None and eves is not None
        old = saved.read_text(encoding="utf-8") if saved.exists() else ""

        if over.exists():                                      # the team's emergency fix wins
            text = over.read_text(encoding="utf-8")
            o_nfp, o_eves = read_dates(text, "NFP"), read_dates(text, "FOMC_EVE")
            bad = problem(year, "NFP", o_nfp) or problem(year, "FOMC_EVE", o_eves)
            if bad:
                warnings.append(f"{year}: override file is not usable ({bad}); ignored")
            else:
                if not fetched_ok or o_nfp != nfp or o_eves != eves:
                    warnings.append(f"{year}: override file in use; the sources show {'other dates' if fetched_ok else 'nothing usable'}. "
                                    "Delete the override once the sources show the right dates")
                else:
                    print(f"{year}: override matches the sources; it can be deleted")
                out.write_text(file_text(year, o_nfp, o_eves, "OVERRIDE"), encoding="utf-8")
                published += 1
                print(f"{year}: OVERRIDE NFP={show(o_nfp)} | FOMC_EVE={show(o_eves)}")
                continue

        if fetched_ok:
            text = file_text(year, nfp, eves, f"NFP:{nfp_src};FOMC:{eve_src}")
            if old:
                o_nfp, o_eves = read_dates(old, "NFP"), read_dates(old, "FOMC_EVE")
                for kind, was, now in (("jobs report", o_nfp, nfp), ("FOMC eve", o_eves, eves)):
                    if was != now:
                        warnings.append(f"{year}: {kind} dates changed: removed {show(was - now)}, added {show(now - was)}. Check it")
            if read_dates(old, "NFP") != nfp or read_dates(old, "FOMC_EVE") != eves:
                saved.write_text(text, encoding="utf-8")          # committed by the workflow; only when the dates change
                print(f"{year}: dates {'changed' if old else 'verified for the first time'}")
            out.write_text(text, encoding="utf-8")
        elif old:
            out.write_text(old, encoding="utf-8")
            if year <= today.year or year == today.year + 1 and today.month >= 10:
                warnings.append(f"{year}: no usable source ({nfp_src if nfp is None else eve_src}); published the last verified copy")
        elif year > today.year:
            print(f"{year}: not published yet ({nfp_src if nfp is None else eve_src})")   # next year's dates are not all out yet
            if year == today.year + 1 and today.month >= 11:
                warnings.append(f"{year}: still not complete in {today:%B}; the bot needs it by January")
            continue
        else:
            warnings.append(f"{year}: no usable source and no verified copy; NOT published")
            continue
        published += 1
        lines = out.read_text(encoding="utf-8").splitlines()
        print(f"{year}: {lines[2]} | {lines[3]} | {lines[4]}")

    status = [f"LastRunUtc={datetime.now(timezone.utc).isoformat()}", f"Warnings={len(warnings)}"] + [f"WARN={w}" for w in warnings]
    (a.output_dir / "status.txt").write_text("\n".join(status) + "\n", encoding="utf-8")
    (a.output_dir.parent / "warnings.txt").write_text("\n".join(warnings) + ("\n" if warnings else ""), encoding="utf-8")
    for w in warnings:
        print("WARNING:", w)
    if published == 0:
        raise SystemExit("No calendar years were published")


if __name__ == "__main__":
    main()
