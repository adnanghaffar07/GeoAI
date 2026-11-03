# Forecasting F4e: Automatic Alerts (Design)

**Status:** **Approved 2026-11-02** (owner: "ok i approve", E-D1 to E-D4 as suggested). **Built 2026-11-02:** part 1 rules (`backend/app/services/alerts.py`, run after every hourly tick; thresholds in `.env`: `FORECAST_ALERT_FREEZE_THAW_DAYS`, `FORECAST_ALERT_RAIN_MM`, `FORECAST_ALERT_DAILY_STALE_DAYS`, `FORECAST_ALERT_WEEKLY_STALE_DAYS`); part 2 screens (Alerts menu item with unread count, Alerts page, alert page that marks read, Home "What to do next", Open alerts box in the Road risk tab); API `GET /notifications/{id}`, `POST /notifications/read-all`, `manages_projects`. Backend 282 passed.
**Builds on:** roadmap §7.5 (alert decisions of 2026-10-28), `forecasting-f4-plan.md` §5 (alert rules), F4b tables
`alerts` / `alert_reads` (already in the database), F4c API (`/notifications`, `/projects/{id}/alerts`), F4d screens.
Levels only (F4-D2): alerts never show a percentage.

## In plain words

The app tells **project managers** by itself when something needs attention; nobody has to open the Road risk
tab and look. In the app only: a **bell with a count** in the top bar, a **notifications list**, an **alert
page** with the roads and reasons, and an item in Home **"What to do next"**. No email, no SMS.

## 1. When an alert is created (checked after every daily and weekly job)

| Alert | Rule | Chicago (Level 2) | Other areas (Level 1) |
|---|---|---|---|
| **Road turned high** | A road is **high** this Monday and was not high last Monday | Yes, one alert listing all such roads | No (no weekly levels) |
| **Freeze-thaw coming** | NWS outlook: **3 or more** freeze-thaw days in the next 7 | Lists the project's **high and medium** roads | Lists roads with a high freeze-thaw, low-spot or flood-zone factor |
| **Heavy rain coming** | NWS outlook: a day with **25 mm or more** in the next 7 | Lists high and medium roads | Lists roads in low spots or flood zones |
| **Data problem** | A job failed, or levels are more than **8 days** old, or the daily update more than **2 days** old | Yes | Yes |

- **One alert per event and project**, listing all affected roads; it is not repeated while it is open.
- Alerts **close by themselves** when the event is over (the forecast days have passed, the next Monday
  replaces "turned high", a successful job ends a data problem). Closed alerts stay in the history.
- The roadmap's "sharp jump" rule is **left out**: it needs percentages, and F4-D2 says levels only.

## 2. What every alert shows

1. Title and project, e.g. "Freeze-thaw coming: 6 roads at high or medium risk".
2. **When**: the dates of the weather event, the source ("National Weather Service, issued …").
3. **Each road**: name, level (and last week's level for "turned high"), the main reasons in plain words,
   missing inputs. Buttons **Open** (road page) and **Plan inspection**.
4. **Suggested action**, e.g. "Inspect these roads before Friday 6 November".
5. **Model and data**: model version, TRIAL FORECAST label, data dates; and "Risk estimate, not a confirmed defect."

## 3. Who receives them

Project managers of the project (`alert.view`). Org admins see a project's alerts when they open it (Road risk
tab), and in the bell only for projects where they are a project manager. Read/unread is kept per person.

## 4. Screens

| Where | What |
|---|---|
| Top bar | **Bell** with the number of unread alerts (project managers only); click → notifications list |
| Notifications page | All my alerts, newest open first; unread in bold; "Mark all as read" |
| Alert page | Everything in section 2 |
| Home "What to do next" | "Freeze-thaw coming: 6 roads in Wicker Park → See them" for each unread open alert |
| Road risk tab | An **Alerts** box at the top with the project's open alerts (no new tab) |

## 5. Tests

Backend: each rule (creates once, no repeat while open, closes by itself), Level 1 vs Level 2 contents,
data-problem rules, no percentage in any alert, only managers receive them. Frontend: bell count, list, alert
page, mark read, Home item. All existing backend (277) and frontend (99) tests must still pass.

## 6. Decisions for the owner

| # | Question | Suggestion |
|---|---|---|
| E-D1 | Freeze-thaw and rain thresholds | **3 freeze-thaw days in 7; 25 mm in a day** (the F4 plan), in a settings file so they can change later |
| E-D2 | "Sharp jump" alert | **Leave out** (needs percentages) |
| E-D3 | Project alerts list | **Inside the Road risk tab** (no eighth tab) |
| E-D4 | Closing | **Automatic** when the event is over; managers can also mark read |

## 7. Time

About 3-4 days, in two parts tested on the laptop: **part 1** alert rules in the background jobs
(`backend-tests.bat`); **part 2** bell, list, alert page, Home item (`frontend-tests.bat`), then your check.
