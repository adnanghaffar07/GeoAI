# Forecasting F4: Forecasts and Risk Factors in the App (Plan)

**Status:** **Approved 2026-10-30** (owner: "ok i approve", with F4-D1 to F4-D5). Written 2026-10-30, after the any-area step (`forecasting-any-area-plan.md`).
**Builds on:** roadmap §7 (database, jobs, API, screens, alerts; alert decisions of 2026-10-28) and §7.7 (two levels).
Model card: `07-ml/model-card-forecast-chicago.md`. Level 1 cut-offs: `ml/forecasting/config/risk-factors.yaml` (approved 2026-10-30).

## In plain words

Project managers will see road risk **inside the app**, on the project map, for their project area:

- **Chicago projects (Level 2):** each road section gets a **risk level** (high / medium / low) from the tested B1 model, with the reasons.
  A **percentage** is shown only if the refresh check in step F4a passes.
- **Every other US project (Level 1):** the **risk factors** (freeze-thaw, frost days, snow, bus routes) and the **background
  information** (heavy rain, dips, slope, flood zone, traffic), never a percentage.
- Every day the app uses the **weather forecast** (US National Weather Service) to warn managers **before** a freeze-thaw spell or heavy rain.
- Alerts go to **project managers only, in the app only** (bell and list), as decided on 2026-10-28.

Everything stays labelled **TRIAL** and **"risk estimate, not a confirmed defect"**. People still decide what to inspect.

## 1. Steps

| Step | What | Owner action | Time |
|---|---|---|---|
| **F4a** | **Refresh the Chicago model** (see section 2): check B1 on the 15 never-used months, retrain on all data, re-check the percentages | 2 double-click runs on the laptop (~20-40 min each); decide percentages or levels | 2-3 days |
| F4b | **App database and daily jobs**: add-only migration 0009 (tables in section 3); Celery Beat jobs: daily weather, weekly Chicago scores, NWS forecast, alert rules | Approve the table list | ~1 week |
| F4c | **API and permissions**: `risk.view`, `risk.configure`, `alert.view` (section 4) | Approve the permission keys | 3-4 days |
| F4d | **Screens**: "Road risk" tab with map and "Inspect first" list, weather strip, settings switch, export | Try it on the live demo | ~1 week |
| F4e | **Alerts**: bell with count, list, detail page, Home "What to do next" | Try it on the live demo | 3-4 days |
| F4f | **Tests and owner check**: backend and frontend tests, a guided test like P5-P7 | Test with the guide; sign off | 2-3 days |

About **4 weeks** in total. Each step is shown to the owner before the next starts.

## 2. F4a: refresh the Chicago model before any percentage is shown

1. **Fresh check on unseen months.** The Chicago data downloaded on 2026-10-28 already holds reports after the locked test
   (July 2025 - September 2026, about 15 months, never used). Score the **existing** B1 (`forecast-chicago-0.1`) on them:
   precision at top 1%, recall at top 10%, PR-AUC, Brier, calibration, for all sections, winter and held-out areas.
   This is an extra, honest check that the forecast still works now. It is not a new pass/fail test of F0 (that test is used up);
   it is reported as "fresh check" next to the locked-test results.
2. **Retrain** B1 with the same settings and inputs on all Mondays up to the latest complete 30-day window, as `forecast-chicago-0.2`
   (new fingerprints, model card updated). LightGBM is not retrained (not chosen).
3. **Re-check the percentages** on the most recent complete year with a simple calibration (isotonic, as in F2), fitted on the year
   before it, so the check is not on the same months it was fitted on.
4. **Decision for the owner:** if the fresh check holds up (precision at top 1% clearly above the simple rule B0) and the
   percentages are close (each tenth within about 2 points of what happened), show percentages for Chicago; otherwise show only
   the high / medium / low levels and the reasons.

**F4a done 2026-10-30:** fresh check holds up (B1 0.315 vs simple rule 0.238 at top 1%); calibrated percentages missed the 2-point rule (2.5), raw were within 1.3. Decision: **levels only**, monthly comparison of raw percentages with outcomes; app model `forecast-chicago-0.2` without calibrator.

## 3. Database (app database, add-only migration 0009)

| Table | Holds |
|---|---|
| `forecast_settings` | Project, forecasting on/off, level (1 or 2, set by the area check), area key in the forecast database, last run |
| `risk_runs` | Project, run date, kind (weekly score / daily weather / forecast weather), model version or "Level 1", data dates, status, message |
| `risk_scores` | Run, road section (id, name, line), Level 2: rank, level (high/medium/low), percentage (only if approved in F4a); top reasons with their values; missing inputs |
| `risk_factors_app` | Run, road section, factor, value, level, kind (risk / background), as in the Level 1 report |
| `weather_outlook` | Project, issued at, next 7 days: forecast freeze-thaw days, frost days, heavy-rain days, snow (from NWS) |
| `alerts`, `alert_reads` | As in roadmap §7.5 |
| `inspections.risk_score_id` | Optional link from an inspection to the score that suggested it (feedback loop, roadmap §8) |

The heavy data (roads, weather history, map layers) stays in the separate `forecast` database, one schema per project area,
exactly as the any-area code does now. Only the results the screens need are copied into the app database.

## 4. Background jobs, API, permissions

- **Area setup** (when a manager switches forecasting on): the project's survey area becomes the area's boundary (`geojson_file`),
  then area check, download, load (the same code as `forecast-area.bat`). Chicago projects reuse the Chicago area and pick the
  sections inside the project.
- **Daily (Celery Beat, early morning):** new NOAA weather; NWS 7-day forecast for each project; Level 1 factors; alert rules.
- **Weekly (Monday, as the model was trained):** Chicago B1 scores for all sections; projects show the ones inside their area.
- **If the computer was off** (the backend still runs on the laptop until P10), missed days are caught up on the next start, and a
  "data problem" alert says the forecast is old.
- API under `/api/v1` as in roadmap §7.3 and §7.5 (risk, risk history, weather summary, notifications), plus
  `PUT /projects/{id}/forecast-settings`. Permission keys: `risk.view` (managers, reviewers, viewers), `risk.configure` and
  `alert.view` (project managers).

## 5. Alert rules (starting values, configurable and documented like the priority weights)

| Alert | Level 2 (Chicago) | Level 1 (other areas) |
|---|---|---|
| Section turns high | Section moves into "high" in the weekly score | - |
| Freeze-thaw coming | NWS forecast: 3 or more freeze-thaw days in the next 7, on sections at medium or high | Same forecast rule, for the whole project, listing sections with dips or in flood zones as background |
| Heavy rain coming | 25 mm or more forecast in a day, on sections at medium or high | Same, for the whole project |
| Data problem | Weather download, forecast or score failed, or many inputs missing | Same |

One alert per event and project, with all affected sections; no repeats while it is open (roadmap §7.5).

## 6. Not in F4

- Email or SMS alerts (later; needs an email provider).
- A percentage for any area other than Chicago (needs local history and its own test; F3 or the app's own inspections).
- Horizons other than 30 days (only 30 days was trained and tested).
- Using forecast risk inside the inspection priority score (roadmap §7.6, later).

## 7. Decisions for the owner

| # | Question | Suggestion |
|---|---|---|
| F4-D1 | Where the forecasting jobs run | **In the existing Celery worker**, using the `ml/forecasting` code as a package, with the separate `forecast` database for heavy data and only results in the app database |
| F4-D2 | What Chicago shows | **Levels (high = top 1% each week, medium = next 9%, low = the rest)** always; **percentages only if F4a passes** |
| F4-D3 | Weather-coming thresholds | 3+ forecast freeze-thaw days in the next 7 days; 25 mm+ rain forecast in a day |
| F4-D4 | Largest project area for Level 1 | 500 km² (Naperville is 110 km²), so downloads stay a few minutes |
| F4-D5 | Running while the laptop is off | Accept catch-up on the next start until always-on hosting (P10); the screens show "last updated" and old forecasts are flagged |
