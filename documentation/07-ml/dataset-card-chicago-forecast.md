# Dataset Card: Chicago forecasting data (F1)

**Status:** **F1 complete for Chicago, 2026-10-29.** The owner downloaded and loaded the data on the laptop on 2026-10-28 (`scripts/forecast-f1.bat`); counts below come from `ml/forecasting/reports/chicago/f1-data-report.md`. Cook County pavement condition (checking only) downloaded and loaded 2026-10-29. **Used for F2 (2026-10-29):** the locked test (2022-07-04 to 2025-06-30) is now used; the Cook County outside check found no link between forecast risk and PCI. Results and the chosen model (B1): `07-ml/model-card-forecast-chicago.md`.
**Rules:** `04-design/forecasting-f0-ground-rules.md` (approved and frozen 2026-10-28). **Plan:** `04-design/forecasting-roadmap.md`.

## In plain words

To learn where potholes are likely to appear, the forecast needs four kinds of past data for Chicago: the **roads** (cut into 100 m pieces), **where and when potholes were reported** (311 requests since 2011), the **daily weather**, and the **community areas** (to keep 10 areas aside as a test of places the model never saw). All of it is free public data. It goes into a separate database called `forecast`, never into the app database.

## 1. Sources

| Data | Source | What we keep | Licence / terms |
|------|--------|--------------|-----------------|
| Pothole reports, old 311 system (2011 to 2018-12-17) | City of Chicago Data Portal, dataset `7as2-ds3y` | request number, created date, status, request type, latitude, longitude | City of Chicago Data Portal Terms of Use: "as is"; the City may require naming the source and version |
| Pothole reports, new 311 system (from 2018-12-18) | City of Chicago Data Portal, dataset `v6vf-nfxy`, type code `PHF` | request number, type, created date, status, duplicate flag, legacy flag, latitude, longitude | Same |
| Community areas (77) | City of Chicago Data Portal, dataset `igwz-8jzy` | number, name, boundary | Same |
| Daily weather | NOAA GHCN-Daily, stations USW00094846 (O'Hare) and USW00014819 (Midway), from 2010-10-01 | max/min temperature, rain, snowfall, snow depth | CC0 public domain, attribution requested |
| Roads | OpenStreetMap via the Overpass API, one extract (date recorded) | road type, name, lanes, surface, shape | ODbL 1.0: credit; share-alike for derived databases |
| Elevation (F1b) | USGS 3DEP elevation service, sampled at start, middle and end of every section | height, slope %, low spot (vs sections within 200 m) | Public domain |
| Flood zones (F1b) | FEMA National Flood Hazard Layer, layer 28, Chicago box | 1% and 0.2% flood-zone flags | US government public data; information only |
| Soil (F1b) | USDA SSURGO via Soil Data Access, Chicago box in 0.05° squares | drainage class of the main soil, "urban land" flag; dropped if >80% of sections have no class | Public domain |
| Traffic (F1b) | IDOT Traffic Count Program (`ADT_COMP` layer) | vehicles per day, heavy vehicles per day, count years; matched within 15 m and 20° | No licence stated; research use. F2 uses the latest count as a busy-ness band (owner decision B) and is also trained without it |
| Bus routes (F1b) | City of Chicago Data Portal `6uva-a5ei` (CTA bus routes) | number of routes along each section (within 15 m, 20°) | Chicago Data Portal Terms of Use |
| Pavement condition, **checking only** (team lead's suggestion, 2026-10-29) | Cook County DOTH map service `Pavement_Condition_Index`, 2025 survey, townships Barrington, Bloom, Lake, Palos, Stickney, Thornton | street, cities, length, PCI score (0–100), shape | **No licence stated.** Internal checking only (photo AI and forecast checks); never a training label or shown in the product until CCDOTH agrees in writing (PI-23) |

**Never downloaded** (privacy, F0 section 9): street address, ward, police district, free-text fields. The download asks the portal for the kept columns only.

**Licence check:** the Chicago terms page could not be opened from Claude's workspace, so the download refuses to fetch Chicago data until the owner has read the terms and runs it with `--chicago-terms-confirmed`; the time of that confirmation is stored in `manifest.json`. Our use: research, not republished; the F2 report names each dataset and its download date (source and version).

## 2. How the files are checked

Every downloaded file is listed in `ml/forecasting/data/raw/manifest.json` with its URL, query, columns, download time, size, SHA-256 fingerprint, row count and licence. The download stops with a clear message if the portal renames a column, and the load stops if the 77 community areas are not all there or if the weather temperatures do not look like °C.

## 3. Processing rules

| Item | Rule |
|------|------|
| Road types | primary, secondary, tertiary, residential, unclassified and their `_link` roads; private roads (`access=private/no`) and areas left out |
| Intersections | A road is split where it shares a point with another included road (or with itself) |
| Sections | Pieces of 100 m. A leftover shorter than 30 m is **joined to the last section** (so sections are 30–129 m); a whole piece between intersections shorter than 30 m is **not** a section and is counted (its potholes still match the neighbouring sections within 20 m) |
| City limit | A section is kept if its middle point is inside a community area |
| Section id | `<OSM way>-<piece>-<cut>`: the same on every load of the same OpenStreetMap extract |
| Duplicates | Old system: status `Completed - Dup` or `Open - Dup`. New system: duplicate flag true. Kept in the table, marked, never counted as a new pothole |
| Old and new systems | Old dataset only before 2018-12-18, new dataset only from that day, so no request is counted twice |
| Locations | Missing coordinates are marked `missing`; points outside the Chicago box are marked `outside_chicago`. Neither is moved or guessed, and neither can match a section |
| Dates | 311 times are Chicago local time, as published |
| Weather | Values that failed a NOAA quality check are dropped and counted; missing days stay missing |
| Held-out community areas | Chosen by the fixed seed 20261028 from the 77 area numbers: **1, 5, 6, 19, 28, 34, 64, 70, 72, 75** (expected names: Rogers Park, North Center, Lake View, Belmont Cragin, Near West Side, Armour Square, Clearing, Ashburn, Beverly, Morgan Park; confirmed in the report) |
| Test period | The report does not analyse 2022-07-04 to 2025-06-30; it shows only the total number of reports |

## 4. Database tables (`forecast`)

`community_areas`, `road_sections`, `pothole_reports`, `weather_stations`, `weather_daily`, `load_log` (time, OSM extract date, all counts). A load replaces the previous one in a single transaction.

## 5. Known limits and questions

| Limit | Effect | What we do |
|-------|--------|------------|
| A 311 report is a **report**, not an inspection | Busy streets and active neighbourhoods report more | Stated in every report; F3 adds verified city data (PI-21) |
| Some reports may be entered by city crews, not residents | Could make "reports" follow crew routes | Check in F2 whether the new dataset's origin field should be used; not downloaded yet |
| 311 system change on 2018-12-18 | Counting or duplicate rules may differ | The report compares two years before and after (per week, duplicate share) |
| 2020 pandemic | Fewer trips and reports | Read the yearly table with this in mind |
| **Roads are today's OpenStreetMap, used for 2011–2025** | Roads built or removed since then are slightly wrong for early years | Accepted for the proof of concept; noted in the F2 report |
| Two airport weather stations for the whole city | Lake-side and inland weather differ a little | Nearest station per section in F2 |
| Static layers (elevation, flood zone, soil, traffic) | Not in this first F1 step | Added in F1b before F2 training, each with its licence |
| Midway is missing 95% of its snowfall values | Snow inputs from Midway would be mostly empty | **Decision:** snow (and snow depth) come from O'Hare for every section; temperature and rain from the nearest station |
| Cook County PCI: one survey (2025) | Cannot teach change over time; 2025 falls in the locked test period, so it must never be an input | **Checking only.** Its Lake Township layer lies **inside Chicago** (south-west side: 20,941 pieces named Chicago, 21,108 inside the city), so in F2 it gives an independent check of the Chicago forecast (do high-risk sections have lower PCI?); ask CCDOTH for older surveys (2022, 2019) and permission (PI-23) |

## 6. Counts (first load, 2026-10-28; OpenStreetMap extract 2026-10-28)

| Item | Count |
|------|-------|
| Road sections | **71,979** (6,316 km); length 30 / 100 / 130 m (min / median / max) |
| By road type | residential 46,759; secondary 12,947; tertiary 8,509; primary 2,276; unclassified 1,289; links 199 |
| Building steps | 35,087 OSM roads → 61,463 pieces between intersections → 73,445 sections; 10,023 pieces under 30 m (160 km, 2.5%) not sections; 1,466 sections outside the city removed |
| Tags present | lanes 20.3%, surface 34.4% (missing stays missing) |
| Held-out areas | 1 Rogers Park 717, 5 North Center 773, 6 Lake View 1,220, 19 Belmont Cragin 1,426, 28 Near West Side 2,377, 34 Armour Square 380, 64 Clearing 802, 70 Ashburn 1,736, 72 Beverly 1,100, 75 Morgan Park 1,152 sections |
| 311 old system | 560,458 downloaded = 559,071 loaded + 1,387 repeated request numbers; 164,349 duplicates; 871 no location; 6 outside Chicago; 2009-01-12 to 2018-12-17 |
| 311 new system | 429,231 downloaded = 429,231 loaded; 135,467 duplicates; 1,878 no location; 4 legacy records; 2018-12-18 to 2026-10-28 |
| Usable reports per year (not duplicate, located) | 2011 62,630 · 2012 38,627 · 2013 52,534 · 2014 69,731 (polar-vortex winter) · 2015 47,511 · 2016 37,821 · 2017 41,874 · 2018 42,831 · 2019 43,211 · 2020 32,779 · 2021 31,391 · 2022 (to July 3) 33,576 |
| Locked test period | 218,284 reports in total, **not analysed** |
| 311 system change | usable per week 822.9 before → 718.0 after (ratio 0.87; the after window includes the 2020 pandemic); duplicates 30.5% → 38.4%. Usable reports in 2018 and 2019 are nearly equal (42,831 vs 43,211), so the switch did not break the history. F2 adds an "old/new 311 system" input and reports results on both sides |
| Coverage | **90.6%** of usable reports before the test period (484,769 of 535,068) are within 20 m of a section; the rest are on excluded roads (expressways, alleys) or mislocated |
| Weather, O'Hare | 2010-10-01 onwards, 0.0% missing temperature, rain and snow; 3 values failed NOAA quality checks |
| Weather, Midway | 0.1% missing temperature, 0.2% rain, **95.2% snow** (see section 5); 7 temperature values failed quality checks |
| Freeze–thaw days per winter (Nov–Apr) | 46–82 (realistic for Chicago) |
| F1b first run (2026-10-29) | Elevation 100% (median 182 m, slope median 0.15%; extreme slopes up to 37% and dips to −13 m are likely bridges over ground, flagged in F2); bus routes 100% answered, 23.2% of sections on ≥ 1 of 127 CTA routes; traffic 34.6% (main roads), years 2017–2025, mostly 2022 and 2025; soil **dropped** (93.5% no drainage class; 97.6% "urban land"); flood zones on the second try: 3,159 FEMA zone areas; **303 sections (0.4%) touch a 1% zone, 155 (0.2%) a 0.2% zone**, all sections answered. **F1b complete** |
| Cook County PCI 2025 (checking only) | 44,090 pieces, 4,772 km, all scored; median PCI 58–62 per township, range 38–90. Barrington 1,705; Bloom 5,574; **Lake 21,263 (inside Chicago)**; Palos 3,237; Stickney 2,254; Thornton 10,057 |

## 7. F1 acceptance (from the roadmap)

- [x] All sources downloaded with manifest entries (Chicago terms confirmed by the owner, 2026-10-28)
- [x] Counts reconcile: rows downloaded = rows loaded + rows skipped (with reasons)
- [x] 311 system change checked and described (section 6)
- [x] Dataset card numbers filled in (section 6)
- [x] Nothing from the locked test period analysed (built into the report)
- [x] Cook County pavement condition downloaded and loaded (checking only), 2026-10-29: 44,090 road pieces, all with a PCI score
