# F2 locked test report (Chicago forecast, TRIAL)

Run once with the owner's go-ahead: 2026-10-29T20:44:56+00:00 – 2026-10-29T21:21:33+00:00. Test Mondays 2022-07-04 to 2025-06-30. Main model: **M_lightgbm_without_traffic**.

## Outcome: **PARTIAL** (pass marks are PLACEHOLDER until the partner confirms them, PI-20)

| Check | Main model | Best baseline | Ratio | Needed | Passed |
|---|---|---|---|---|---|
| 1_precision_top_1pct_ratio | 0.2928 | 0.2852 | 1.027 | >= 1.15 | NO |
| 1b_precision_range_above_baseline | 0.2726 | 0.2852 |  |  | NO |
| 2_pr_auc_ratio | 0.1686 | 0.1673 | 1.008 | >= 1.15 | NO |
| 3_brier_better_than_both | 0.043 | 0.0429 |  |  | NO |
| 4_winter_precision_ratio | 0.3761 | 0.3687 | 1.02 | >= 1.0 | yes |
| 5_held_out_areas_precision_ratio | 0.283 | 0.2791 | 1.014 | >= 1.0 | yes |

## Results
### All sections
157 Mondays, 11,300,703 section-Mondays. Values with 95% ranges.

| Model | Precision at top 1% (higher better) | Recall at top 10% | PR-AUC | Brier (lower better) | Base rate |
|---|---|---|---|---|---|
| B0 simple rule | 0.215 (0.200–0.230) | 0.240 (0.236–0.244) | 0.103 (0.095–0.111) | 0.046 (0.043–0.049) | 0.0478 |
| B1 statistics (logistic regression) | 0.285 (0.266–0.305) | 0.313 (0.310–0.317) | 0.167 (0.153–0.180) | 0.043 (0.040–0.046) | 0.0478 |
| M main model (LightGBM) | 0.293 (0.273–0.313) | 0.321 (0.318–0.325) | 0.168 (0.155–0.180) | 0.043 (0.040–0.046) | 0.0478 |
| M without traffic | 0.293 (0.273–0.313) | 0.321 (0.318–0.324) | 0.169 (0.155–0.181) | 0.043 (0.040–0.046) | 0.0478 |

### Winter (Nov–Apr)
77 Mondays, 5,542,383 section-Mondays. Values with 95% ranges.

| Model | Precision at top 1% (higher better) | Recall at top 10% | PR-AUC | Brier (lower better) | Base rate |
|---|---|---|---|---|---|
| B0 simple rule | 0.273 (0.251–0.295) | 0.232 (0.226–0.238) | 0.126 (0.115–0.136) | 0.058 (0.053–0.063) | 0.0628 |
| B1 statistics (logistic regression) | 0.369 (0.339–0.397) | 0.317 (0.312–0.321) | 0.202 (0.186–0.215) | 0.055 (0.050–0.059) | 0.0628 |
| M main model (LightGBM) | 0.376 (0.345–0.404) | 0.323 (0.318–0.327) | 0.202 (0.188–0.214) | 0.055 (0.050–0.060) | 0.0628 |
| M without traffic | 0.376 (0.345–0.405) | 0.323 (0.318–0.328) | 0.202 (0.188–0.214) | 0.055 (0.050–0.060) | 0.0628 |

### Held-out community areas (never trained on)
157 Mondays, 1,834,231 section-Mondays. Values with 95% ranges.

| Model | Precision at top 1% (higher better) | Recall at top 10% | PR-AUC | Brier (lower better) | Base rate |
|---|---|---|---|---|---|
| B0 simple rule | 0.203 (0.184–0.220) | 0.227 (0.221–0.234) | 0.109 (0.099–0.119) | 0.051 (0.048–0.055) | 0.0543 |
| B1 statistics (logistic regression) | 0.279 (0.253–0.305) | 0.301 (0.295–0.306) | 0.170 (0.154–0.184) | 0.049 (0.045–0.052) | 0.0543 |
| M main model (LightGBM) | 0.286 (0.260–0.312) | 0.304 (0.298–0.309) | 0.173 (0.158–0.186) | 0.048 (0.045–0.052) | 0.0543 |
| M without traffic | 0.283 (0.258–0.308) | 0.303 (0.298–0.308) | 0.173 (0.158–0.186) | 0.048 (0.045–0.052) | 0.0543 |

## Calibration of the main model (test)
| Predicted (mean) | Happened | Rows |
|---|---|---|
| 0.0067 | 0.0065 | 1,130,071 |
| 0.0114 | 0.0116 | 1,130,071 |
| 0.016 | 0.0163 | 1,130,071 |
| 0.0221 | 0.0212 | 1,130,070 |
| 0.0289 | 0.0272 | 1,130,070 |
| 0.0373 | 0.0349 | 1,130,070 |
| 0.0498 | 0.0453 | 1,130,070 |
| 0.0671 | 0.0594 | 1,130,070 |
| 0.0968 | 0.0849 | 1,130,070 |
| 0.2073 | 0.1713 | 1,130,070 |

## Outside check: Cook County pavement condition 2025 (never an input)
```
{
  "matched_sections": 20396,
  "spearman_risk_vs_pci": 0.025,
  "p_value": 0.0003496482218012836,
  "mean_pci_riskiest_10pct": 58.3,
  "mean_pci_other_90pct": 58.0,
  "reading": "a negative correlation (riskier sections have lower PCI) supports the forecast; PCI is from 2025, one survey"
}
```

## Honest limits
- The answer is a **311 pothole report**, not an inspection: busy, active neighbourhoods report more.
- Roads are today's OpenStreetMap for all years; two airport weather stations cover the whole city.
- Traffic counts are mostly from 2022–2025 (decision B); the model was also scored without traffic.
- A forecast is a **chance**, not a confirmed defect. Shown in the app only as a TRIAL forecast to help choose where to inspect.
- The test period is now used. Any new attempt needs a new, later test period (F0 section 7).
