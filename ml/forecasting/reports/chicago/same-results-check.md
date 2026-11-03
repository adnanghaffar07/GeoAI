# Chicago same-results check (any-area code)

Checked 2026-10-30. Result: **PASSED: Chicago gives exactly the same results**.

## 1. Database tables (reloaded from the same raw files)

| Table | Rows | Only in old | Only in new | Result |
|---|---|---|---|---|
| community_areas | 77 | 0 | 0 | same |
| road_sections | 71979 | 0 | 0 | same |
| pothole_reports | 988302 | 0 | 0 | same |
| weather_stations | 2 | 0 | 0 | same |
| weather_daily | 11734 | 0 | 0 | same |
| pavement_condition_cook | 44090 | 0 | 0 | same |
| section_static | 71979 | 0 | 0 | same |
| flood_zones | 3159 | 0 | 0 | same |
| soil_units | 7370 | 0 | 0 | same |
| traffic_counts | 4705 | 0 | 0 | same |
| bus_routes | 950 | 0 | 0 | same |

## 2. Learning table (rebuilt)

79 of 79 items identical.


## 3. Validation scores of the existing models

| Model | Precision at top 1% before | Now | Result (all measures) |
|---|---|---|---|
| B0_rule | 0.2762 | 0.2762 | same |
| B1_logistic | 0.3571 | 0.3571 | same |
| M_lightgbm | 0.3641 | 0.3641 | same |
| M_lightgbm_without_traffic | 0.3652 | 0.3652 | same |

The locked test was not run again (it is used up). Nothing in schema `chicago` or in data/chicago was changed.
