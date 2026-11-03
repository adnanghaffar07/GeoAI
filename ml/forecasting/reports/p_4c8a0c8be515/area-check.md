# Area check: New Project

Result: **Level 1 only** (risk factors; no pothole history, so no tested percentage).

- Map zone for measuring meters: EPSG:26916; box: {'min_lon': -88.2524, 'min_lat': 41.7208, 'max_lon': -88.1625, 'max_lat': 41.7961}; area inside the boundary: 20.9 km²
- Roads (OpenStreetMap extract 2026-11-02T18:34:05Z): 6,189 sections, 520.5 km before roads outside the boundary are removed at load.

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
- USC00115097 Lisle - Morton Arboretum
- USW00094892 Chicago W Chicago Dupage Ap
- Snow from: USC00115097

Rule D3: within 30 km of the area's box, at least 90% of days with temperature and with rain, 2016-01-01 to 2025-12-31. 9 candidates found; the nearest 8 were measured:

| Station | Name | Distance (km) | Temperature days | Rain days | Snow days | Chosen |
|---|---|---|---|---|---|---|
| USC00110338 | Aurora Water | 4.7 | 100% | 100% | 89% | yes |
| USC00115097 | Lisle - Morton Arboretum | 7.7 | 97% | 98% | 99% | yes |
| USW00094892 | Chicago W Chicago Dupage Ap | 11.2 | 100% | 100% | 6% | yes |
| USC00117457 | Romeoville Wfo | 14.5 | 100% | 100% | 100% |  |
| USW00004808 | Chicago Aurora Muni Ap | 19.0 | 100% | 99% | 6% |  |
| USW00014834 | Joliet | 20.1 | 10% | 6% | 0% |  |
| USC00114530 | Joliet Brandon Road Lock/Dam | 24.7 | 96% | 98% | 98% |  |
| USW00094846 | Chicago Ohare Intl Ap | 26.4 | 100% | 100% | 100% |  |
