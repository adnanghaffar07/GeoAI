# Model Card: Chicago pothole forecast (F2, TRIAL)

**Status:** **TRIAL.** F2 locked test run once on 2026-10-29: outcome **PARTIAL** (2 of 5 checks passed; pass marks are PLACEHOLDER until PI-20). **Chosen for the app: B1 (logistic regression)**, owner decision 2026-10-29. The LightGBM main model was tested but not chosen.
**Version:** `forecast-chicago-0.1` (trained 2026-10-29). Model files and SHA-256 fingerprints: `ml/forecasting/models/chicago/f2-models.json`. The chosen file is `b1_logistic.joblib` (fingerprint `e8a52fa7…6620d3`).
**Reports:** `ml/forecasting/reports/chicago/f2-validation-report.md`, `ml/forecasting/reports/chicago/f2-test-report.md`. Rules: `04-design/forecasting-f0-ground-rules.md`. Plan: `04-design/forecasting-f2-plan.md`. Data: `07-ml/dataset-card-chicago-forecast.md`.

## In plain words

Every Monday the model gives each Chicago road section (about 100 m) a **chance that a new pothole will be reported to the city's 311 service within the next 30 days**. Its job is to help project managers choose **where to inspect first**.

On three years it had never seen (July 2022 – June 2025), the riskiest 1% of sections each Monday got a new report about **29% of the time**, while the average section's chance was 4.8%: about **6× better than chance** and about **33% better than the simple rule** "most reports in the last 90 days". It did as well in 10 community areas it never trained on.

A forecast is a **chance, not a confirmed defect**. It predicts **where people will report** potholes, which is not the same as how worn the road is (see section 6).

## 1. What it predicts

| Item | Value |
|---|---|
| Unit | Road section of 30–129 m (OpenStreetMap primary to unclassified roads; motorways, trunk roads, service roads, alleys and private roads excluded); 71,979 sections, 6,316 km |
| When | Every Monday, using only data from **before** that Monday |
| Answer | Yes if a new, non-duplicate, located City of Chicago 311 pothole report falls within 20 m of the section in the next 30 days |
| Output | A risk score (used for ranking) and a probability (0–1) |

## 2. The model

**B1, logistic regression** (scikit-learn): a "scorecard" in which each input has one fixed weight, so the reason for a high score can be shown (for example "many reports last year, pothole season, cold month"). Numbers are filled with the median where missing (plus a "was missing" flag) and scaled; road type and surface are one-hot categories.

- Trained on 1 million rows drawn from the training sample (all positive rows plus about 4.5% of negative rows, with weights that undo the sampling), training Mondays 2012-01-02 to 2021-05-31.
- **42 inputs** (all built only from data before the Monday):
  - Own history: reports in the last 7, 14, 30, 90 and 365 days; the same 30 days last year; all reports before; reports within ±30 days of the same date in each of the last 3 years; how many of the last 5 years had a report; duplicate reports in the last 30 and 90 days; days since the last report.
  - Neighbours within 200 m: reports in the last 7, 30, 90 and 365 days.
  - Weather (O'Hare and Midway; snow from O'Hare): freeze–thaw days (7, 14, 30), days below freezing, rain (7, 30), heavy-rain days, snow (7, 30), hot days, days since the last freeze.
  - Road: road type, length, lanes, surface, slope, low spot, flood-zone flags, probable-bridge flag, **traffic band and heavy-vehicle band**, bus routes.
  - Time: week of year, month, old/new 311 system.

**Compared models** (same data and periods): **B0** simple rule (reports in the last 90 days, ties broken by freeze–thaw days); **M** LightGBM, with and without the two traffic inputs (`num_leaves 63, learning_rate 0.02, n_estimators 1500, min_child_samples 1000, colsample_bytree 0.7, subsample 0.8`; ranked by raw score, probabilities by isotonic calibration).

## 3. Data periods

| Period | Mondays | Use |
|---|---|---|
| Training | 2012-01-02 to 2021-05-31 | Fitting |
| Validation | 2021-07-05 to 2022-05-30 (48 Mondays) | Choosing settings, one improvement round, calibration |
| **Locked test** | 2022-07-04 to 2025-06-30 (157 Mondays, 11.3 million section-Mondays) | **Used once**, 2026-10-29 |
| Held-out areas | Community areas 1, 5, 6, 19, 28, 34, 64, 70, 72, 75 | Never trained on; scored separately |

A row is used only if its 30-day answer window ends before the next period starts (purge).

## 4. Results on the locked test (95% ranges)

| Model | Precision at top 1% | Recall at top 10% | PR-AUC | Brier (lower is better) |
|---|---|---|---|---|
| B0 simple rule | 0.215 (0.200–0.230) | 0.240 | 0.103 | 0.046 |
| **B1 (chosen)** | **0.285 (0.266–0.305)** | **0.313** | **0.167** | **0.0429** |
| M LightGBM | 0.293 (0.273–0.313) | 0.321 | 0.168 | 0.043 |
| M without traffic (tested main model) | 0.293 (0.273–0.313) | 0.321 | 0.169 | 0.0430 |

Base rate 4.8%. **Winter (Nov–Apr):** B1 0.369, M 0.376 (base rate 6.3%). **Held-out areas:** B1 0.279, M 0.283 (base rate 5.4%).

**Pass-mark checks** (main model M without traffic against the best baseline, which was B1 on every measure): precision ratio 1.027 (needed 1.15) NO; lower end of precision range above B1 NO; PR-AUC ratio 1.008 (needed 1.15) NO; Brier better than both NO (0.0430 vs 0.0429, a tie); winter ratio 1.02 yes; held-out areas ratio 1.014 yes. **Outcome PARTIAL.**

**Why B1:** LightGBM was only 1–3% better than B1, inside the uncertainty ranges, and no better on probabilities. B1 is as good in practice, easier to explain to project managers and partners, smaller and faster to run.

## 5. Calibration (do the probabilities match what happened?)

Test period, ten equal groups from lowest to highest risk:

| Group | B1 predicted | Happened |
|---|---|---|
| 1 (lowest) | 0.5% | 0.9% |
| 5 | 3.0% | 2.9% |
| 9 | 8.1% | 8.2% |
| 10 (highest) | 15.1% | 16.9% |

B1's probabilities are close to reality overall. Fewer reports came in during 2022–2025 (4.8% of section-Mondays) than in the validation year (6.4%), so probabilities should be **re-checked on recent data before percentages are shown in the app** (F4).

## 6. Outside check: Cook County pavement condition (never an input)

The 2025 Cook County PCI survey (Lake Township layer, inside Chicago) was matched to 20,396 sections within 15 m. **No real link was found** between forecast risk and road condition: Spearman correlation +0.025; mean PCI of the riskiest 10% of sections 58.3 vs 58.0 for the rest. (This check used the tested LightGBM main model; B1 ranks almost the same.)

**Reading:** the model forecasts **311 reports**, which depend on reporting habits, traffic of people and recent pothole activity, not only on surface wear. One survey year, so this is a limited check, but it must be said clearly: **a high forecast does not mean a worn road, and a low forecast does not mean a good road.**

## 7. Limits and risks

- The answer is a **311 report**, not an inspection: busy, active neighbourhoods report more, so the forecast can under-serve areas that report less. Show it as "where reports are likely", next to the app's own verified findings.
- Roads are today's OpenStreetMap map, used for all years.
- Two airport weather stations cover the whole city.
- **The tested B1 uses the traffic and heavy-vehicle bands**, whose counts are mostly dated 2022–2025 (decision B). For LightGBM, removing them changed nothing. A B1 without traffic would be a new model and needs its own check on later data before it replaces this one.
- The test period is now used. Any new pass/fail attempt needs a new, later test period (F0 section 7).
- Pass marks are placeholders until PI-20; engineering check pending (PI-22).

## 7b. F4a refresh (2026-10-30)

- **Fresh check** on never-used Mondays 2025-08-04 to 2026-09-28 (after the locked test): B1 precision at top 1% **0.315** (0.280-0.355), simple rule 0.238 (ratio 1.32); winter 0.447; held-out areas 0.289; base rate 4.5%. LightGBM 0.317.
- **Percentages:** raw B1 was within 1.3 points of what happened in every tenth of the latest year; after calibration it was up to 2.5 points off. Decision F4-D2: **the app shows levels only** (high = top 1% each week, medium = next 9%), with reasons; raw percentages are compared with outcomes every month.
- **Model used by the app: `forecast-chicago-0.2`**: B1 with the same settings, trained on Mondays 2012-01-02 to 2026-09-28, no calibrator (`ml/forecasting/models/chicago/f4a-models.json`). Report: `ml/forecasting/reports/chicago/f4a-refresh-report.md`.

## 8. Intended use

- **For:** ranking road sections to help project managers decide where to inspect first; shown as a **TRIAL** forecast in the app (F4), with the reasons for each score.
- **Not for:** stating that a road has a defect, judging road condition or repair budgets, comparing neighbourhoods, or any area outside Chicago (other areas get Level 1 "risk factors" only, never an untested percentage).
- **Before F4:** retrain on data up to the latest Monday with the same settings, and re-check the probabilities on the most recent year.
