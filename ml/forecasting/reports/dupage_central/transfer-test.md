# Transfer test: the Chicago model on Central DuPage (Lombard, Glen Ellyn, Oak Brook, Wheaton)

**Outcome: PASS** (PLACEHOLDER pass marks until PI-20 (same as Chicago's).)

Model `forecast-chicago-0.2`, used unchanged. Test Mondays 2025-01-06 to 2026-10-19 (94). Reports 2013-02-12 to 2026-11-19; 10,160 road sections; 1,604 section-Mondays with a new report in the next 30 days; 0 crew repairs marked as the same pothole as a request.

| Measure | Chicago model (B1) | Baseline B0 (reports in 90 days) |
|---|---|---|
| Precision, top 1% of roads | 0.0159 (0.0126–0.0192) | 0.0084 (0.006–0.0112) |
| Recall, top 10% | 0.3353 (0.2957–0.3768) | 0.1559 (0.1257–0.196) |
| PR-AUC | 0.0059 (0.0053–0.0068) | 0.0029 (0.0027–0.0039) |
| Brier (lower is better) | 0.0019 (0.0018–0.002) | 0.0069 (0.0067–0.007) |
| Winter precision, top 1% | 0.0207 (0.0155–0.026) | 0.0116 (0.0073–0.0162) |

| Check | Value | Needed | Passed |
|---|---|---|---|
| 1_precision_top_1pct_ratio | 1.8929 | >= 1.15 | yes |
| 2_precision_ci_low_above_baseline | 0.0126 | > 0.0084 | yes |
| 3_pr_auc_ratio | 2.0345 | >= 1.15 | yes |
| 4_winter_precision_ratio | 1.7845 | >= 1.0 | yes |
| 5_brier_better_than_baseline | 0.0019 | < 0.0069 | yes |

## Limits
- Reports in this area start 2013-02-12; where the history is shorter than in Chicago, the model's 3- and 5-year history inputs are shorter too.
- Few new-report weeks (1,604 section-Mondays): wide ranges; a FAIL can mean 'not enough data' as well as 'does not transfer'.
- A report is a report, not an inspection; crew repairs are confirmed potholes.
- Probabilities are Chicago's scale (much higher than here), so the Brier check mainly tests calibration.
