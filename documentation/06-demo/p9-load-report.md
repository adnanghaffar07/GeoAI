# P9.5 Speed test results

Run 2026-11-03 22:39 on the laptop (Docker), test database. Filling took 0.1 minutes.
Volume (P9-D1, PLACEHOLDER until the partner confirms): 20 projects, 10,000 photos, 5,004 findings, 2,502 verified findings, 1,000 inspections, 6,003 road sections, 10,005 road risk levels.
Each page was asked 5 times (reports 2 times) by a signed-in manager; times are inside the app, without the internet.

| Screen | Usual (median) | Slowest | Target | Result |
|---|---|---|---|---|
| Projects list | 0.04 s | 0.06 s | 2 s | OK |
| Home dashboard | 0.22 s | 0.49 s | 2 s | OK |
| Project page | 0.04 s | 0.04 s | 2 s | OK |
| Photos list | 0.03 s | 0.03 s | 2 s | OK |
| Findings list | 0.03 s | 0.03 s | 2 s | OK |
| Findings list, verified only | 0.03 s | 0.03 s | 2 s | OK |
| Findings map | 0.04 s | 0.05 s | 2 s | OK |
| Review: one finding | 0.02 s | 0.02 s | 2 s | OK |
| Review: finding history | 0.02 s | 0.02 s | 2 s | OK |
| Priority list | 0.29 s | 0.95 s | 2 s | OK |
| Inspections | 0.09 s | 0.21 s | 2 s | OK |
| Road risk list | 1.03 s | 1.11 s | 2 s | OK |
| Road risk map | 1.25 s | 1.34 s | 2 s | OK |
| Road risk: one road | 1.08 s | 1.25 s | 2 s | OK |
| Alerts | 0.02 s | 0.03 s | 2 s | OK |
| Report: CSV | 0.44 s | 0.51 s | 60 s | OK |
| Report: map file (GeoJSON) | 0.29 s | 0.30 s | 60 s | OK |
| Report: PDF | 20.89 s | 20.90 s | 60 s | OK |
| Road risk download (CSV) | 1.90 s | 2.42 s | 60 s | OK |

**All within target.**
