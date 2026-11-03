# Forecasting F1b: Static Layers Plan

**Status:** **Approved by the owner 2026-10-29** (including CTA bus routes and the 80% soil rule). **Built, tested and run: F1b COMPLETE 2026-10-29** (`ml/forecasting/static.py`, 30 forecasting tests); waiting for the owner's run of `scripts\forecast-f1.bat`. Added during the build: IDOT's **heavy-vehicle count** (`HCV_AADT`) next to total traffic. Builds on F1 (complete for Chicago, `07-ml/dataset-card-chicago-forecast.md`). Rules: `forecasting-f0-ground-rules.md` section 4 (static layers allowed; their date is recorded; nothing from the forecast horizon).

## In plain words

F1 gave every road section its **history** (potholes) and **weather**. F1b adds facts about the **place itself** that do not change week to week: is the road on a slope or in a dip where water collects, is it in a flood zone, what is the soil under it, how much traffic does it carry, and do buses run on it. Each fact is attached to each of the 71,979 sections. Anything we cannot find stays **missing and flagged**, never guessed.

## 1. Layers

| # | Layer | Source (free) | What each section gets | Licence | Expected coverage |
|---|-------|---------------|------------------------|---------|-------------------|
| 1 | **Elevation** | USGS 3DEP elevation service (`elevation.nationalmap.gov`, `getSamples`; best available, ~1 m lidar in Chicago) | height at start, middle, end; **slope %** along the section; **low spot** = middle height minus the average of sections within 200 m (negative = water collects) | US government, public domain | ~100% |
| 2 | **Flood zone** | FEMA National Flood Hazard Layer (`hazards.fema.gov`, layer 28 "Flood Hazard Zones"), effective maps | in 1% annual-chance zone (A, AE, AH, AO) yes/no; in 0.2% zone yes/no; map effective date | US government, public; "for information", not for insurance decisions | All sections answered; few will be "yes" in Chicago |
| 3 | **Soil drainage** | USDA Soil Data Access (SSURGO), map units intersecting Chicago | drainage class of the main soil (ordered, e.g. well → poorly drained); share of "Urban land" | US government, public domain | **Unknown:** much of Chicago is mapped as "Urban land" with no drainage class. **Rule:** if more than 80% of sections get no class, the layer is dropped and the decision recorded |
| 4 | **Traffic (AADT)** | IDOT Traffic Count Program (`ADT_COMP` layer on IDOT's ArcGIS service) | vehicles per day and the count year, from a count line within 15 m running the same direction (within 20°) | State of Illinois public data; **no licence stated** → confirm on download (as with Cook County) | Main roads only; **most residential sections will be missing** (flagged, not guessed) |
| 5 | **Bus routes** (recommended extra) | City of Chicago data portal, "CTA - Bus Routes" (`6uva-a5ei`) | number of CTA bus routes on the section (heavy vehicles break roads faster) | Chicago Data Portal Terms of Use (already accepted) | All sections answered |

**No-cheating checks** (F0 section 4):
- Traffic: ~~use only counts dated 2021 or earlier~~ **changed 2026-10-29 (owner, option B):** only 1.2% of sections had such a count, so F2 uses the latest count of any year as a busy-ness band and trains with and without traffic to show it does not leak the future. The count year is stored with the value.
- Flood maps, soil and elevation describe the ground, not the horizon; their dates go in the dataset card.
- Cook County PCI is **not** an input (one year, 2025, inside the test period).

## 2. How it works (same pattern as F1)

| Step | What changes | Owner action |
|------|--------------|--------------|
| Download | 4–5 new items in `config/sources.yaml`; ArcGIS queries limited to the Chicago box; elevation sampled at about 216,000 points (3 per section) in batches of 1,000 | Double-click `scripts\forecast-f1.bat` (about 20–40 extra minutes, mostly elevation) |
| Load | New table `section_static` (one row per section: slope, low spot, flood flags, soil class, traffic + year, bus routes, and "missing" flags) | None |
| Report | New "Static layers" section: coverage % of each input, value ranges, and how many sections are flagged missing | Read it with Claude |

New Python packages: **none** (same requests / shapely / psycopg).

## 3. Tests

Unit tests with small fake answers from each service (paging, errors, renamed fields), the slope and low-spot calculations, the traffic match (distance and direction), the 80% soil rule, the "count year 2021 or earlier" rule, and the full PostGIS load test extended with the new table.

## 4. Done when

- [x] Code, tests and report section built (2026-10-29)
- [x] Every layer downloaded (flood zones on the second try, 2026-10-29, with the small-squares fix: 3,159 zone areas) with a manifest entry (URL, date, fingerprint, licence)
- [x] `section_static` has one row for each of the 71,979 sections
- [x] Coverage of every input reported; missing values flagged, none guessed
- [x] Soil kept or dropped by the 80% rule, decision recorded (**dropped**: 93.5% missing)
- [x] Traffic rule decided (option B: busy-ness bands, with/without check in F2)
- [x] Dataset card updated (sources, licences, coverage)

## 5. Decisions for the owner

1. Approve this plan.
2. Include **CTA bus routes** (recommended: buses are among the heaviest vehicles on city streets)?
3. Accept the **soil rule** (drop if more than 80% of sections have no drainage class)?

## 6. Not in F1b (later, if data can be found)

- **Road age / last resurfacing date**: probably the strongest missing input. Needs city records (PI-21 for the suburbs; to be searched for Chicago).
- Pavement type (asphalt vs concrete): OpenStreetMap `surface` is tagged on only 34% of sections.
