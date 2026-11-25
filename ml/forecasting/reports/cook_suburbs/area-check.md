# Area check: Cook suburbs (La Grange Park, Elk Grove Village, Schaumburg)

Result: **Level 1 only** (risk factors; no pothole history, so no tested percentage).

- Map zone for measuring meters: EPSG:26916; box: {'min_lon': -88.1594, 'min_lat': 41.8142, 'max_lon': -87.8468, 'max_lat': 42.0831}; area inside the boundary: 87.9 km²
- Roads (OpenStreetMap extract 2026-11-24T21:41:29Z): 10,347 sections, 876.6 km before roads outside the boundary are removed at load.

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

- USW00094846 Chicago Ohare Intl Ap
- USC00115097 Lisle - Morton Arboretum
- USC00110442 Barrington 3Sw
- Snow from: USW00094846

Rule D3: within 30 km of the area's box, at least 90% of days with temperature and with rain, 2016-01-01 to 2025-12-31. 14 candidates found; the nearest 8 were measured:

| Station | Name | Distance (km) | Temperature days | Rain days | Snow days | Chosen |
|---|---|---|---|---|---|---|
| USW00094846 | Chicago Ohare Intl Ap | 0.0 | 100% | 100% | 100% | yes |
| USC00115097 | Lisle - Morton Arboretum | 0.2 | 97% | 98% | 99% | yes |
| USC00110442 | Barrington 3Sw | 3.6 | 98% | 99% | 81% | yes |
| USW00004838 | Chicago Palwaukee Ap | 4.2 | 100% | 100% | 6% |  |
| USW00094892 | Chicago W Chicago Dupage Ap | 7.6 | 100% | 100% | 6% |  |
| USW00014819 | Chicago Midway Ap | 8.3 | 100% | 100% | 6% |  |
| USC00111577 | Chicago Midway Ap 3Sw | 10.3 | 100% | 100% | 100% |  |
| USC00112736 | Elgin Water | 10.5 | 98% | 100% | 98% |  |
