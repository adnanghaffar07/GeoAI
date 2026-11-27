# F6: do county-trained models beat the Chicago model? (2026-11-27)

**Result: no. The Chicago model (`forecast-chicago-0.2`) stays for all tested areas.** Development evidence only; no locked test was re-run and no tested level changed.

## Question
The tested county areas (Central DuPage, Cook suburbs, Cook northwest, Naperville, Aurora) use the Chicago model unchanged. Would a model that also learns from the counties' own pothole reports forecast them better?

## Method (fixed before any result)
- Leave one area out: each area is scored by models trained without it.
- Scored on the Mondays of the area's own transfer test (the same ones used to test the Chicago model).
- C = Chicago B1 as in the app. B0 = simple rule. K1 = scorecard (same inputs, minus the old/new-311 switch) trained on the other four counties only. K2 = the same scorecard trained on Chicago training years plus the other four counties, counties weighted to count as much as Chicago.
- "Clear improvement": K beats C on top-1% precision and PR-AUC in at least 4 of 5 areas, and the average precision ratio K / C is at least 1.10.
- Code: `ml/forecasting/f6_county_model.py`, run with `scripts/forecast-f6-county-model.bat`. Report: `ml/forecasting/reports/counties/f6-county-model-report.md`.

## Result (top-1% precision, C / K1 / K2)
| Area | C | K1 | K2 |
|---|---|---|---|
| Central DuPage | 0.0159 | 0.0127 | 0.0162 |
| Cook suburbs | 0.0191 | 0.0220 | 0.0183 |
| Cook northwest | 0.0058 | 0.0059 | 0.0059 |
| Naperville | 0.0407 | 0.0347 | 0.0392 |
| Aurora | 0.0304 | 0.0211 | 0.0326 |

K1 beat C in 1 of 5 areas (average ratio 0.90); K2 in 1 of 5 (average 1.01). Differences are inside the 95% ranges almost everywhere. One bright spot: K1's PR-AUC in Cook northwest was 0.0070 against 0.0030 for C, but its top-1% precision was the same, so it is not a reliable gain.

## What it means
- Retraining with the counties' own reports does not improve the ranking. The Chicago model already carries what the scorecard can learn from these inputs (earlier, LightGBM was only 1 to 3% better than B1 on the same inputs).
- Gains now have to come from **new information**, not from a different model: more months of county reports (each area has one to four winters), the app's own verified findings and inspection outcomes as ground truth, or new inputs that cause potholes.
- Areas with no reports cannot be helped by this: they have no local history to learn from.

## Limits
- Development evidence: the scoring Mondays were already used to test C. A real pass/fail test of any new model needs Mondays after 2026-11-24 (spring or summer 2027).
- Reports, not potholes. Pass marks are placeholders (PI-20).
- One input (position 34, probably a traffic band) was empty in some counties; the scorecard skipped it.
