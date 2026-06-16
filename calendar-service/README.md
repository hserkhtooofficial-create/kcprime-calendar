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
Source=NFP:FRED_CALENDAR;FOMC:FED_CALENDAR
```

The service is designed for GitHub Actions + GitHub Pages or any static host.

