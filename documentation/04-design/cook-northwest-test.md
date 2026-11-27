# Cook northwest transfer test (counties expansion, 2026-11-25)

**Status:** locked transfer test **PASS** on all five checks (placeholder pass marks), **lower confidence**. Switched on in the app code; backend tests and the live check on the laptop are still to do. Internal, non-commercial use (same SeeClickFix licence note as `dupage-central-test.md`).

## Data
- Towns: Mount Prospect, Des Plaines, Arlington Heights (next to each other, east of the Cook suburbs area). Found by the 2026-11-25 scan of 48 towns.
- 245 SeeClickFix pothole reports after removing repeats from overlapping search boxes (about 235 since 2022; Mount Prospect about 32 a year since 2020).
- Area `ml/forecasting/config/areas/cook_northwest.yaml` (own schema), prepared with `scripts/cook-northwest-prepare.bat`: 12,994 road sections; weather from Palwaukee, O'Hare and Barrington. The optional HPMS layer was not published for Illinois.

## Test
Model `forecast-chicago-0.2` unchanged. Mondays 2022-01-03 to 2026-10-19 (251); 12,525 sections; 635 section-Mondays with a new report in the next 30 days. Report: `ml/forecasting/reports/cook_northwest/transfer-test.md`.

| Measure | Chicago model | Simple rule |
|---|---|---|
| Precision, top 1% of roads | 0.0058 (0.0043 to 0.0076) | 0.0010 (0.0005 to 0.0017) |
| Recall, top 10% | 0.371 | 0.140 |
| PR-AUC | 0.0030 | 0.0009 |
| Winter precision, top 1% | 0.0078 | 0.0009 |
| Brier (lower is better) | 0.0004 | 0.0055 |

Ratios against the simple rule: precision 5.8, PR-AUC 3.3, winter 8.7 (needed 1.15, 1.15, 1.0).

## Limits
- The ratios look large because the simple rule scored very poorly. Only about 0.6 in 100 flagged roads got a report in 30 days.
- The Brier check mostly tests calibration at a tiny base rate; do not lean on it.
- Reports, not inspections. Reporting habits and app use change over time.
- Pass marks are placeholders until PI-20.

## App changes (2026-11-25)
- `backend/app/services/forecasting.py`: `COOK_NORTHWEST` in `TESTED_AREAS`.
- `backend/app/services/road_risk.py`: same "lower confidence" label as Cook suburbs (credits seeclickfix.com).
- `backend/tests/test_forecasting_tested_areas.py`: label check added.

## To try it on the laptop
1. `scripts\backend-tests.bat`, then `scripts\start-live.bat`.
2. Create a project inside Mount Prospect, Des Plaines or Arlington Heights and switch Road risk on: it should show the lower-confidence label crediting seeclickfix.com.
