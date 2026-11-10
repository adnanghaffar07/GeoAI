# Transfer test: the Chicago model on City of Naperville

**Outcome: PASS** (PLACEHOLDER pass marks until PI-20 (same as Chicago's).)

Model `forecast-chicago-0.2`, used unchanged. Test Mondays 2025-01-06 to 2026-10-05 (92). Reports 2023-01-02 to 2026-11-09; 11,697 road sections; 2,255 section-Mondays with a new report in the next 30 days; 170 crew repairs marked as the same pothole as a request.

| Measure | Chicago model (B1) | Baseline B0 (reports in 90 days) |
|---|---|---|
| Precision, top 1% of roads | 0.0407 (0.0324–0.0497) | 0.0262 (0.0193–0.0336) |
| Recall, top 10% | 0.5342 (0.4877–0.577) | 0.1847 (0.16–0.2087) |
| PR-AUC | 0.0206 (0.0178–0.0236) | 0.0116 (0.0106–0.0152) |
| Brier (lower is better) | 0.0023 (0.0021–0.0025) | 0.0072 (0.007–0.0074) |
| Winter precision, top 1% | 0.0563 (0.0425–0.0694) | 0.029 (0.0187–0.0413) |

| Check | Value | Needed | Passed |
|---|---|---|---|
| 1_precision_top_1pct_ratio | 1.5534 | >= 1.15 | yes |
| 2_precision_ci_low_above_baseline | 0.0324 | > 0.0262 | yes |
| 3_pr_auc_ratio | 1.7759 | >= 1.15 | yes |
| 4_winter_precision_ratio | 1.9414 | >= 1.0 | yes |
| 5_brier_better_than_baseline | 0.0023 | < 0.0072 | yes |

## Limits
- The city's history starts in 2023, so the model's 3- and 5-year history inputs are shorter than in Chicago.
- Few reports (about 150-190 a year): wide ranges; a FAIL can mean 'not enough data' as well as 'does not transfer'.
- A report is a report, not an inspection; crew repairs are confirmed potholes.
- Probabilities are Chicago's scale (much higher than here), so the Brier check mainly tests calibration.
