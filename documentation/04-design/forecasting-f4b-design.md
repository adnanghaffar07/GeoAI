# Forecasting F4b: App Database and Daily Jobs (Design)

**Status:** **Complete 2026-10-30** (approved: "ok go ahead", with B-D1 to B-D3; built in two parts, all tests passed, results in section 6). Written 2026-10-30.
**Builds on:** `forecasting-f4-plan.md` (approved 2026-10-30, F4-D1 to F4-D5), roadmap §7. Model: `forecast-chicago-0.2`, levels only (F4-D2).

## In plain words

F4b gives the app what it needs to show road risk, but no screens yet (F4d):

1. **New tables** in the app database for the results only: which projects use forecasting, each run, each road's level and reasons,
   the weather outlook, and alerts. Nothing existing changes (add-only migration **0009**).
2. **Automatic jobs** in the app's background worker: every day new weather and the 7-day forecast; every Monday new Chicago
   pothole reports and new Chicago risk levels; when forecasting is switched on for a project, the area is set up once.
3. **Small changes to the worker** so it can run the forecasting code.

## 1. Tables (app database, migration 0009, add-only)

| Table | Main columns | Notes |
|---|---|---|
| `forecast_settings` | project, enabled, level (1/2), area_key, status (setting_up / ready / failed / too_large), area_km2, last_weekly_run, last_daily_run, message | One row per project; created when a manager switches forecasting on |
| `forecast_sections` | area_key, section_key (the forecast's section id), name, road type, length_m, line (EPSG:4326) | The road pieces of an area, copied once per area; Chicago projects use the Chicago rows inside their area |
| `risk_runs` | project, kind (weekly_levels / daily_factors / outlook), as_of, model_version (`forecast-chicago-0.2` or `level1`), data_dates (JSON), status, message, started/finished | One row per job run and project; old runs are kept as history |
| `risk_levels` | run, section, rank, level (high/medium/low), reasons (JSON: top inputs with their values and contributions), missing inputs | Level 2 only. **No percentage column is filled** while F4-D2 says "levels only"; the raw value is kept in `monitor_value` for the monthly check (never shown) |
| `risk_factor_values` | run, section, factor, value, level, kind (risk/background) | Level 1 and 2: the same factors as the Level 1 report |
| `weather_outlooks` | project, issued_at, source (NWS office, grid), next 7 days per day: max/min °C, rain mm, snow mm; counts: freeze-thaw days, frost days, heavy-rain days | From api.weather.gov at the project's centre |
| `alerts`, `alert_reads` | As in roadmap §7.5 (type, title, details JSON, open/closed; who read it and when) | Filled in F4e; the tables come now so the migration is done once |
| `inspections.risk_level_id` | Optional link from an inspection to the level that suggested it | Feedback loop (roadmap §8) |
| `forecast_monitoring` | month, sections, predicted mean (raw B1), happened, gap, status | The monthly percentage check agreed in F4-D2 (never shown as a percentage to users) |

## 2. Jobs (Celery Beat, a new small `beat` container)

| When | Job | What it does |
|---|---|---|
| When switched on | `forecast.setup_area` | Project survey area becomes the area boundary; checks size (max 500 km², F4-D4); runs area check, downloads, load (the same code as `forecast-area.bat`); copies sections into `forecast_sections`. Chicago projects: no download, the Chicago area is used |
| Daily, 06:00 Chicago time | `forecast.daily` | New NOAA weather for each area's stations; NWS 7-day outlook for each project; Level 1 factors; (F4e) alert rules |
| Monday, 07:00 Chicago time | `forecast.weekly_chicago` | New Chicago 311 reports since the last one (only the new rows, same columns, same privacy rule); matches them to sections; computes that Monday's inputs; B1 `forecast-chicago-0.2` ranks every Chicago section; levels: top 1% high, next 9% medium (F4-D2); projects show their own sections |
| 1st of each month | `forecast.monitor` | Compares last month's raw B1 values with what happened (F4-D2 monthly check) |
| After any failure | (part of each job) | The run is marked failed with a plain reason; the next run catches up missed days (F4-D5); F4e turns this into a "data problem" alert |

**Check before use:** the new "inputs for one Monday" code must give exactly the same values as the learning table for past Mondays
(a test compares them, like the same-results check). Only then are weekly levels trusted.

## 3. Worker changes

- The `worker` and new `beat` containers get the forecasting code (`./ml` mounted, read-write for the forecast data folders) and its
  packages, **pinned to the versions that trained B1 on the laptop**: scikit-learn 1.9.1, numpy 2.5.4, scipy 1.18.1, joblib 1.6.0,
  shapely 2.2.0, pyproj 3.8.0, pyyaml 6.0.3. LightGBM is not needed (not chosen).
- The worker reaches the `forecast` database on the same PostgreSQL server (new setting `FORECAST_DATABASE_URL`, refuses the app database).
- The app only accepts the model file whose fingerprint matches `models/chicago/f4a-models.json` (like the trial photo model).
- Internet for the jobs: City of Chicago portal, NOAA, NWS (api.weather.gov, needs a contact in the User-Agent: `FORECAST_CONTACT_EMAIL`).

## 4. Tests

Backend tests (`docker compose exec api pytest`, run by a new `scripts\backend-tests.bat`): migration up/down, the tables' rules,
switching forecasting on and the size limit, levels from ranks (1% / 9%), the outlook counts from a saved NWS answer, catch-up after
missed days, and fingerprint refusal. Forecasting tests: the one-Monday inputs equal the learning table. All 240 existing backend tests must still pass.

## 5. Decisions for the owner

| # | Question | Suggestion |
|---|---|---|
| B-D1 | Job times | Daily 06:00, weekly Monday 07:00, Chicago time |
| B-D2 | Weather outlook point | The project's centre (one NWS grid point per project); large projects get the centre only for now |
| B-D3 | New Chicago reports | Download only rows newer than the last one, weekly, with the same columns (no address), under the terms you accepted |

## 6. Results (2026-10-30)

- **Part 1** (tables): migration 0009 applied on the owner's laptop (app database backed up first to `_backups/app-db-before-0009-forecasting.dump`). Weekly check PASSED: the one-Monday inputs equal the learning table on 5 Mondays. Backend tests 251 passed.
- **Part 2** (jobs): `ml/forecasting/nws.py`, `ml/forecasting/live.py`, `backend/app/services/forecasting.py`, `backend/app/workers/forecast_tasks.py`, new `beat` container (hourly tick that runs whatever is due: daily 06:00, weekly Monday 07:00, monthly check, catch-up after missed days; Chicago time), commands `forecast-enable` and `forecast-tick`.
- Tests on the owner's laptop: forecasting **74 passed** (`scripts\forecast-tests.bat`), backend **257 passed** (`scripts\backend-tests.bat`).
- Forecasting is **off** for every project until switched on. Nothing is shown in the app until F4d (screens).

