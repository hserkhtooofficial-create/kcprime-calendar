from __future__ import annotations

import argparse
import calendar
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


FRED_EMPLOYMENT_SITUATION_RID = 50
FED_FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

BUILT_IN = {
    2025: {
        "NFP": [
            "2025-04-04", "2025-05-02", "2025-06-06", "2025-07-03",
            "2025-08-01", "2025-09-05", "2025-11-20", "2025-12-16",
        ],
        "FOMC_EVE": [
            "2025-03-18", "2025-05-06", "2025-06-17", "2025-07-29",
            "2025-09-16", "2025-10-28", "2025-12-09",
        ],
    },
    2026: {
        "NFP": [
            "2026-01-09", "2026-02-11", "2026-03-06", "2026-04-03",
            "2026-05-08", "2026-06-05", "2026-07-02", "2026-08-07",
            "2026-09-04", "2026-10-02", "2026-11-06", "2026-12-04",
        ],
        "FOMC_EVE": [
            "2026-01-27", "2026-03-17", "2026-04-28", "2026-06-16",
            "2026-07-28", "2026-09-15", "2026-10-27", "2026-12-08",
        ],
    },
}


def get(url: str) -> str:
    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0 KCPrimeCalendarService/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml,text/plain,*/*",
        },
    )
    response.raise_for_status()
    return response.text


def parse_fred_nfp(year: int) -> list[str]:
    url = (
        "https://fred.stlouisfed.org/releases/calendar"
        f"?rid={FRED_EMPLOYMENT_SITUATION_RID}&view=year"
        f"&vs={year}-01-01&ve={year}-12-31&od=asc"
    )
    html = get(url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    pattern = re.compile(
        r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
        rf"(\d{{1,2}}),\s+{year}",
        re.IGNORECASE,
    )
    found: set[str] = set()
    for match in pattern.finditer(text):
        month = list(calendar.month_name).index(match.group(2).capitalize())
        day = int(match.group(3))
        found.add(f"{year:04d}-{month:02d}-{day:02d}")
    return sorted(found)


def parse_fed_fomc_eve(year: int) -> list[str]:
    html = get(FED_FOMC_URL)
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    start = text.find(str(year))
    if start == -1:
        return []
    next_year = text.find(str(year + 1), start + 4)
    section = text[start:next_year if next_year != -1 else len(text)]

    month_names = "|".join(calendar.month_name[1:])
    pattern = re.compile(rf"({month_names})\s+(\d{{1,2}})\s*[-\u2013]\s*(\d{{1,2}})", re.IGNORECASE)
    found: set[str] = set()
    for match in pattern.finditer(section):
        month = list(calendar.month_name).index(match.group(1).capitalize())
        first_day = int(match.group(2))
        found.add(f"{year:04d}-{month:02d}-{first_day:02d}")
    return sorted(found)


def validate_dates(year: int, nfp: list[str], fomc_eve: list[str]) -> None:
    if not (8 <= len(nfp) <= 13):
        raise ValueError(f"NFP date count looks wrong for {year}: {len(nfp)}")
    if not (6 <= len(fomc_eve) <= 9):
        raise ValueError(f"FOMC Eve date count looks wrong for {year}: {len(fomc_eve)}")
    for value in nfp + fomc_eve:
        parsed = datetime.strptime(value, "%Y-%m-%d")
        if parsed.year != year:
            raise ValueError(f"Date outside requested year: {value}")
        if parsed.weekday() >= 5:
            raise ValueError(f"Weekend event date looks wrong: {value}")


def build_year(year: int, output_dir: Path) -> Path:
    source_parts: list[str] = []
    try:
        nfp = parse_fred_nfp(year)
        if not nfp:
            raise ValueError("FRED returned no NFP dates")
        source_parts.append("NFP:FRED")
    except Exception as exc:
        nfp = BUILT_IN.get(year, {}).get("NFP", [])
        source_parts.append(f"NFP:BUILT_IN({type(exc).__name__})")

    try:
        fomc_eve = parse_fed_fomc_eve(year)
        if not fomc_eve:
            raise ValueError("Fed returned no FOMC dates")
        source_parts.append("FOMC:FED")
    except Exception as exc:
        fomc_eve = BUILT_IN.get(year, {}).get("FOMC_EVE", [])
        source_parts.append(f"FOMC:BUILT_IN({type(exc).__name__})")

    validate_dates(year, nfp, fomc_eve)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"event-calendar-{year}.txt"
    content = "\n".join(
        [
            f"LastUpdatedUtc={datetime.now(timezone.utc).isoformat()}",
            f"Year={year}",
            f"NFP={','.join(nfp)}",
            f"FOMC_EVE={','.join(fomc_eve)}",
            f"Source={';'.join(source_parts)}",
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("public"))
    args = parser.parse_args()
    for year in args.years:
        path = build_year(year, args.output_dir)
        print(path)


if __name__ == "__main__":
    main()
