# Area check: City of Philadelphia

Result: **Level 1 only** (risk factors; no pothole history, so no tested percentage).

- Map zone for measuring meters: EPSG:26918; box: {'min_lon': -75.2853, 'min_lat': 39.862, 'max_lon': -74.9508, 'max_lat': 40.143}; area inside the boundary: 368.9 km²
- Roads (OpenStreetMap extract 2026-11-09T20:54:48Z): 54,183 sections, 4,136.0 km before roads outside the boundary are removed at load.

## Data available

| Layer | Available |
|---|---|
| pothole history (Level 2) | yes |
| weather (freeze-thaw, rain, snow) | yes |
| elevation (USGS, national) | yes |
| flood zones (FEMA, national) | yes |
| soil (USDA, national) | yes |
| traffic counts | no (shown as missing) |
| bus routes | no (shown as missing) |

## Weather stations

- USC00286864 Pennsauken 1N
- USW00013739 Phila Intl Ap
- USW00094732 Ne Phila Ap
- Snow from: USW00013739

Rule D3: within 30 km of the area's box, at least 90% of days with temperature and with rain, 2016-01-01 to 2025-12-31. 17 candidates found; the nearest 8 were measured:

| Station | Name | Distance (km) | Temperature days | Rain days | Snow days | Chosen |
|---|---|---|---|---|---|---|
| USC00286864 | Pennsauken 1N | 0.0 | 99% | 99% | 96% | yes |
| USC00366886 | Phila Franklin Inst | 0.0 | 94% | 70% | 82% |  |
| USW00013739 | Phila Intl Ap | 0.0 | 100% | 100% | 100% | yes |
| USW00094732 | Ne Phila Ap | 0.0 | 98% | 94% | 0% | yes |
| USC00366194 | Neshaminy Falls | 0.6 | 99% | 100% | 99% |  |
| USC00366370 | Norristown | 4.4 | 96% | 97% | 96% |  |
| USC00285728 | Moorestown 4 E | 7.3 | 36% | 42% | 42% |  |
| USW00093780 | S Jersey Rgnl Ap | 9.4 | 96% | 95% | 0% |  |
