# F4a: Chicago model refresh (TRIAL)

Fresh check on never-used Mondays 2025-08-04 to 2026-09-28 (after the locked test; an extra check, not a new F0 pass/fail test).

## In plain words
- On the newest months, B1 is right 31% of the time in its riskiest 1% of roads (simple rule: 24%; base rate 4.5%). B1 still clearly beats the simple rule (ratio 1.32).
- Percentages after calibration are off by at most 2.5 points in the latest year (without calibration: 1.3 points). Rule for showing percentages: at most 2 points.
- **Suggestion (owner decides, F4-D2): show levels only.**
- Extended learning table repeats the F2 table exactly: yes (31 items checked).

## Fresh check (existing models, forecast-chicago-0.1)

| Model | Precision at top 1% | Recall at top 10% | PR-AUC | Brier | Winter precision | Held-out areas precision |
|---|---|---|---|---|---|---|
| B0_rule | 0.238 (0.210-0.272) | 0.253 | 0.116 | 0.0438 | 0.342 | 0.240 |
| B1_logistic | 0.315 (0.280-0.355) | 0.336 | 0.183 | 0.0405 | 0.447 | 0.289 |
| M_lightgbm | 0.317 (0.284-0.354) | 0.349 | 0.190 | 0.0403 | 0.441 | 0.291 |
| M_lightgbm_without_traffic | 0.317 (0.283-0.354) | 0.348 | 0.190 | 0.0403 | 0.443 | 0.293 |

## Percentage check (B1 trained before 2024-10-07, calibrated on year 1, judged on year 2: 2025-10-06 to 2026-09-28)

| Group (low to high risk) | Raw: predicted | Raw: happened | Calibrated: predicted | Calibrated: happened |
|---|---|---|---|---|
| 1 | 0.5% | 0.8% | 0.6% | 0.8% |
| 2 | 1.0% | 1.1% | 0.9% | 1.1% |
| 3 | 1.6% | 1.5% | 1.3% | 1.6% |
| 4 | 2.3% | 2.1% | 1.7% | 2.1% |
| 5 | 3.0% | 2.6% | 2.3% | 2.6% |
| 6 | 3.9% | 3.3% | 2.9% | 3.3% |
| 7 | 4.9% | 4.5% | 3.8% | 4.5% |
| 8 | 6.4% | 6.2% | 5.0% | 6.2% |
| 9 | 8.8% | 8.8% | 7.2% | 8.8% |
| 10 | 17.1% | 18.4% | 15.9% | 18.4% |

## New model forecast-chicago-0.2
B1 logistic regression, same settings and inputs as forecast-chicago-0.1; trained on Mondays 2012-01-02 to 2026-09-28; calibrator: isotonic, fitted on ['2025-10-06', '2026-09-28'] predictions of a B1 trained before that year.
Files and fingerprints: `models/chicago/f4a-models.json`. The app uses it only after the owner's decision.

Honest limit: after retraining on all data there is no unseen period left for this exact model; the percentage check above uses the same method on a model trained one year earlier, and the app will compare forecasts with real outcomes every month.
