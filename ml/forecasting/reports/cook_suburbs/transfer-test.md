# Transfer test: the Chicago model on Cook suburbs (La Grange Park, Elk Grove Village, Schaumburg)

**Outcome: PASS** (PLACEHOLDER pass marks until PI-20 (same as Chicago's).)

Model `forecast-chicago-0.2`, used unchanged. Test Mondays 2025-01-06 to 2026-10-19 (94). Reports 2008-06-11 to 2026-11-19; 9,635 road sections; 768 section-Mondays with a new report in the next 30 days; 0 crew repairs marked as the same pothole as a request.

| Measure | Chicago model (B1) | Baseline B0 (reports in 90 days) |
|---|---|---|
| Precision, top 1% of roads | 0.0191 (0.0127–0.026) | 0.009 (0.0055–0.0134) |
| Recall, top 10% | 0.4438 (0.3723–0.5093) | 0.1612 (0.1253–0.2012) |
| PR-AUC | 0.0201 (0.0185–0.0229) | 0.0112 (0.0108–0.0121) |
| Brier (lower is better) | 0.0011 (0.0009–0.0012) | 0.0061 (0.006–0.0062) |
| Winter precision, top 1% | 0.0352 (0.024–0.0477) | 0.0144 (0.007–0.0228) |

| Check | Value | Needed | Passed |
|---|---|---|---|
| 1_precision_top_1pct_ratio | 2.1222 | >= 1.15 | yes |
| 2_precision_ci_low_above_baseline | 0.0127 | > 0.009 | yes |
| 3_pr_auc_ratio | 1.7946 | >= 1.15 | yes |
| 4_winter_precision_ratio | 2.4444 | >= 1.0 | yes |
| 5_brier_better_than_baseline | 0.0011 | < 0.0061 | yes |

## Limits
- Reports in this area start 2008-06-11; where the history is shorter than in Chicago, the model's 3- and 5-year history inputs are shorter too.
- Few new-report weeks (768 section-Mondays): wide ranges; a FAIL can mean 'not enough data' as well as 'does not transfer'.
- A report is a report, not an inspection; crew repairs are confirmed potholes.
- Probabilities are Chicago's scale (much higher than here), so the Brier check mainly tests calibration.
