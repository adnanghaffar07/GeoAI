# F5: forecast without a road's own report history (Chicago validation year)

Exploratory check on the validation year only. The locked test period was not read. Not a pass/fail test and not a reason to show tested levels anywhere.

Inputs used by the no-history model (25): freeze_thaw_7d, freeze_thaw_14d, freeze_thaw_30d, below_freezing_days_30d, rain_mm_7d, rain_mm_30d, heavy_rain_days_30d, snow_mm_7d, snow_mm_30d, hot_days_30d, days_since_freeze, highway_code, length_m, lanes, surface_code, slope_pct, low_spot_m, flood_1pct, flood_02pct, probably_bridge, traffic_band, heavy_vehicle_band, bus_routes, week_of_year, month.

| Model | Top-1% precision | PR-AUC | Winter top-1% | Held-out areas top-1% |
|---|---|---|---|---|
| B0 simple rule (needs history) | 0.2762 (0.2279-0.3224) | 0.1462 (0.1167-0.1725) | 0.3402 (0.2704-0.4168) | 0.2748 (0.2281-0.3218) |
| B1 full (needs history) | 0.3571 (0.3020-0.4111) | 0.2416 (0.2026-0.2699) | 0.4304 (0.3463-0.5185) | 0.3616 (0.3038-0.4188) |
| B1 no history (works anywhere) | 0.1478 (0.1209-0.1740) | 0.1276 (0.1049-0.1423) | 0.1827 (0.1404-0.2263) | 0.1040 (0.0817-0.1259) |

Read the first row as the bar to beat: it is the simple rule from the original F2. If the no-history model is clearly above chance but well below the full model, areas without reports can get a weaker, clearly labelled forecast. If it is close to chance, they should stay at Level 1.

Raw summaries: f5-no-history-report.json.
