# Forecasting: Any-Area Pipeline Plan (step "FA", between F2 and F4)

**Status:** **Complete 2026-10-30** (approved 2026-10-29 with D1–D5; results in section 7). Written 2026-10-29 after F2 (locked test PARTIAL; B1 chosen, `07-ml/model-card-forecast-chicago.md`).
**Builds on:** roadmap §7.7 "Two levels for any project area" (`forecasting-roadmap.md`), F0 rules (`forecasting-f0-ground-rules.md`, frozen).

## In plain words

Today the forecasting code only knows Chicago: its 311 datasets, its community areas, its two airport weather stations and its map zone are written into the code and settings. This step moves everything about a place into **one small "area file"**, so the same code can run for **any US area**:

- **Every area** gets **Level 1 "risk factors"** from free national data: weather (freeze–thaw, heavy rain, snow), low spots and slope, flood zones and road type, plus traffic and bus routes where they are published. They are shown as factors, **never as a percentage**.
- **Areas with pothole history** (only Chicago for now) also get the **Level 2 tested forecast** (B1).

**Chicago must give exactly the same results as today.** No new model is trained in this step, and nothing is shown in the app yet (that is F4).

## 1. What changes

| Today (Chicago only) | After this step |
|---|---|
| Chicago datasets, box, OpenStreetMap boundary, stations, bus routes, Cook County check in `config/sources.yaml` and `f2.yaml` | One file per area: `config/areas/chicago.yaml`. `sources.yaml` keeps only the **national** sources (NOAA, USGS, FEMA, USDA, OpenStreetMap) |
| Map zone UTM 16N (EPSG:26916) written into the code | Chosen from the area's centre (Chicago is still 16N) |
| Hand-typed Chicago box | Worked out from the area's boundary |
| Weather stations listed by hand | Chosen automatically by a fixed rule (decision D3); Chicago keeps O'Hare and Midway, with snow from O'Hare |
| Held-out places = Chicago community areas | Area file says which districts to hold out (Chicago: the same 10 community areas) |
| One set of folders (`data/`, `models/`, `reports/`) | A sub-folder per area (`data/chicago/`, `models/chicago/`, `reports/chicago/`). Chicago's existing files are **moved, not changed**, so their fingerprints and the test lock stay valid |
| Database tables for Chicago only | One database schema per area inside the `forecast` database (decision D1). Chicago's tables are moved into a `chicago` schema without changing any data |
| Commands assume Chicago | Every command takes `--area` (default `chicago`, so the existing scripts keep working) |

**Area boundary** can be given three ways: an OpenStreetMap place (as Chicago is now), a GeoJSON file, or later (in F4) a project's survey area from the app.

## 2. New pieces

1. **`area-check` command.** Given an area, it reports in plain words what is available: road length and number of sections; nearest weather stations and how complete they are; flood, elevation and soil coverage; whether traffic, bus routes or pothole history exist. It then says **Level 1** or **Level 2**. It downloads nothing large.
2. **Level 1 risk-factor table** (`risk_factors.py`). For every section and day it gives the factor values that already feed the forecast:
   - recent freeze–thaw days, days below freezing, heavy-rain days, snow
   - low spot, slope, flood zone, probable bridge
   - road type, lanes, traffic band and bus routes (or "missing")

   Each factor gets a plain label such as "many freeze–thaw days" using fixed, written-down cut-offs (decision D5). **No percentage and no model.**
3. **Level 2 stays Chicago only**, with the same B1 files and fingerprints. Adding another Level 2 city later needs its own data, training and locked test (as in F2), which is outside this step.

## 3. Checks (how we know nothing broke)

1. **Chicago, same results (on the laptop):** rebuild the sections and the learning table with the new code, then compare with today's files:
   - number of sections and the fingerprint of every section shape
   - checksums of every learning-table array
   - the validation results of the **existing** B0, B1 and LightGBM files, which must match `f2-validation-report.json` to the last digit

   The locked test is **not** run again (it is used up); its files are only moved.
2. **Trial Level 1 area (decision D2):** run `area-check` and the Level 1 build for one area outside Chicago, then read the plain-words report together.
3. **Tests in Claude's workspace:** loading area files; boundary → box and map zone; station choice; "missing" when a layer does not exist; a small made-up area from start to finish; the Chicago area file giving the same settings as today's `sources.yaml`/`f2.yaml`. The existing 49 forecasting tests must still pass.

## 4. Steps and owner actions

| Step | What | Owner action | Time |
|---|---|---|---|
| FA1 | Area files, `--area` option, per-area folders and schema; move Chicago files and tables | Approve this plan | ~2 days (Claude) |
| FA2 | `area-check`, automatic station choice, map zone from centre | — | ~1 day |
| FA3 | Level 1 risk-factor table | Agree the cut-offs (D5) | ~1 day |
| FA4 | Tests here, then the Chicago "same results" check on the laptop | Double-click `scripts\forecast-area-check-chicago.bat` | ~30–45 min on the laptop |
| FA5 | Trial Level 1 area | Double-click `scripts\forecast-area.bat` and choose the area | ~10–20 min on the laptop |
| — | Record results; update docs and the Project | Read the reports with Claude | — |

About **1 week** in total. A copy of Chicago's data, models and reports is saved in `_backups/` before anything is moved.

## 5. Not in this step

- Showing anything in the app, daily jobs, NWS weather forecasts, alerts → **F4**.
- Suburb pothole or repair data → **F3** (waits for PI-21).
- Training a new model, a B1 without traffic, or re-calibrating probabilities on recent data → separate, later steps (model card §7–8).
- Changing any F0 rule or pass mark.

## 6. Decisions for the owner

| # | Question | Suggestion |
|---|---|---|
| D1 | How to keep areas apart in the database | **One schema per area** in the `forecast` database (Chicago moved into `chicago`). Simple to delete or rebuild one area; no change to Chicago's data. Alternative: an "area" column on every table |
| D2 | Which area for the Level 1 trial | **Naperville**: a suburb we want for F3 anyway, and it has no pothole history, so it is a true Level 1 test |
| D3 | Rule for choosing weather stations | Stations within **30 km** with at least **90%** of days for temperature and rain over the last 10 years; snow from the station with the most complete snow record (the rule that picked O'Hare) |
| D4 | Held-out places for a future Level 2 city | The city's own districts if published; otherwise squares of about 2 km picked with a fixed seed. Only needed when a new Level 2 city is added |
| D5 | Cut-offs for the Level 1 labels | Drafted in FA3 from Chicago's training years only, written in a settings file, and shown to the owner before use |

## 7. Results (2026-10-30, owner's laptop)

- **Tests:** all 65 forecasting tests pass, including the database tests (`scripts\forecast-tests.bat`). A database connection that hung on Windows/Docker was fixed: the scripts use `127.0.0.1`, and every connection has a 20-second limit and 3 tries.
- **Move:** Chicago's 12 tables moved into schema `chicago`; its data, models and reports into `data/chicago`, `models/chicago`, `reports/chicago`. Database backup first: `_backups/forecast-db-before-any-area-2026-10-29.dump`.
- **Chicago same-results check: PASSED** (`ml/forecasting/reports/chicago/same-results-check.md`): all 11 tables, all 79 learning-table items and all 4 models' validation scores identical. The first run found 93 of 71,979 sections with a different nearest weather station (the safer search measured on the earth's oval shape instead of a sphere); fixed by measuring on a sphere as the F2 build did.
- **Level 1 cut-offs (D5):** drafted from Chicago's training years (`ml/forecasting/reports/chicago/risk-factor-cutoffs-draft.md`). Only 4 of 10 factors were followed by more reports in Chicago. **Owner decision (option 1):** risk factors = freeze-thaw days, days below freezing, snow, bus routes; background information without a warning level = heavy rain, dips, slope, flood zone, traffic, heavy vehicles. `config/risk-factors.yaml` APPROVED.
- **Naperville Level 1 trial** (`ml/forecasting/reports/naperville/area-check.md`, `level1-risk-factors.md`): boundary 110 km²; 11,697 road sections; stations Lisle–Morton Arboretum, Aurora Water, Romeoville (snow) chosen by rule D3 (O'Hare passed too but is farther; West Chicago and Aurora airports fail on snow, Joliet on completeness); traffic counts on 24% of sections; no bus data (missing). As of 2026-10-28: no frost or snow yet (all low); two heavy-rain days on 30 Sep–2 Oct at all three stations; 219 sections in a 1% flood zone.
