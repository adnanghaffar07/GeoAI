# Area check: PROJECT LINE TESTING

Result: **Level 1 only** (risk factors; no pothole history, so no tested percentage).

- Map zone for measuring meters: EPSG:26916; box: {'min_lon': -88.2596, 'min_lat': 41.7903, 'max_lon': -88.2478, 'max_lat': 41.8011}
- Roads (OpenStreetMap extract 2026-11-12T13:53:06Z): 93 sections, 8.1 km before roads outside the boundary are removed at load.

## Data available

| Layer | Available |
|---|---|
| pothole history (Level 2) | no (shown as missing) |
| weather (freeze-thaw, rain, snow) | yes |
| elevation (USGS, national) | yes |
| flood zones (FEMA, national) | yes |
| soil (USDA, national) | yes |
| traffic counts | yes |
| bus routes | no (shown as missing) |

## Weather stations

- USC00110338 Aurora Water
- USW00094892 Chicago W Chicago Dupage Ap
- USC00115097 Lisle - Morton Arboretum
- Snow from: USC00115097

Rule D3: within 30 km of the area's box, at least 90% of days with temperature and with rain, 2016-01-01 to 2025-12-31. 6 candidates found; the nearest 6 were measured:

| Station | Name | Distance (km) | Temperature days | Rain days | Snow days | Chosen |
|---|---|---|---|---|---|---|
| USC00110338 | Aurora Water | 4.3 | 100% | 100% | 89% | yes |
| USW00094892 | Chicago W Chicago Dupage Ap | 10.6 | 100% | 100% | 6% | yes |
| USC00115097 | Lisle - Morton Arboretum | 14.6 | 97% | 98% | 99% | yes |
| USW00004808 | Chicago Aurora Muni Ap | 18.5 | 100% | 99% | 6% |  |
| USC00117457 | Romeoville Wfo | 24.7 | 100% | 100% | 100% |  |
| USC00112736 | Elgin Water | 29.2 | 98% | 100% | 98% |  |
