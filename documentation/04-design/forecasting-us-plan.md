# Road risk for the whole US (Plan, step A)

**Status:** **Approved 2026-11-05** (owner: "ok go ahead"; US-D1–D4 as suggested). Owner: "lets move to part 2" (2026-11-05).
**Goal:** every US project gets more than today, and big cities that publish pothole reports get tested levels like Chicago — free data only, as little storage as possible.
**Rules unchanged:** `forecasting-f0-ground-rules.md` (tested levels only after a locked test; levels only, never percentages; TRIAL label; pass marks PLACEHOLDER until PI-20).

## 1. What changes for users

| Place | Today | After this plan |
|---|---|---|
| Chicago | Tested levels (Level 2) | Same, plus measured road condition on main roads |
| Cities added below that **pass** their test | Risk factors (Level 1) | **Tested levels, like Chicago** |
| Cities added that fail their test | Risk factors | Risk factors + measured condition; stay Level 1 |
| Everywhere else in the US | Risk factors | Risk factors + **measured road condition and traffic on main roads (HPMS)** |

Places with no published pothole history can never be tested, so they never get tested levels.

## 2. Free data

| Data | Source | Covers | Use |
|---|---|---|---|
| Road roughness (IRI), cracking, rutting; traffic per day | **HPMS** (FHWA), yearly, queried per project box | Main roads, all states | New "Level 1+" factors; replaces the Illinois-only traffic counts |
| Pothole reports | City open-data portals (Socrata, ArcGIS, CKAN, Carto) | Cities that publish | Level 2 history per city |
| Roads, weather, outlook, elevation, flood zones | OpenStreetMap, NOAA, NWS, USGS, FEMA (already used) | Whole US | Unchanged |
| Bus routes (optional, later) | Transit agencies' published GTFS files | Most cities | Replaces Chicago-only CTA routes |

Every source's terms are read and recorded before use (as for Chicago), and every report names its sources.

## 3. Storage rules (minimum)

1. **Per project, never per country:** each download asks only for the project's box.
2. **Raw files compressed after loading** (gzip) with their fingerprint kept in `manifest.json`; they can be downloaded again.
3. **Keep per-section summaries,** not raw rows, where the app does not need the rows.
4. **No large working files:** training tables are built in chunks and deleted after training; only the model file stays.
5. **One shared US model** trained on a sample of rows from every city.
6. Clean-up of today's Chicago working folders (`data/chicago/f2`, `f4a`, 2.9 GB) once the new model is in place (needs the owner's permission to delete).

Estimate: **50–150 MB per city project**, about **0.5 GB once** for the shared training sample and model.

## 4. Steps

| Step | What | Done when | Time |
|---|---|---|---|
| **A** | This plan; second reachability check (`scripts/national-check.bat`, round 2: where HPMS holds Illinois, Philadelphia's pothole name, New York with a date filter, Boston's files) | Owner approves the plan; check answers all questions | 1–2 days |
| **B** | **HPMS in the app:** download per project box, match to sections (15 m, same direction), new factors "road roughness", "cracking", "traffic"; shown with source and year; Level 1 cut-offs drafted from Chicago | Tests pass; Chicago and one non-Illinois project show the new factors | 2–3 weeks |
| **C** | **City connector:** one downloader for the 4 portal types + one settings file per city (dataset, columns, pothole type, terms); first 3 cities | Counts reconcile (downloaded = loaded + skipped) for 3 cities; data report per city | 2 weeks |
| **D** | About 6 more cities, 2–3 days each | ~10 cities loaded | 2–3 weeks |
| **E** | **Shared US model:** inputs made comparable between cities (e.g. reports here vs the city's average); trained on most cities; **locked test on whole cities kept aside** and on later months; per-city result | Each city's result recorded; only passing cities switch to tested levels | 2–3 weeks |

The owner runs the tests after each step and decides whether to go on. Every step can be the last one.

## 5. Decisions for the owner

| # | Question | Suggestion |
|---|---|---|
| US-D1 | First cities | **New York, Boston, Philadelphia** (or the partner's cities) |
| US-D2 | Raw files after loading | **Keep compressed** (can be deleted later) |
| US-D3 | Pass marks for new cities | **Same placeholders as Chicago** until PI-20 |
| US-D4 | Where it runs | **Laptop for steps B–C**; move to a server (P10: 4 CPU, 8 GB, 80–100 GB) before step D |

## 6. Known limits

- HPMS covers mainly main roads; most residential streets have no measured condition.
- A 311 report is a report, not an inspection; cities report differently, so each city is tested on its own.
- Free services can be slow (Overpass took 28 s in the check); downloads retry and run in the background.
- Nothing here changes the photo AI, which already works anywhere.

## 7. First check (2026-11-05, round 1)

Laptop: 97 GB free disk, 7 GB memory for Docker. HPMS service, Boston, Philadelphia, NOAA, NWS and OpenStreetMap answered; New York timed out (whole-history count); HPMS returned 0 pieces for the Chicago box and Philadelphia 0 "pothole" requests — question wording, checked again in round 2.
