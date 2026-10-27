# Final test: frcnn-rdd2022-0.1

Tested on 2829 photos from the locked test set (all Czech, never seen in training) on 2026-10-22.

**Result: NOT PASSED**

> The pass marks are PLACEHOLDERS set by the owner. The partner has not confirmed them (PI-17).

| Damage type | Real boxes | Found | False alarms | Recall (need) | Precision (need) | AP50 | Result |
|---|---|---|---|---|---|---|---|
| pothole | 197 | 15 | 40 | 8% (70%) | 27% (50%) | 0.058 | FAIL |
| surface_cracking | 1387 | 236 | 263 | 17% (60%) | 47% (40%) | 0.217 | FAIL |
| pavement_deterioration | 161 | 54 | 188 | 34% (60%) | 22% (40%) | 0.181 | FAIL |

*Recall* = share of real damage the model found. *Precision* = share of the model's suggestions that were real damage. A suggestion counts only with the right type and at least 50% box overlap. Cut-offs were chosen on validation photos.

## Difficult photos (reported only, not part of the pass mark)

| Group | Photos | pothole recall | surface_cracking recall | pavement_deterioration recall |
|---|---|---|---|---|
| Dark | 0 | – of 0 (too few) | – of 0 (too few) | – of 0 (too few) |
| Blurry | 0 | – of 0 (too few) | – of 0 (too few) | – of 0 (too few) |

WEAK = recall more than 15 points below the overall recall for that type (judged only with at least 30 real boxes).

Roads with no damage: 1757 photos, 142 false alarms (0.08 per photo).

## Speed on a CPU

Median 3.6 s per photo (slowest 3.7 s) over 20 photos with 1 CPU threads: within the 5 s target. The app server's CPU may be faster or slower.

## What this does and does not mean

- The model's findings are **candidates** for a person to review; they are never confirmed damage.
- The model's confidence is **not** severity. Nothing here measures size, depth or repair cost.
- The test photos are Czech roads from RDD2022. Results on the client's own roads may differ until the model is checked on their photos (P8.3).
