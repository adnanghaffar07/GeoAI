# Transfer test: the Chicago model on Cook northwest (Mount Prospect, Des Plaines, Arlington Heights)

**Outcome: PASS** (PLACEHOLDER pass marks until PI-20 (same as Chicago's).)

Model `forecast-chicago-0.2`, used unchanged. Test Mondays 2022-01-03 to 2026-10-19 (251). Reports 2010-01-05 to 2026-11-24; 12,525 road sections; 635 section-Mondays with a new report in the next 30 days; 0 crew repairs marked as the same pothole as a request.

| Measure | Chicago model (B1) | Baseline B0 (reports in 90 days) |
|---|---|---|
| Precision, top 1% of roads | 0.0058 (0.0043–0.0076) | 0.001 (0.0005–0.0017) |
| Recall, top 10% | 0.3712 (0.3147–0.4338) | 0.14 (0.1035–0.1792) |
| PR-AUC | 0.003 (0.0027–0.0037) | 0.0009 (0.0009–0.0011) |
| Brier (lower is better) | 0.0004 (0.0004–0.0005) | 0.0055 (0.0055–0.0056) |
| Winter precision, top 1% | 0.0078 (0.0048–0.011) | 0.0009 (0.0002–0.0017) |

| Check | Value | Needed | Passed |
|---|---|---|---|
| 1_precision_top_1pct_ratio | 5.8 | >= 1.15 | yes |
| 2_precision_ci_low_above_baseline | 0.0043 | > 0.001 | yes |
| 3_pr_auc_ratio | 3.3333 | >= 1.15 | yes |
| 4_winter_precision_ratio | 8.6667 | >= 1.0 | yes |
| 5_brier_better_than_baseline | 0.0004 | < 0.0055 | yes |

## Limits
- Reports in this area start 2010-01-05; where the history is shorter than in Chicago, the model's 3- and 5-year history inputs are shorter too.
- Few new-report weeks (635 section-Mondays): wide ranges; a FAIL can mean 'not enough data' as well as 'does not transfer'.
- A report is a report, not an inspection; crew repairs are confirmed potholes.
- Probabilities are Chicago's scale (much higher than here), so the Brier check mainly tests calibration.
