# KCPrime Event Calendar Service

This service publishes simple yearly calendar files for KC Prime bots.

The NinjaTrader strategy should consume:

```text
https://<host>/event-calendar-2026.txt
```

File format:

```text
LastUpdatedUtc=2026-06-16T18:00:00Z
Year=2026
NFP=2026-01-09,2026-02-11
FOMC_EVE=2026-01-27,2026-03-17
Source=NFP:BLS;FOMC:FED
```

The service is designed for GitHub Actions + GitHub Pages or any static host.


## Where the dates come from (since 2026-11-02)

Two official sources for each kind of date, from two different places:

- Jobs reports (NFP): main = the BLS Employment Situation archive (past) and release schedule (about 14 months ahead);
  second = FRED's release calendar (St. Louis Fed, current year). The BLS iCalendar feed is a further cross-check. BLS refuses
  the Python `requests` library and browser-like agents, so the service downloads with Python's own `urllib`.
- FOMC eves (first day of each two-day meeting): main = each "<year> FOMC Meetings" panel on the Fed's calendar page;
  second = the Fed's calendar feed (`json/calendar.json`), the weekday before each decision day.

The main source is used when it looks like a real year (10 to 13 jobs reports, 7 to 9 FOMC eves, weekdays inside that year),
else the second one. When both have the year and disagree, or a published date changes, the run warns.

- `verified/`: the last dates that passed, committed by the job. When neither source gives a real year, this copy is published
  again. `verified/second-sources.txt` remembers since when a second source has failed (warning after a week).
- `override/`: the team's emergency fix, see `override/README.md`.
- `status.txt` (published next to the calendars): when the job last ran and its warnings. The license server reads it every
  5 minutes and sends team phone alerts (Code/LicenseServer/api/_calendar.js in the kcprime-project repo). A run with warnings
  also ends as failed ("Calendar needs attention"), so GitHub emails the owner.

There are no typed-in dates: the old built-in lists started in April 2025 and left Jan-Mar 2025 out of the published file.
