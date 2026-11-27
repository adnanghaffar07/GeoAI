# Area check: Cook northwest (Mount Prospect, Des Plaines, Arlington Heights)

Result: **Level 1 only** (risk factors; no tested forecast yet: pothole history missing or too short, so no tested percentage).

- Map zone for measuring meters: EPSG:26916; box: {'min_lon': -88.0315, 'min_lat': 41.9903, 'max_lon': -87.855, 'max_lat': 42.1589}; area inside the boundary: 108.0 km²
- Roads (OpenStreetMap extract 2026-11-25T22:23:33Z): 12,994 sections, 1,115.3 km before roads outside the boundary are removed at load.

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

- USW00004838 Chicago Palwaukee Ap
- USW00094846 Chicago Ohare Intl Ap
- USC00110442 Barrington 3Sw
- Snow from: USW00094846

Rule D3: within 30 km of the area's box, at least 90% of days with temperature and with rain, 2016-01-01 to 2025-12-31. 10 candidates found; the nearest 8 were measured:

| Station | Name | Distance (km) | Temperature days | Rain days | Snow days | Chosen |
|---|---|---|---|---|---|---|
| USW00004838 | Chicago Palwaukee Ap | 0.0 | 100% | 100% | 6% | yes |
| USW00094846 | Chicago Ohare Intl Ap | 3.3 | 100% | 100% | 100% | yes |
| USC00110442 | Barrington 3Sw | 10.9 | 98% | 99% | 81% | yes |
| USC00115097 | Lisle - Morton Arboretum | 20.0 | 97% | 98% | 99% |  |
| USW00094892 | Chicago W Chicago Dupage Ap | 20.9 | 100% | 100% | 6% |  |
| USC00112736 | Elgin Water | 21.0 | 98% | 100% | 98% |  |
| USW00014819 | Chicago Midway Ap | 24.4 | 100% | 100% | 6% |  |
| USC00115493 | Mchenry Stratton Lock/Dam | 24.8 | 99% | 96% | 98% |  |
