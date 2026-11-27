# Transfer test: the Chicago model on City of Aurora

**Outcome: PASS** (PLACEHOLDER pass marks until PI-20 (same as Chicago's).)

Model `forecast-chicago-0.2`, used unchanged. Test Mondays 2025-05-05 to 2026-05-25 (56). Reports 2025-01-31 to 2026-06-24; 12,186 road sections; 1,454 section-Mondays with a new report in the next 30 days; 0 crew repairs marked as the same pothole as a request.

| Measure | Chicago model (B1) | Baseline B0 (reports in 90 days) |
|---|---|---|
| Precision, top 1% of roads | 0.0304 (0.0258–0.0354) | 0.0179 (0.0143–0.0217) |
| Recall, top 10% | 0.2765 (0.2505–0.3) | 0.165 (0.1437–0.1852) |
| PR-AUC | 0.0117 (0.0106–0.0131) | 0.0053 (0.0048–0.0074) |
| Brier (lower is better) | 0.0023 (0.0021–0.0025) | 0.0073 (0.0071–0.0074) |
| Winter precision, top 1% | 0.0394 (0.0331–0.0463) | 0.0145 (0.0101–0.0189) |

| Check | Value | Needed | Passed |
|---|---|---|---|
| 1_precision_top_1pct_ratio | 1.6983 | >= 1.15 | yes |
| 2_precision_ci_low_above_baseline | 0.0258 | > 0.0179 | yes |
| 3_pr_auc_ratio | 2.2075 | >= 1.15 | yes |
| 4_winter_precision_ratio | 2.7172 | >= 1.0 | yes |
| 5_brier_better_than_baseline | 0.0023 | < 0.0073 | yes |

## Limits
- Reports in this area start 2025-01-31; where the history is shorter than in Chicago, the model's 3- and 5-year history inputs are shorter too.
- Few new-report weeks (1,454 section-Mondays): wide ranges; a FAIL can mean 'not enough data' as well as 'does not transfer'.
- A report is a report, not an inspection; crew repairs are confirmed potholes.
- Probabilities are Chicago's scale (much higher than here), so the Brier check mainly tests calibration.
