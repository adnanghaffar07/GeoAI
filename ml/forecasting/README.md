# ml/forecasting: road damage forecasting (V2 research track)

Separate from the photo model (`ml/training/`). For each ~100 m road section: **Level 2** (areas with pothole history,
Chicago first) the chance of a new pothole report in the next 30 days; **Level 1** (any US area) risk factors, never a
percentage.

- Plan: `documentation/04-design/forecasting-roadmap.md` (phases F0–F6); any-area step: `documentation/04-design/forecasting-any-area-plan.md`
- Ground rules (approved and frozen 2026-10-28): `documentation/04-design/forecasting-f0-ground-rules.md`
- Machine-readable rules and pass marks: `config/acceptance-thresholds.yaml` (pass marks PLACEHOLDER until PI-20)
- National data sources: `config/sources.yaml`; **one file per area**: `config/areas/<area>.yaml` (`chicago`, `naperville`)
- Level 1 cut-offs: `config/risk-factors.yaml` (drafted from Chicago's training years; DRAFT until the owner approves, D5)
- Dataset card: `documentation/07-ml/dataset-card-chicago-forecast.md`; model card: `documentation/07-ml/model-card-forecast-chicago.md`

Status (2026-10-29): F0–F2 complete for Chicago (locked test PARTIAL; **B1 chosen** for the app; the locked test cannot be
run again, `reports/chicago/f2-test-usage.json`). **Any-area step (FA) complete 2026-10-30**: 65 tests pass, Chicago
same-results check PASSED, Level 1 cut-offs approved (two groups), Naperville Level 1 trial done.
Training data is never committed to Git (`data/` is git-ignored). Reports hold only counts and may be committed.

## Layout: one folder set and one database schema per area

| What | Where |
|------|-------|
| Raw downloads + `manifest.json` | `data/<area>/raw/` |
| Learning table (Level 2) | `data/<area>/f2/` |
| Models with fingerprints (Level 2) | `models/<area>/` |
| Reports | `reports/<area>/` |
| Database tables | schema `<area>` of the separate `forecast` database (PostGIS stays in `public`) |
| NOAA station lists (shared) | `data/_national/` |

Chicago's files and tables were moved into this layout once with `move-to-areas` (nothing changed, only moved).

## Commands (from the ml/ folder; `--area` defaults to chicago)

| Step | Command | Result |
|------|---------|--------|
| Area check | `python -m forecasting.run --area naperville area-check` | Boundary, weather stations (rule D3), roads; `reports/<area>/area-check.md` says Level 1 or 2 |
| Download | `python -m forecasting.run --area naperville download` (`--terms-confirmed` for city portal data) | Raw files in `data/<area>/raw/` |
| Load | `python -m forecasting.run --area naperville load` | The area's schema: road sections, districts or boundary, (311 reports), weather, static layers |
| Level 1 | `python -m forecasting.run --area naperville level1` | Table `section_risk_factors` and `reports/<area>/level1-risk-factors.md` |
| F1 report (Level 2) | `python -m forecasting.run report` | `reports/chicago/f1-data-report.md` |
| F2 (Level 2) | `f2-build`, `f2-train`, `f2-test --owner-go-ahead --main-model without_traffic` | Learning table, models, validation and (once) test reports |
| One-time move | `python -m forecasting.run move-to-areas` | Old one-area folders and tables into the `chicago` area |
| Same-results check | `python -m forecasting.run same-results-check` | Reloads, rebuilds and re-scores Chicago with this code; `reports/chicago/same-results-check.md` |
| Level 1 cut-offs | `python -m forecasting.run risk-cutoffs-draft` | `config/risk-factors.yaml` (DRAFT) and `reports/chicago/risk-factor-cutoffs-draft.md` |

On Windows the owner uses the double-click scripts in `scripts\`: `forecast-f1.bat`, `forecast-f2.bat`,
`forecast-tests.bat`, `forecast-area-check-chicago.bat`, `forecast-area.bat`. Each reads the database password from `.env`.

- Running a step again is safe: downloads skip files already there (`--force` to fetch again, `--only osm_roads` for one item),
  and a load replaces that area's previous load in one transaction.
- If a website is busy (HTTP 429/5xx) the download waits and retries 3 times. If a portal renamed a column, it stops and
  names it: fix the area file or `config/sources.yaml`, not the code.
- The app database is never touched; the commands refuse a database named `geoinfralens`.

## A new area

Add `config/areas/<name>.yaml` with a `name`, `level: 1` and a `boundary` (an OpenStreetMap boundary relation filter, as in
`naperville.yaml`, or `geojson_file:` with a polygon, e.g. a project's survey area). Optional: `traffic_counts: idot` (Illinois),
`bus_routes`, and city datasets via a `portal`. Weather stations are chosen automatically (`weather_stations: auto`).
A Level 2 area also needs its pothole history, districts with a held-out rule (D4), and its own training and locked test.

## Tests

`scripts\forecast-tests.bat` runs all forecasting tests on the laptop, including the database tests in a throwaway
database `forecast_test` (`FORECAST_TEST_DATABASE_URL`). Output: `ml\forecast-tests.log`.
