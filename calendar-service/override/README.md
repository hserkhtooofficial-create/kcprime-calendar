# Emergency override

Use this only when an official date has moved (for example a government shutdown moves a jobs report) and the service cannot
read the new date from BLS/FRED or the Fed, so the published file is wrong.

1. In GitHub (the app works on a phone), add a file here named `event-calendar-<year>.txt`, for example `event-calendar-2027.txt`.
2. Put the whole year in it, two lines, dates as YYYY-MM-DD, comma-separated, no spaces:

```text
NFP=2027-01-08,2027-02-05,...
FOMC_EVE=2027-01-26,2027-03-16,...
```

   NFP = jobs-report (Employment Situation) release days; FOMC_EVE = the first day of each two-day Fed meeting.
3. Commit it. The service publishes it within minutes (a change here starts the job) and the bots pick it up at their next
   30-minute check. Copy the current lines from https://calendar.knyawcapital.com/event-calendar-<year>.txt and change only
   the date that moved.

The file must still look like a real year (10 to 13 jobs reports, 7 to 9 FOMC eves, weekdays in that year), or it is ignored.
While it differs from what the sources show, every run warns (team phone alert) so it is not forgotten. Delete it once the
sources show the right dates.
