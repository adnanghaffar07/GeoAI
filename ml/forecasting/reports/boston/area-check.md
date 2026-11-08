# Area check: City of Boston

Result: **Level 1 only** (risk factors; no pothole history, so no tested percentage).

- Map zone for measuring meters: EPSG:26919; box: {'min_lon': -71.1962, 'min_lat': 42.2229, 'max_lon': -70.7995, 'max_lat': 42.402}; area inside the boundary: 246.4 km²
- Roads (OpenStreetMap extract 2026-11-06T21:38:33Z): 19,713 sections, 1,518.3 km before roads outside the boundary are removed at load.

## Data available

| Layer | Available |
|---|---|
| pothole history (Level 2) | no (shown as missing) |
| weather (freeze-thaw, rain, snow) | yes |
| elevation (USGS, national) | yes |
| flood zones (FEMA, national) | yes |
| soil (USDA, national) | yes |
| traffic counts | no (shown as missing) |
| bus routes | no (shown as missing) |

## Weather stations

- USC00193624 Hingham
- USC00193890 Jamaica Plain
- USW00014739 Boston
- Snow from: USW00014739

Rule D3: within 30 km of the area's box, at least 90% of days with temperature and with rain, 2016-01-01 to 2025-12-31. 17 candidates found; the nearest 8 were measured:

| Station | Name | Distance (km) | Temperature days | Rain days | Snow days | Chosen |
|---|---|---|---|---|---|---|
| USC00193624 | Hingham | 0.0 | 98% | 98% | 98% | yes |
| USC00193890 | Jamaica Plain | 0.0 | 100% | 99% | 100% | yes |
| USW00014739 | Boston | 0.0 | 100% | 100% | 100% | yes |
| USC00190736 | Blue Hill Coop | 1.2 | 100% | 100% | 100% |  |
| USW00014753 | Blue Hill Lcd | 1.2 | 100% | 100% | 100% |  |
| USW00054704 | Norwood Mem Ap | 3.5 | 99% | 99% | 0% |  |
| USC00198757 | Walpole 2 | 8.0 | 100% | 100% | 100% |  |
| USW00014702 | Bedford Hanscom Fld | 10.9 | 98% | 96% | 0% |  |
