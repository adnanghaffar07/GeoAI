# Forecasting F0: Ground Rules

**Status:** **APPROVED 2026-10-28** by the owner ("ok go ahead"). CR-005 (start the forecasting track) approved the same day ("ok lets start this phase"). Sections 2–7 are now **frozen**: any change needs a line in `project-decisions.md` with the reason (change control), so the goalposts never move after we see results. Pass marks stay **PLACEHOLDER** until the partner confirms them (PI-20).
**Source:** `04-design/forecasting-roadmap.md` (phases F0–F6), the research deck in this folder, data checks of 2026-10-27/28.
**Machine-readable copy of the measures and pass marks:** `ml/forecasting/config/acceptance-thresholds.yaml`.

## In plain words

Before downloading or training anything we write down:
1. **what exactly the forecast predicts** (and how we know the right answer for the past),
2. **what it may look at** (only things known before the forecast date, so it cannot "cheat"),
3. **how we test it** (on later years it never saw), and
4. **the pass mark**, compared with simple rules a city could use without AI.

The first version is a **proof of concept on the City of Chicago**, because Chicago publishes dated, located pothole reports going back to 2011. The suburbs (Naperville, Aurora, Oswego) follow in F3 once their data is available.

---

## 1. Sub-steps of the forecasting track

| Step | What | Owner action | Output |
|------|------|--------------|--------|
| **F0** | Ground rules (this document) | Approve sections 2–7 | This document + thresholds file |
| F1 | Data pipeline for Chicago | Confirm licences, run the download notebook/script | Data in a separate database, dataset card, counts |
| F2 | Proof of concept: baselines + main model, one locked test | Read the report | Test report + model card |
| F3 | Suburbs | Get city data (PI-21) | Suburb report |
| F4 | App integration (incl. manager-only in-app alerts) | Try the screens | Trial forecast in the app |
| F5 | Field pilot (one winter) | Run with the partner | Pilot report |
| F6 | Sign-off | Sign off | Documents |

## 2. What we predict (the target)

| Item | Rule |
|------|------|
| **Question** | "Will at least one **new pothole** be reported on this road section in the **next 30 days**?" (yes / no, given as a probability) |
| **Forecast date** | Every **Monday**; the forecast uses only information available before that Monday |
| **Horizon** | **30 days** (Monday plus the following 29 days). 60 and 90 days are reported later, not used for pass/fail |
| **"New pothole" in Chicago (F2)** | A City of Chicago 311 request of the pothole type, **created** in the horizon, **located within 20 m** of the section's centre line, not marked as a duplicate |
| **Suburbs and the app (F3+)** | A **verified** pothole or road finding, or an inspection outcome "damage found", in the horizon |

Why potholes: they are the damage type with dated, public, located records. Cracking and general deterioration are added when city condition surveys (PI-21) or GeoInfraLens findings provide dated labels.

## 3. The unit: road sections

| Item | Rule |
|------|------|
| Road network | OpenStreetMap, one dated extract, licence ODbL (credit + share-alike for derived databases) |
| Included road types | `primary`, `secondary`, `tertiary`, `residential`, `unclassified` and their `_link` roads |
| Excluded | `motorway`, `trunk` (state expressways, other maintainer), `service`, alleys, footways, private roads |
| Sections | Roads split at intersections, then into pieces of about **100 m** (shorter end pieces kept if 30 m or longer). *Clarified in F1, 2026-10-28 (not a change): a leftover under 30 m is joined to the last section, so sections are 30–129 m; a whole piece between intersections under 30 m is not a section* |
| Area | City of Chicago boundary (F2) |
| Coordinates | Stored in EPSG:4326; lengths and distances computed in meters (geography or a projected system, e.g. EPSG:26916 UTM 16N) |

## 4. What the model may use (inputs) and the no-cheating rule

**No-cheating rule (leakage):** every input for a forecast made on Monday *D* uses only data **dated before D**. Nothing from the 30-day horizon is ever an input. Static layers (elevation, soil, flood zone, road type) are allowed because they do not depend on the horizon; their date is recorded.

| Group | Inputs (starting list; F1 may add, never inputs from the horizon) |
|-------|------------------------------------------------------------------|
| Weather (nearest station(s), NOAA GHCN-Daily) | freeze–thaw cycles in the last 7 / 14 / 30 days (a day with max above 0 °C and min below 0 °C), days below freezing, rain and snow totals (7 / 30 days), heavy-rain days (≥ 25 mm), extreme-heat days, days since last freeze |
| Damage history | pothole reports on this section and on neighbouring sections (within 200 m) in the last 30 / 90 / 365 days, and in the same season last year |
| Road | road type, length, number of lanes if mapped, surface if mapped |
| Use | traffic per day where IDOT / HPMS has it (missing flagged, not guessed) |
| Place | slope and low points (USGS 3DEP), flood zone (FEMA NFHL), soil drainage class (USDA SSURGO) |
| Season | week of year, month |

**Missing values** stay missing and are flagged (the model handles them); they are never filled with made-up numbers. Each input's coverage is reported in F1.

## 5. How we test (frozen once F0 is approved)

| Item | Rule |
|------|------|
| **Training period** | Forecast dates from 2012-01-02 to 2021-06-28 (2011 used only as history for the first inputs) |
| **Validation period** | 2021-07-05 to 2022-06-27 (one full season): used to choose settings and the probability calibration |
| **Test period (locked)** | 2022-07-04 to 2025-06-30 (three seasons). Used **once**, after all choices are fixed. A usage log blocks running it twice (as in P8.5) |
| **Place check** | 10 Chicago community areas chosen by a fixed random seed are left out of training entirely; test results are also reported for them alone |
| **Data change to note** | Chicago changed its 311 system on 2018-12-18; F1 checks that pothole counts per week are comparable before and after, and the report states it |
| Gaps | Weeks with missing weather or report outages are reported, not silently dropped |

## 6. Models and measures

**Models (simplest first):**

| Name | What |
|------|------|
| B0 Rule | Rank sections by pothole reports in the last 90 days, ties broken by freeze–thaw cycles in the last 14 days. A rule a city could use without AI |
| B1 Logistic regression | Transparent statistical baseline on the same inputs |
| M LightGBM | Main model, probabilities calibrated on the validation period, per-section factor contributions for the "why" |

**Measures (reported on validation and on the locked test, overall, for winter months Nov–Apr, and for the held-out community areas, each with 95% bootstrap ranges):**

| Measure | Meaning in plain words |
|---------|------------------------|
| **Precision at top 1%** (averaged over forecast weeks) | Of the 1% of sections ranked riskiest each week, how many really got a new pothole report |
| **Recall at top 10%** | How much of all new pothole reports the riskiest 10% of sections covered |
| **PR-AUC** | Overall ranking quality when "yes" cases are rare |
| **Brier score** and calibration chart | Whether "30% risk" happens about 30% of the time |
| Base rate | Share of section-weeks with a new report (to read the other numbers against) |

## 7. Pass marks (PLACEHOLDER until the partner confirms PI-20)

The main model **passes F2** only if, on the locked test period, all of these hold:

1. Precision at top 1% is at least **1.15 ×** the best baseline (B0 or B1), and the lower end of its 95% range is above the baseline's value.
2. PR-AUC is at least **1.15 ×** the best baseline.
3. Brier score is **better** than both baselines.
4. In winter months (Nov–Apr), precision at top 1% is **not lower** than the best baseline.
5. In the held-out community areas, precision at top 1% is at least **1.0 ×** the best baseline (no worse than the simple rule in places it never saw).

**Outcomes:** all pass → the model may go into the app as a labelled TRIAL FORECAST (F4) and to the field pilot (F5). Some pass → owner decides (partial pass, recorded in `project-decisions.md`). None pass → report honestly, improve inputs or targets, and run a **new** locked test period later; the test period is never reused for tuning.

## 8. Data sources and licences

| Source | Licence / terms | Status |
|--------|-----------------|--------|
| NOAA GHCN-Daily | CC0 public domain; attribution requested | Confirmed 2026-10-27 |
| National Weather Service API (forecasts, F4 alerts) | Free, "open data, free to use for any purpose"; requires an identifying User-Agent; unpublished rate limit | Confirmed 2026-10-28 |
| OpenStreetMap | ODbL: credit, share-alike for derived databases | Known; record extract date |
| City of Chicago 311 pothole requests, community areas | City of Chicago Data Portal Terms of Use: public data "as is"; the City may require naming the source and version (Open Data Executive Order 2012-2) | **Owner reads the terms before the first download**; the download refuses Chicago data without `--chicago-terms-confirmed` and records the time in `manifest.json` |
| Cook County DOTH pavement condition (2025, six suburban townships) | No licence stated on the service | **Checking only** (not a label, not in the product) until CCDOTH agrees in writing (PI-23) |
| USGS 3DEP elevation | US government public data | Confirm on download |
| FEMA NFHL | Public services; fees or terms not stated | Confirm on download |
| USDA SSURGO | Free download | Confirm on download |
| FHWA HPMS / IDOT traffic | Public; licence wording not stated | Confirm on download |

Every layer's source, download date and licence go into the F1 dataset card. No layer is republished in the app beyond what its licence allows.

## 9. Privacy

- From 311 records we keep only: request type, created date, status (duplicate or not), latitude and longitude. Street address text, ward, and any free-text fields are dropped at download.
- No personal data is used. Client photos are not used in F1–F2.

## 10. Where the work happens

| Item | Decision |
|------|----------|
| Code | `ml/forecasting/` with its own `requirements-forecast.txt` (pandas, pyarrow, LightGBM, scikit-learn), separate from the app and from the photo model |
| Data preparation | A **separate PostGIS database** (`forecast`) in the same Docker PostgreSQL, so app data is never touched |
| Training | The owner's laptop (no GPU). Free Colab only if memory is short |
| Storage | About 3–6 GB on disk for Chicago; training data never committed to Git (only code, configs, reports, and the final model file with its fingerprint) |

## 11. Partner inputs added by this track

| ID | Input | Status | Needed before |
|----|-------|--------|---------------|
| PI-20 | Forecast pass marks (section 7) | PLACEHOLDER | F2 decision, F4 |
| PI-21 | Pavement condition ratings and repair history for Naperville, Aurora, Oswego | Not requested yet | F3 |
| PI-22 | Engineering check of the target ("new pothole within 30 days") and of the inputs | Academic / engineering partner | F2 report |

## 12. Owner decisions for F0

- [x] Target: new pothole report within 30 days, Monday forecasts (section 2) — approved 2026-10-28
- [x] Unit: 100 m sections of city-maintained road types (section 3) — approved 2026-10-28
- [x] Inputs and the no-cheating rule (section 4) — approved 2026-10-28
- [x] Training / validation / locked test periods and the place check (section 5) — approved 2026-10-28
- [x] Models and measures (section 6) — approved 2026-10-28
- [x] Placeholder pass marks (section 7) — approved 2026-10-28
- [ ] Who contacts the cities and the academic partner (PI-21, PI-22) — still open; needed before F3
