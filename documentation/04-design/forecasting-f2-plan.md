# Forecasting F2: Proof-of-Concept Plan (Chicago)

**Status:** **Approved 2026-10-29** (owner: "ok go to f2", including the purge and the go-ahead gate). **Built and tested 2026-10-29** (`ml/forecasting/f2_*.py`, `metrics.py`; 46 forecasting tests; a Chicago-sized trial on made-up data ran in ~5 min with 2.4 GB). Waiting for the owner's run of `scripts\forecast-f2.bat`. Uses the frozen F0 rules (`forecasting-f0-ground-rules.md` sections 2–7) and the F1/F1b data (`07-ml/dataset-card-chicago-forecast.md`). Pass marks stay PLACEHOLDER until PI-20. **Complete 2026-10-29:** validated twice (one improvement round), locked test run once, outcome **PARTIAL**; **B1 chosen for the app** (section 11, `07-ml/model-card-forecast-chicago.md`).

## In plain words

F2 answers one question: **can a model predict which Chicago road sections will get a new pothole report in the next 30 days, clearly better than simple rules?**

1. Build a **learning table**: one row per road section per Monday (2012–2025), holding only what was known **before** that Monday, plus the answer (was a new pothole reported in the next 30 days?).
2. Train three models on 2012–2021: the **simple rule (B0)**, a **basic statistics model (B1)**, and the **main model (M, LightGBM)**.
3. Compare them on the **validation year** (July 2021 – June 2022). Settings may be tuned here only.
4. **The owner looks at the validation results and says "run the test".** Only then is the **locked test** (July 2022 – June 2025) run, **once**, and the pass marks applied.

## 1. The learning table

| Part | Content (all from before the Monday, F0 section 4) |
|------|------------------------------------------------------|
| Answer (label) | 1 if a non-duplicate, located 311 pothole report was created within 20 m of the section in the Monday + 29 days, else 0 |
| Pothole history | reports on the section in the last 30 / 90 / 365 days; in the same 30 days one year earlier; days since the last report |
| Neighbours | reports on sections within 200 m in the last 30 / 90 / 365 days |
| Weather (nearest airport; snow always O'Hare) | freeze–thaw days in the last 7 / 14 / 30 days; days below 0 °C (30); rain total (7, 30); heavy-rain days ≥ 25 mm (30); snowfall (7, 30); hot days ≥ 32 °C (30); days since the last freeze |
| Road | road type, length, lanes (if mapped), surface (if mapped) |
| Use | traffic band and heavy-vehicle band (quiet / medium / busy / very busy; missing = its own value), number of bus routes |
| Place | slope, low spot, 1% and 0.2% flood zone, "probably a bridge" flag (slope > 10% or low spot beyond ±5 m) |
| Time | week of year, month, old/new 311 system |

**Size:** about 72,000 sections × 700 Mondays ≈ 50 million rows, too big for laptop memory as one table. So:
- Features are computed for all rows with compact arrays (counts stored as small integers).
- **Training** uses all positive rows and a random 10% of the negative rows (weighted ×10, so probabilities stay right); fixed random seed.
- **Validation and test** use **every** row, week by week (no sampling), so the measures are exact.

## 2. No-cheating safeguards

| Risk | Safeguard |
|------|-----------|
| Inputs from the future | Every input uses reports and weather dated **before** the Monday; a test checks this on made-up data |
| Answer windows crossing periods | Rows whose 30-day answer window reaches into the next period are left out ("purge"): the last 4 Mondays of training and of validation |
| Held-out places | Sections in the 10 held-out community areas are never training rows (their past reports may still be inputs for neighbours, as a city would know them) |
| Locked test used twice | A usage file (`reports/chicago/f2-test-usage.json`) blocks a second run, as in P8.5; the run also requires the owner's go-ahead flag |
| Traffic counts from 2022–2025 (decision B) | The main model is trained **with and without** traffic; both results are reported. If traffic makes results suspiciously better, it is dropped |
| Cook County PCI (2025) | Never an input. Used after the test only as an outside check (do high-risk sections have lower PCI?) |

## 3. Models

| Name | What | Probabilities for the Brier score |
|------|------|-----------------------------------|
| **B0 rule** (F0) | Rank by reports in the last 90 days, ties broken by freeze–thaw days in the last 14 days | Rate of positives per "reports in 90 days" value, measured on training data |
| **B1 logistic regression** | Same inputs, standardised; missing values filled with the training median plus a "was missing" flag | Its own output |
| **M LightGBM** | Same inputs; settings chosen on validation from a small fixed list; probabilities calibrated on validation (isotonic) | Calibrated output; per-section "why" from feature contributions |

## 4. Measures (F0 section 6)

Precision at top 1% (average over Mondays), recall at top 10%, PR-AUC, Brier score with calibration chart, base rate. Reported for all sections, winter (Nov–Apr), and the held-out areas, each with 95% bootstrap ranges (1,000 resamples of Mondays). Pass marks from `config/acceptance-thresholds.yaml`.

## 5. Steps and owner actions

| Step | What | Owner action | Time on the laptop |
|------|------|--------------|--------------------|
| F2a | Build the learning table + checks (base rate per year, no future inputs, row counts) | Double-click `scripts\forecast-f2.bat` | ~15–30 min |
| F2b | Train B0, B1, M (with and without traffic) and report **validation** results | Same script | ~20–40 min |
| — | Owner reads the validation report with Claude | **Decide: run the locked test?** | — |
| F2c | Locked test **once**, pass/fail against the marks, F2 report + model card; Cook County outside check | `scripts\forecast-f2-test.bat` (asks for confirmation) | ~10–20 min |

New Python packages (in `requirements-forecast.txt`): numpy, scipy, scikit-learn, lightgbm. No GPU; the laptop is enough.

Outputs: `ml/forecasting/reports/chicago/f2-validation-report.md`, `f2-test-report.md`, `documentation/07-ml/model-card-forecast-chicago.md`, model file `ml/forecasting/models/chicago/` with its fingerprint (small; may be committed). The learning table stays in `forecasting/data/` (git-ignored).

## 6. Tests (Claude's side, before the owner runs anything)

Made-up mini city: labels and every history/neighbour/weather window checked by hand; the "before the Monday" rule; purge; held-out areas never in training; sampling weights; each measure on known answers; the test-usage lock; a full small run end to end.

## 7. Done when

- [x] Code and tests built (2026-10-29)
- [x] Learning table built; checks pass (no future inputs; base rate reported per year)
- [x] B0, B1, M trained; validation report read by the owner (twice: before and after the improvement round)
- [x] Owner's go-ahead recorded; locked test run once (2026-10-29)
- [x] Pass / partial / fail recorded in `project-decisions.md` with honest limits: **PARTIAL**
- [x] Model card written (`07-ml/model-card-forecast-chicago.md`) (what it predicts, data, measures, limits, "TRIAL", "not a confirmed defect")

## 8. Decisions for the owner

1. Approve this plan.
2. Approve the **purge** (dropping the last 4 Mondays of training and of validation so answer windows never cross into the next period). It is a safety detail inside the frozen periods, not a change to them.
3. Approve the **go-ahead gate**: the locked test runs only after you have seen the validation results and said so.

## 9. Build notes (2026-10-29, details inside the approved plan)

- **Purge** is applied as "the 30-day answer window must end before the next period starts" (the last ~5 Mondays of training and of validation).
- **Days below freezing** = days whose maximum stayed below 0 °C (frozen all day); freeze–thaw = max above 0 and min below 0.
- **Training sample**: all positives and 10% of negatives, both shrunk together to at most 2.5 million rows; weights undo the sampling. B1 uses a random 1 million of those rows (a linear model needs no more).
- **Main model ranking** uses the raw LightGBM score; the isotonic calibration (fitted on validation) is used only for probabilities and the Brier score. Found in the Chicago-sized trial: calibrating the ranking created ties and lowered precision at the top.
- **PR-AUC ranges** use per-Monday score histograms, shifted to the exact PR-AUC.
- Model files: `forecasting/models/` with SHA-256 fingerprints in `f2-models.json`; the locked test refuses changed files.
- **Neighbours within 200 m** are found with a k-d tree on section middles in meters (seconds). The first version asked the database to compare every pair without a spatial index and stalled for over an hour on the owner's first run (2026-10-29); fixed the same day.
- **Save-as-you-go (owner request 2026-10-29):** every long step shows progress (step X of Y, time spent, time left) and saves its work as it goes: report matching year by year, then history, neighbours, weather and facts; in training the sample, B0/B1, each LightGBM setting, calibration, the no-traffic model and each model's scores. Double-clicking the script again continues after the last saved part. If the data load or settings change, that part starts fresh. `--restart` forces a fresh start. The locked test also continues after a stop (still one test: nothing is shown until it finishes) and is locked once finished.

## 10. Improvement round (owner decision 2026-10-29, after the first validation report)

First validation: the main model clearly beat the simple rule B0 (precision at top 1% 0.344 vs 0.276; PR-AUC 0.230 vs 0.146) and was as good in held-out areas, but only ~2–3% better than B1 (pass mark: 15% better than the **best** baseline). Traffic made no difference (0.344 with, 0.345 without).

Agreed before seeing any new result:
- **One** improvement round, using the validation year only: new inputs (reports in the last 7 / 14 days, also for neighbours; reports around the same date in each of the last 3 years; how many of the last 5 years had a report; all reports before the Monday; duplicate reports in the last 30 / 90 days) and two more LightGBM settings (slower learning, more trees).
- Then the locked test is run **whatever the validation result**, with the main model **without traffic** (no gain, removes the 2022–2025 count concern). Pass marks unchanged.
- If the main model is still not clearly better than B1, the report says so, and B1 (simpler, easier to explain) is considered for the app.

## 11. Result (2026-10-29)

- **Validation run 2** (after the improvement round): precision at top 1% B0 0.276, B1 0.357, M 0.364, M without traffic 0.365; ratio to B1 still ~1.02.
- **Locked test, run once** (2022-07-04 to 2025-06-30, 157 Mondays), main model M without traffic: precision at top 1% 0.293 vs B1 0.285 (ratio 1.027, needed 1.15); PR-AUC 0.169 vs 0.167; Brier 0.0430 vs 0.0429 (tie, counts as not better); winter 0.376 vs 0.369; held-out areas 0.283 vs 0.279. **Outcome PARTIAL** (checks 4 and 5 passed).
- Cook County PCI outside check: no link between forecast risk and road condition (Spearman +0.025).
- During the run: the lock was first started with the with-traffic model by mistake and the Cook County query hit a PostGIS error; both corrected before any main-model result was seen (`project-decisions.md`).
- **Owner decision: B1 is the app's forecast model.** Details and limits: `07-ml/model-card-forecast-chicago.md`.
