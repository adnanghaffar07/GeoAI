# Level 1 risk factors: DRAFT cut-offs (Chicago training years)

Drafted 2026-10-30 from Chicago training Mondays (2012-01-02 to 2021-05-31), held-out areas left out. Rule: medium = 75th, high = 95th percentile (dips: 10th and 2nd); freeze, frost and snow on Nov-Apr Mondays.
Each factor is shown as low / medium / high. **No percentage is ever shown for a Level 1 area.**

The last columns show how often a new pothole report followed within 30 days in Chicago at each level. 'Lines up' means the high level was followed by reports more often than the low level.

| Factor | Medium from | High from | Share low / medium / high / missing | Report rate low / medium / high | Lines up |
|---|---|---|---|---|---|
| Freeze-thaw days in the last 14 days | 7.0 days | 10.0 days | 83% / 14% / 3% / 0% | 9.1% / 12.5% / 11.7% | yes |
| Days below freezing in the last 30 days | 10.0 days | 17.0 days | 88% / 9% / 3% / 0% | 8.4% / 16.9% / 22.1% | yes |
| Heavy-rain days (25 mm or more) in the last 30 days | 1.0 days | 2.0 days | 59% / 24% / 17% / 0% | 10.1% / 9.6% / 8.2% | **no** |
| Snow in the last 30 days | 241.0 mm | 664.0 mm | 87% / 10% / 3% / 0% | 8.5% / 16.7% / 20.1% | yes |
| Dip where water collects (height compared with roads within 200 m) | -0.26 m | -0.82 m | 90% / 8% / 2% / 0% | 9.7% / 9.0% / 8.8% | **no** |
| Slope | 0.31 % | 1.03 % | 75% / 20% / 5% / 0% | 9.6% / 9.7% / 9.6% | **no** |
| FEMA flood zone (high = 1% yearly chance, medium = 0.2%) | fixed | fixed | 99% / 0% / 0% / 0% | 9.7% / 2.2% / 8.9% | **no** |
| Traffic (vehicles per day: high = 30,000 or more, medium = 15,000-30,000) | fixed | fixed | 23% / 10% / 1% / 66% | 10.9% / 12.6% / 9.7% | **no** |
| Heavy vehicles (per day: high = 2,500 or more, medium = 1,000-2,500) | fixed | fixed | 33% / 1% / 0% / 66% | 11.5% / 11.2% / 6.5% | **no** |
| Bus routes on the road (high = 2 or more, medium = 1) | fixed | fixed | 77% / 16% / 7% / 0% | 8.8% / 11.8% / 13.5% | yes |

On average 9.6% of section-Mondays in these years were followed by a new report within 30 days.

A factor that does **not** line up in Chicago should be shown with care or left out; Claude and the owner decide.
To approve: the owner says so, the decision is logged, and `status` in `config/risk-factors.yaml` becomes APPROVED.
