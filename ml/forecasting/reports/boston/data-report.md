# Boston data report (US plan step C)

**Status:** loaded 2026-11-09 into schema `boston` of the forecast database; shown as Level 1 (risk factors) until the shared US model passes its test here (step E). TRIAL.

## Sources

| Data | Source | Rows / size | Licence |
|---|---|---|---|
| Pothole requests | Analyze Boston, 311 Service Requests (old system 2012 to mid-2026, new "BCS-" system from mid-2026) | 147,458 | Analyze Boston 311 Service Requests, Open Data Commons PDDL (public domain) |
| Road condition and traffic | FHWA HPMS, Massachusetts 2025 | 29,857 pieces | FHWA Highway Performance Monitoring System (US DOT), US government work, public domain |
| Roads, weather, elevation, flood zones, soil | OpenStreetMap, NOAA (Boston Logan, Hingham, Jamaica Plain), USGS, FEMA, USDA | 19,713 sections | as for Chicago |
| **Total raw files** | | **103 MB** | |

## Pothole requests per year

| Year | Requests | Marked duplicate |
|---|---|---|
| 2012 | 5,046 | 143 |
| 2013 | 5,943 | 190 |
| 2014 | **no data** (the portal's 2014 file is empty) | — |
| 2015 | 8,433 | 306 |
| 2016 | 6,444 | 197 |
| 2017 | 11,929 | 324 |
| 2018 | 16,967 | 515 |
| 2019 | 16,005 | 370 |
| 2020 | 9,429 | 257 |
| 2021 | 9,838 | 212 |
| 2022 | 12,996 | 238 |
| 2023 | 11,828 | 156 |
| 2024 | 10,620 | 134 |
| 2025 | 11,064 | 91 |
| 2026 | 10,916 | 384 |

## Rules used

- **Residents' requests only:** old system type "Request for Pothole Repair"; new system service "Pothole". City crews' internal repair records ("Pothole Repair (Internal)", about 6,500 a year) are left out, as in Chicago.
- **No report counted twice:** old-system requests from the new system's first day on are left out (20 on 2026-11-09).
- **Only these columns are fetched:** request number, date, status, closure reason (for duplicates), latitude, longitude. No addresses, names or free text.
- **Locations:** 158 without a location and 0 at City Hall (the old system's "no location" point) count as missing, never guessed.
- **Duplicates:** Boston seldom marks them (closure reason "duplicate" or "multiple cases"), so the rate is low (about 2%) compared with Chicago (about 30%). Step E will use one rule for every city (reports at the same spot within a few days count once).
- **2014:** marked as missing in `config/areas/boston.yaml` so a model never reads it as "no potholes".

## Road condition (HPMS)

Roughness is in inches per mile (checked: median 198 in Boston, 181 in Chicago, 127 in Naperville). FHWA's limits (poor above 170) were set for highways; slow city streets naturally measure rougher, so "high" on a city street means rough, not necessarily unsafe.

Risk factors: `reports/boston/level1-risk-factors.md`. Area check: `reports/boston/area-check.md`.
