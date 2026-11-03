# F1 data report (Chicago)

Generated from the `forecast` database loaded at 2026-10-29 15:07:39.593204+00. OpenStreetMap extract: 2026-10-28T21:47:28Z.
Machine-readable copy: `f1-data-report.json`. The locked test period is not analysed (only its total is shown).

## Sources
| Name | Downloaded (UTC) | Rows | MB | SHA-256 (first 12) | Licence |
|---|---|---|---|---|---|
| bus_routes | 2026-10-29T14:30:27+00:00 |  | 1.9 | cb9c74d8a382 | City of Chicago Data Portal Terms of Use: public data provided "as is"; the City may require users to name the source and version of a dataset. Not republished by GeoInfraLens; used for research only. |
| community_areas | 2026-10-28T21:47:41+00:00 |  | 2.1 | 3468ac30bd81 | City of Chicago Data Portal Terms of Use: public data provided "as is"; the City may require users to name the source and version of a dataset. Not republished by GeoInfraLens; used for research only. |
| cook_county_pci | 2026-10-29T13:38:57+00:00 | 44,090 | 28.8 | a4fc51a2e4e1 | Cook County DOTH map service; no licence or terms stated on the service (checked 2026-10-29). Internal checking only until CCDOTH gives written permission. |
| elevation | 2026-10-29T14:28:51+00:00 | 135,810 | 4.2 | 591c71fd6664 | USGS 3D Elevation Program (3DEP), US government public domain |
| flood_zones | 2026-10-29T15:03:18+00:00 | 3,159 | 2.6 | 497c7ca9ef4d | FEMA National Flood Hazard Layer (effective maps), US government public data; for information, not insurance decisions |
| osm_roads | 2026-10-28T21:48:51+00:00 |  | 33.9 | 3f131d596225 | OpenStreetMap contributors, ODbL 1.0 (credit; share-alike for derived databases) |
| potholes_current | 2026-10-28T21:47:40+00:00 | 429,231 | 55.2 | eebc4bf60454 | City of Chicago Data Portal Terms of Use: public data provided "as is"; the City may require users to name the source and version of a dataset. Not republished by GeoInfraLens; used for research only. |
| potholes_historical | 2026-10-28T21:41:22+00:00 | 560,458 | 58.4 | 4e4626e7c081 | City of Chicago Data Portal Terms of Use: public data provided "as is"; the City may require users to name the source and version of a dataset. Not republished by GeoInfraLens; used for research only. |
| soils | 2026-10-29T14:30:22+00:00 | 7,370 | 17.1 | 7fdd22308ece | USDA NRCS SSURGO via Soil Data Access, US government public domain |
| traffic_counts | 2026-10-29T14:29:56+00:00 | 4,655 | 4.8 | d2bac5fef81b | IDOT Traffic Count Program (State of Illinois); no licence stated on the service (checked 2026-10-29), research use |
| weather_USW00014819 | 2026-10-28T21:47:43+00:00 | 10,763 | 2.8 | 54dc454b808f | NOAA GHCN-Daily, CC0 public domain (attribution requested) |
| weather_USW00094846 | 2026-10-28T21:47:43+00:00 | 29,232 | 11.0 | 004884c89964 | NOAA GHCN-Daily, CC0 public domain (attribution requested) |

## Road sections
71,979 sections, 6,316.2 km. Length min / median / max: 30.0 / 100.0 / 130.0 m. Lanes tagged: 20.3%, surface tagged: 34.4%.

| Road type | Sections | km |
|---|---|---|
| residential | 46,759 | 4354.8 |
| secondary | 12,947 | 946.0 |
| tertiary | 8,509 | 724.0 |
| primary | 2,276 | 167.0 |
| unclassified | 1,289 | 111.6 |
| secondary_link | 116 | 7.1 |
| primary_link | 56 | 4.2 |
| tertiary_link | 27 | 1.5 |

Building steps: osm ways: 35,087, sections built: 73,445, ways missing nodes: 0, pieces shorter than min: 10,023, pieces shorter than min km: 160.4, pieces between intersections: 61,463, sections outside city removed: 1,466

Held-out community areas (place check, never used in training):

| Area | Name | Sections |
|---|---|---|
| 1 | Rogers Park | 717 |
| 5 | North Center | 773 |
| 6 | Lake View | 1,220 |
| 19 | Belmont Cragin | 1,426 |
| 28 | Near West Side | 2,377 |
| 34 | Armour Square | 380 |
| 64 | Clearing | 802 |
| 70 | Ashburn | 1,736 |
| 72 | Beverly | 1,100 |
| 75 | Morgan Park | 1,152 |

## 311 pothole reports
| Source | Rows | Duplicates | No location | Outside Chicago | First | Last |
|---|---|---|---|---|---|---|
| potholes_current | 429,231 | 135,467 | 1,878 | 0 | 2018-12-18 | 2026-10-28 |
| potholes_historical | 559,071 | 164,349 | 871 | 6 | 2009-01-12 | 2018-12-17 |

| Year (before test period) | Reports | Duplicates | Usable (not duplicate, located) |
|---|---|---|---|
| 2009 | 3 | 0 | 3 |
| 2010 | 608 | 57 | 549 |
| 2011 | 80,158 | 17,418 | 62,630 |
| 2012 | 43,237 | 4,552 | 38,627 |
| 2013 | 69,568 | 16,967 | 52,534 |
| 2014 | 132,145 | 62,268 | 69,731 |
| 2015 | 59,676 | 12,055 | 47,511 |
| 2016 | 51,423 | 13,494 | 37,821 |
| 2017 | 61,765 | 19,807 | 41,874 |
| 2018 | 60,773 | 17,833 | 42,831 |
| 2019 | 84,097 | 40,199 | 43,211 |
| 2020 | 39,967 | 7,044 | 32,779 |
| 2021 | 38,557 | 6,980 | 31,391 |
| 2022 | 48,041 | 14,307 | 33,576 |

Locked test period: 218,284 reports in total (not analysed).

### 311 system change (2018-12-18)
| Window | From | To | Usable reports per week | Duplicates % |
|---|---|---|---|---|
| before | 2016-12-18 | 2018-12-18 | 822.9 | 30.5 |
| after | 2018-12-18 | 2020-12-18 | 718.0 | 38.4 |

After / before ratio: 0.87. Weather and the 2020 pandemic also change counts, so this is a warning sign to read, not a pass/fail test.

### Coverage
484,769 of 535,068 usable reports before the test period (90.6%) lie within the label distance of a section. Reports farther away are on excluded roads (expressways, alleys) or mislocated.

## Weather (before the test period)
| Station | First | Last | Days | TMAX missing % | TMIN missing % | PRCP missing % | SNOW missing % |
|---|---|---|---|---|---|---|---|
| USW00014819 | 2010-10-01 | 2022-07-03 | 4,292 | 0.1 | 0.1 | 0.2 | 95.2 |
| USW00094846 | 2010-10-01 | 2022-07-03 | 4,294 | 0.0 | 0.0 | 0.0 | 0.0 |

| Station | Winter starting | Freeze-thaw days (Nov-Apr) |
|---|---|---|
| USW00014819 | 2010 | 54 |
| USW00014819 | 2011 | 59 |
| USW00014819 | 2012 | 75 |
| USW00014819 | 2013 | 54 |
| USW00014819 | 2014 | 58 |
| USW00014819 | 2015 | 49 |
| USW00014819 | 2016 | 46 |
| USW00014819 | 2017 | 70 |
| USW00014819 | 2018 | 77 |
| USW00014819 | 2019 | 72 |
| USW00014819 | 2020 | 64 |
| USW00014819 | 2021 | 60 |
| USW00094846 | 2010 | 54 |
| USW00094846 | 2011 | 67 |
| USW00094846 | 2012 | 82 |
| USW00094846 | 2013 | 58 |
| USW00094846 | 2014 | 60 |
| USW00094846 | 2015 | 61 |
| USW00094846 | 2016 | 57 |
| USW00094846 | 2017 | 81 |
| USW00094846 | 2018 | 78 |
| USW00094846 | 2019 | 74 |
| USW00094846 | 2020 | 61 |
| USW00094846 | 2021 | 63 |

## Cook County pavement condition, 2025 (checking only)
Team lead's suggestion. One survey year, six suburban townships, no licence stated: used only to check the photo AI and the forecast (F3), never as a training label or in the product until CCDOTH agrees in writing.

| Township | Road pieces | km | With PCI | PCI min | PCI median | PCI max |
|---|---|---|---|---|---|---|
| Barrington | 1,705 | 312.9 | 1,705 | 43.1 | 61.5 | 77.5 |
| Bloom | 5,574 | 696.9 | 5,574 | 38.2 | 60.3 | 90.2 |
| Lake | 21,263 | 1957.6 | 21,263 | 40.2 | 58.3 | 81.4 |
| Palos | 3,237 | 462.3 | 3,237 | 43.3 | 60.6 | 79.8 |
| Stickney | 2,254 | 255.9 | 2,254 | 44.0 | 60.1 | 79.1 |
| Thornton | 10,057 | 1086.3 | 10,057 | 42.8 | 60.5 | 90.2 |

Road pieces inside the City of Chicago: 21,108 (Lake Township covers much of Chicago's south-west side, so these can check the Chicago forecast).

## Static layers (F1b)
71,979 sections. Missing values stay missing (flagged), never guessed.

| Input | Sections with a value | % |
|---|---|---|
| Elevation (middle) | 71,979 | 100.0 |
| Slope | 71,979 | 100.0 |
| Low spot | 71,976 | 100.0 |
| Flood zone answered | 71,979 | 100.0 |
| In 1% flood zone | 303 | 0.4 |
| In 0.2% flood zone | 155 | 0.2 |
| Soil drainage class | 0 | 0.0 |
| Soil mapped as urban land | 70,240 | 97.6 |
| Traffic count (any year) | 24,899 | 34.6 |
| Traffic count used in F2 (any year, as a busy-ness level) | 24,899 | 34.6 |
| Heavy-vehicle count | 24,899 | 34.6 |
| Bus routes answered | 71,979 | 100.0 |
| On at least one bus route | 16,710 | 23.2 |

| Value | Min | Median | 95th percentile | Max |
|---|---|---|---|---|
| slope % | 0.00 | 0.15 | 1.15 | 37.08 |
| vehicles per day | 20 | 11700 | 27200 | 178300 |
| elevation m | 170.6 | 182.1 | 195.6 | 207.9 |
| low spot m | -13.26 | 0.00 | 0.54 | 9.48 |

Traffic count years (F2 uses the latest count of any year as a busy-ness level, owner decision B, and is also trained without it):

| Count year | Sections |
|---|---|
| 2017 | 5 |
| 2018 | 825 |
| 2022 | 16,803 |
| 2023 | 500 |
| 2024 | 2 |
| 2025 | 6,764 |

| Soil drainage class | Sections |
|---|---|
| (none) | 71,979 |

Layers loaded and soil rule: `{"soil": {"kept": false, "rule": "drop if > 0.8", "missing_share": 0.935}, "flood": true, "traffic": {"busy_bands": [5000, 15000, 30000], "max_count_year_for_training": null}, "elevation": true, "bus_routes": true}`

## Counts while loading
| Item | Count |
|---|---|
| USW00014819.PRCP.missing | 9 |
| USW00014819.SNOW.missing | 5,658 |
| USW00014819.SNWD.missing | 5,011 |
| USW00014819.TMAX.rejected_quality_flag | 4 |
| USW00014819.TMIN.rejected_quality_flag | 3 |
| USW00014819.days | 5,866 |
| USW00094846.SNOW.rejected_quality_flag | 1 |
| USW00094846.SNWD.rejected_quality_flag | 2 |
| USW00094846.days | 5,868 |
| bus_routes.routes | 127 |
| cook_pci.loaded | 44,090 |
| cook_pci.rows | 44,090 |
| flood_zones.polygons | 3,159 |
| potholes_current.duplicates | 135,467 |
| potholes_current.legacy_records | 4 |
| potholes_current.loaded | 429,231 |
| potholes_current.location_missing | 1,878 |
| potholes_current.rows | 429,231 |
| potholes_historical.duplicates | 164,349 |
| potholes_historical.loaded | 559,071 |
| potholes_historical.location_missing | 871 |
| potholes_historical.location_outside_chicago | 6 |
| potholes_historical.rows | 560,458 |
| potholes_historical.skipped_repeated_id | 1,387 |
| traffic_counts.lines | 4,655 |
