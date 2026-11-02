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

- Jobs reports (NFP): the BLS Employment Situation archive (past releases) and the BLS release schedule (about 14 months
  ahead). The BLS iCalendar feed is used as a cross-check. BLS refuses the Python `requests` library and browser-like agents,
  so the service downloads with Python's own `urllib`.
- FOMC eves: the first day of each two-day meeting, read from each "<year> FOMC Meetings" panel on the Fed's calendar page.

A year is published only when it has 10 to 13 jobs reports and 7 to 9 FOMC eves, all on weekdays inside that year. A year that
passed is kept in `verified/` and committed. When a download fails or looks wrong, the last verified copy is published again
and the run ends as failed ("Calendar needs attention"), so GitHub emails the owner. There are no typed-in dates any more:
the old built-in lists started in April 2025 and left Jan-Mar 2025 out of the published file.
