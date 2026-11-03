# Area check: City of Naperville

Result: **Level 1 only** (risk factors; no pothole history, so no tested percentage).

- Map zone for measuring meters: EPSG:26916; box: {'min_lon': -88.2403, 'min_lat': 41.6613, 'max_lon': -88.0835, 'max_lat': 41.827}; area inside the boundary: 110.3 km²
- Roads (OpenStreetMap extract 2026-10-30T15:50:28Z): 12,036 sections, 1,018.2 km before roads outside the boundary are removed at load.

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
- USC00117457 Romeoville Wfo
- Snow from: USC00117457

Rule D3: within 30 km of the area's box, at least 90% of days with temperature and with rain, 2016-01-01 to 2025-12-31. 11 candidates found; the nearest 8 were measured:

| Station | Name | Distance (km) | Temperature days | Rain days | Snow days | Chosen |
|---|---|---|---|---|---|---|
| USC00115097 | Lisle - Morton Arboretum | 0.9 | 97% | 98% | 99% | yes |
| USC00110338 | Aurora Water | 5.7 | 100% | 100% | 89% | yes |
| USC00117457 | Romeoville Wfo | 6.3 | 100% | 100% | 100% | yes |
| USW00094892 | Chicago W Chicago Dupage Ap | 7.8 | 100% | 100% | 6% |  |
| USW00014834 | Joliet | 12.4 | 10% | 6% | 0% |  |
| USC00114530 | Joliet Brandon Road Lock/Dam | 17.6 | 96% | 98% | 98% |  |
| USW00094846 | Chicago Ohare Intl Ap | 19.4 | 100% | 100% | 100% |  |
| USW00004808 | Chicago Aurora Muni Ap | 20.0 | 100% | 99% | 6% |  |
