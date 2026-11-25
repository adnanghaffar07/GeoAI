# Area check: Central DuPage (Lombard, Glen Ellyn, Oak Brook, Wheaton)

Result: **Level 1 only** (risk factors; no pothole history, so no tested percentage).

- Map zone for measuring meters: EPSG:26916; box: {'min_lon': -88.1567, 'min_lat': 41.8077, 'max_lon': -87.9132, 'max_lat': 41.92}; area inside the boundary: 103.1 km²
- Roads (OpenStreetMap extract 2026-11-24T17:00:02Z): 10,735 sections, 931.0 km before roads outside the boundary are removed at load.

## Data available

| Layer | Available |
|---|---|
| pothole history (Level 2) | yes |
| weather (freeze-thaw, rain, snow) | yes |
| elevation (USGS, national) | yes |
| flood zones (FEMA, national) | yes |
| soil (USDA, national) | yes |
| traffic counts | yes |
| bus routes | no (shown as missing) |

## Weather stations

- USC00115097 Lisle - Morton Arboretum
- USW00094846 Chicago Ohare Intl Ap
- USW00094892 Chicago W Chicago Dupage Ap
- Snow from: USW00094846

Rule D3: within 30 km of the area's box, at least 90% of days with temperature and with rain, 2016-01-01 to 2025-12-31. 12 candidates found; the nearest 8 were measured:

| Station | Name | Distance (km) | Temperature days | Rain days | Snow days | Chosen |
|---|---|---|---|---|---|---|
| USC00115097 | Lisle - Morton Arboretum | 0.0 | 97% | 98% | 99% | yes |
| USW00094846 | Chicago Ohare Intl Ap | 4.5 | 100% | 100% | 100% | yes |
| USW00094892 | Chicago W Chicago Dupage Ap | 7.8 | 100% | 100% | 6% | yes |
| USC00110338 | Aurora Water | 13.0 | 100% | 100% | 89% |  |
| USW00014819 | Chicago Midway Ap | 13.3 | 100% | 100% | 6% |  |
| USC00111577 | Chicago Midway Ap 3Sw | 13.7 | 100% | 100% | 100% |  |
| USC00112736 | Elgin Water | 19.1 | 98% | 100% | 98% |  |
| USC00110442 | Barrington 3Sw | 21.7 | 98% | 99% | 81% |  |
