# Area check: Other City Reports

Result: **Level 1 only** (risk factors; no pothole history, so no tested percentage).

- Map zone for measuring meters: EPSG:26916; box: {'min_lon': -88.1563, 'min_lat': 41.7657, 'max_lon': -88.1409, 'max_lat': 41.7802}; area inside the boundary: 0.1 km²
- Roads (OpenStreetMap extract 2026-11-04T17:42:14Z): 352 sections, 29.7 km before roads outside the boundary are removed at load.

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

- USC00115097 Lisle - Morton Arboretum
- USC00110338 Aurora Water
- USW00094892 Chicago W Chicago Dupage Ap
- Snow from: USC00115097

Rule D3: within 30 km of the area's box, at least 90% of days with temperature and with rain, 2016-01-01 to 2025-12-31. 8 candidates found; the nearest 8 were measured:

| Station | Name | Distance (km) | Temperature days | Rain days | Snow days | Chosen |
|---|---|---|---|---|---|---|
| USC00115097 | Lisle - Morton Arboretum | 6.7 | 97% | 98% | 99% | yes |
| USC00110338 | Aurora Water | 12.7 | 100% | 100% | 89% | yes |
| USW00094892 | Chicago W Chicago Dupage Ap | 15.1 | 100% | 100% | 6% | yes |
| USC00117457 | Romeoville Wfo | 18.5 | 100% | 100% | 100% |  |
| USW00014834 | Joliet | 24.5 | 10% | 6% | 0% |  |
| USW00094846 | Chicago Ohare Intl Ap | 26.5 | 100% | 100% | 100% |  |
| USW00004808 | Chicago Aurora Muni Ap | 27.0 | 100% | 99% | 6% |  |
| USC00114530 | Joliet Brandon Road Lock/Dam | 29.3 | 96% | 98% | 98% |  |
