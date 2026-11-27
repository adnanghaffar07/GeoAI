# Area check: City of Aurora

Result: **Level 1 only** (risk factors; no tested forecast yet: pothole history missing or too short, so no tested percentage).

- Map zone for measuring meters: EPSG:26916; box: {'min_lon': -88.4134, 'min_lat': 41.6749, 'max_lon': -88.2, 'max_lat': 41.8272}; area inside the boundary: 125.3 km²
- Roads (OpenStreetMap extract 2026-11-25T15:28:07Z): 12,788 sections, 1,104.8 km before roads outside the boundary are removed at load.

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

- USC00110338 Aurora Water
- USW00004808 Chicago Aurora Muni Ap
- USW00094892 Chicago W Chicago Dupage Ap
- Snow from: USC00110338

Rule D3: within 30 km of the area's box, at least 90% of days with temperature and with rain, 2016-01-01 to 2025-12-31. 9 candidates found; the nearest 8 were measured:

| Station | Name | Distance (km) | Temperature days | Rain days | Snow days | Chosen |
|---|---|---|---|---|---|---|
| USC00110338 | Aurora Water | 0.0 | 100% | 100% | 89% | yes |
| USW00004808 | Chicago Aurora Muni Ap | 5.6 | 100% | 99% | 6% | yes |
| USW00094892 | Chicago W Chicago Dupage Ap | 7.7 | 100% | 100% | 6% | yes |
| USC00115097 | Lisle - Morton Arboretum | 10.5 | 97% | 98% | 99% |  |
| USC00117457 | Romeoville Wfo | 12.4 | 100% | 100% | 100% |  |
| USW00014834 | Joliet | 16.9 | 10% | 6% | 0% |  |
| USC00114530 | Joliet Brandon Road Lock/Dam | 20.7 | 96% | 98% | 98% |  |
| USC00112736 | Elgin Water | 26.2 | 98% | 100% | 98% |  |
