# F2 validation report (Chicago forecast, TRIAL)

Model version forecast-chicago-0.1, trained 2026-10-29. Training Mondays 2012-01-02 to 2021-05-31; validation Mondays 2021-07-05 to 2022-05-30 (the last Mondays of each period are left out so a 30-day answer never reaches the next period).

**This is the validation year. Settings were chosen and probabilities calibrated on it, so these numbers are a little optimistic. The locked test (July 2022 – June 2025) has not been touched.**

## In plain words
- Of the 1% of road sections each model ranks riskiest every Monday, the main model is right 36% of the time; the best simple baseline is right 36% of the time (ratio 1.02; the pass mark asks for 1.15).
- Overall ranking quality (PR-AUC): main 0.247 vs best baseline 0.242 (ratio 1.02; pass mark 1.15).
- Without traffic the main model scores precision 0.365 and PR-AUC 0.247 (with traffic: 0.364 / 0.247). A large gap would mean traffic matters a lot; decision B says we then check it is not leaking the future.
- Base rate: 6.4% of section-Mondays get a new pothole report within 30 days.

## Results
### All sections
48 Mondays, 3,454,992 section-Mondays. Values with 95% ranges.

| Model | Precision at top 1% (higher better) | Recall at top 10% | PR-AUC | Brier (lower better) | Base rate |
|---|---|---|---|---|---|
| B0 simple rule | 0.276 (0.228–0.322) | 0.250 (0.243–0.258) | 0.146 (0.117–0.172) | 0.058 (0.049–0.068) | 0.0639 |
| B1 statistics (logistic regression) | 0.357 (0.302–0.411) | 0.310 (0.304–0.316) | 0.242 (0.203–0.270) | 0.055 (0.045–0.064) | 0.0639 |
| M main model (LightGBM) | 0.364 (0.310–0.416) | 0.316 (0.310–0.323) | 0.247 (0.209–0.275) | 0.054 (0.045–0.063) | 0.0639 |
| M without traffic | 0.365 (0.310–0.418) | 0.316 (0.310–0.323) | 0.247 (0.209–0.274) | 0.054 (0.045–0.063) | 0.0639 |

### Winter (Nov–Apr)
26 Mondays, 1,871,454 section-Mondays. Values with 95% ranges.

| Model | Precision at top 1% (higher better) | Recall at top 10% | PR-AUC | Brier (lower better) | Base rate |
|---|---|---|---|---|---|
| B0 simple rule | 0.340 (0.270–0.417) | 0.239 (0.230–0.248) | 0.172 (0.136–0.203) | 0.073 (0.058–0.088) | 0.0822 |
| B1 statistics (logistic regression) | 0.430 (0.346–0.518) | 0.309 (0.304–0.316) | 0.283 (0.248–0.309) | 0.069 (0.055–0.084) | 0.0822 |
| M main model (LightGBM) | 0.433 (0.350–0.519) | 0.314 (0.307–0.321) | 0.287 (0.253–0.312) | 0.067 (0.054–0.081) | 0.0822 |
| M without traffic | 0.435 (0.351–0.523) | 0.313 (0.306–0.321) | 0.287 (0.252–0.312) | 0.067 (0.054–0.081) | 0.0822 |

### Held-out community areas (never trained on)
48 Mondays, 560,784 section-Mondays. Values with 95% ranges.

| Model | Precision at top 1% (higher better) | Recall at top 10% | PR-AUC | Brier (lower better) | Base rate |
|---|---|---|---|---|---|
| B0 simple rule | 0.275 (0.228–0.322) | 0.247 (0.237–0.258) | 0.148 (0.120–0.174) | 0.063 (0.053–0.073) | 0.0692 |
| B1 statistics (logistic regression) | 0.362 (0.304–0.419) | 0.304 (0.294–0.315) | 0.240 (0.203–0.266) | 0.059 (0.049–0.069) | 0.0692 |
| M main model (LightGBM) | 0.380 (0.326–0.434) | 0.311 (0.300–0.323) | 0.245 (0.211–0.269) | 0.058 (0.049–0.068) | 0.0692 |
| M without traffic | 0.381 (0.325–0.436) | 0.311 (0.300–0.323) | 0.244 (0.211–0.269) | 0.058 (0.049–0.068) | 0.0692 |

## Calibration of the main model (validation)
Each row is a tenth of all section-Mondays: when the model says X%, how often did it happen?

| Predicted (mean) | Happened | Rows |
|---|---|---|
| 0.0071 | 0.0071 | 345,500 |
| 0.0132 | 0.0133 | 345,500 |
| 0.0181 | 0.018 | 345,499 |
| 0.0258 | 0.0259 | 345,499 |
| 0.0332 | 0.0331 | 345,499 |
| 0.0437 | 0.0437 | 345,499 |
| 0.0579 | 0.0578 | 345,499 |
| 0.0776 | 0.0776 | 345,499 |
| 0.1129 | 0.1129 | 345,499 |
| 0.2494 | 0.2495 | 345,499 |

## What the main model relies on most (top 15, LightGBM gain)
| Input | Gain |
|---|---|
| reports_365d | 14860908.3 |
| week_of_year | 7026104.4 |
| days_since_last_report | 6822287.4 |
| reports_same_season_3y | 5574471.3 |
| month | 2354205.1 |
| below_freezing_days_30d | 2038191.9 |
| snow_mm_30d | 1906849.9 |
| new_311_system | 1769713.2 |
| reports_all_before | 1724912.9 |
| years_with_reports_5y | 1249237.3 |
| freeze_thaw_30d | 1136446.2 |
| neighbour_reports_365d | 1110906.2 |
| rain_mm_30d | 818945.6 |
| neighbour_reports_30d | 696280.9 |
| length_m | 681979.9 |

## Settings tried (chosen by validation PR-AUC)
| Settings | Validation PR-AUC |
|---|---|
| {"num_leaves": 31, "learning_rate": 0.05, "n_estimators": 400, "min_child_samples": 200} | 0.246 |
| {"num_leaves": 63, "learning_rate": 0.05, "n_estimators": 600, "min_child_samples": 200} | 0.2459 |
| {"num_leaves": 15, "learning_rate": 0.1, "n_estimators": 300, "min_child_samples": 200} | 0.2455 |
| {"num_leaves": 31, "learning_rate": 0.03, "n_estimators": 1200, "min_child_samples": 500, "colsample_bytree": 0.8, "subsample": 0.8, "subsample_freq": 1} | 0.247 |
| {"num_leaves": 63, "learning_rate": 0.02, "n_estimators": 1500, "min_child_samples": 1000, "colsample_bytree": 0.7, "subsample": 0.8, "subsample_freq": 1} | 0.2474 |

Training rows: {'positives': 2859384, 'negatives': 26806248, 'positive_fraction': 0.45126282109876786, 'negative_fraction': 0.04512628210987679}

## Base rate per year (training and validation Mondays)
| Year | Share of section-Mondays with a new report in 30 days |
|---|---|
| 2012 | 0.0872 |
| 2013 | 0.1238 |
| 2014 | 0.1496 |
| 2015 | 0.1099 |
| 2016 | 0.0906 |
| 2017 | 0.0976 |
| 2018 | 0.0928 |
| 2019 | 0.0741 |
| 2020 | 0.0548 |
| 2021 | 0.0476 |
| 2022 | 0.1044 |

## Next
The owner reads this with Claude and decides whether to run the locked test (once), and with or without traffic.
