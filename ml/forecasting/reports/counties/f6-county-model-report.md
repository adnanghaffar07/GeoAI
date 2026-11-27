# F6: county-trained models against the Chicago model (leave one area out)

Chicago model `forecast-chicago-0.2` as in the app (C). B0 = simple rule. K1 = scorecard trained on the other four counties. K2 = scorecard trained on Chicago plus the other four counties. Each area is scored on the Mondays of its own transfer test, without being in the training data of K1 and K2. **Development evidence only**: those Mondays were already used to test C, and no tested level changes. A new model needs a pass/fail test on Mondays after 2026-11-24.

## dupage_central

| Model | Top-1% precision | Top-10% recall | PR-AUC |
|---|---|---|---|
| C | 0.0159 (0.0126-0.0192) | 0.3353 (0.2957-0.3768) | 0.0059 (0.0053-0.0068) |
| B0 | 0.0084 (0.0060-0.0112) | 0.1559 (0.1257-0.1960) | 0.0029 (0.0027-0.0039) |
| K1 | 0.0127 (0.0102-0.0154) | 0.3892 (0.3472-0.4334) | 0.0056 (0.0049-0.0065) |
| K2 | 0.0162 (0.0128-0.0197) | 0.3432 (0.3041-0.3853) | 0.0060 (0.0054-0.0068) |

## cook_suburbs

| Model | Top-1% precision | Top-10% recall | PR-AUC |
|---|---|---|---|
| C | 0.0191 (0.0127-0.0260) | 0.4438 (0.3723-0.5093) | 0.0201 (0.0185-0.0229) |
| B0 | 0.0090 (0.0055-0.0134) | 0.1612 (0.1253-0.2012) | 0.0112 (0.0108-0.0121) |
| K1 | 0.0220 (0.0154-0.0293) | 0.4246 (0.3631-0.4882) | 0.0145 (0.0125-0.0168) |
| K2 | 0.0183 (0.0121-0.0250) | 0.4285 (0.3674-0.4891) | 0.0163 (0.0147-0.0190) |

## cook_northwest

| Model | Top-1% precision | Top-10% recall | PR-AUC |
|---|---|---|---|
| C | 0.0058 (0.0043-0.0076) | 0.3712 (0.3147-0.4338) | 0.0030 (0.0027-0.0037) |
| B0 | 0.0010 (0.0005-0.0017) | 0.1400 (0.1035-0.1792) | 0.0009 (0.0009-0.0011) |
| K1 | 0.0059 (0.0044-0.0077) | 0.3803 (0.3205-0.4475) | 0.0070 (0.0066-0.0075) |
| K2 | 0.0059 (0.0044-0.0078) | 0.3687 (0.3122-0.4263) | 0.0029 (0.0025-0.0035) |

## naperville

| Model | Top-1% precision | Top-10% recall | PR-AUC |
|---|---|---|---|
| C | 0.0407 (0.0324-0.0497) | 0.5342 (0.4877-0.5770) | 0.0206 (0.0178-0.0236) |
| B0 | 0.0262 (0.0193-0.0336) | 0.1847 (0.1600-0.2087) | 0.0116 (0.0106-0.0152) |
| K1 | 0.0347 (0.0267-0.0429) | 0.4837 (0.4390-0.5262) | 0.0195 (0.0169-0.0225) |
| K2 | 0.0392 (0.0311-0.0481) | 0.5420 (0.4976-0.5835) | 0.0206 (0.0180-0.0237) |

## aurora

| Model | Top-1% precision | Top-10% recall | PR-AUC |
|---|---|---|---|
| C | 0.0304 (0.0258-0.0354) | 0.2765 (0.2505-0.3000) | 0.0117 (0.0106-0.0131) |
| B0 | 0.0179 (0.0143-0.0217) | 0.1650 (0.1437-0.1852) | 0.0053 (0.0048-0.0074) |
| K1 | 0.0211 (0.0180-0.0242) | 0.2565 (0.2283-0.2831) | 0.0080 (0.0071-0.0090) |
| K2 | 0.0326 (0.0275-0.0373) | 0.2651 (0.2391-0.2891) | 0.0113 (0.0103-0.0124) |

## Verdict (rule fixed in advance)

| Model | Areas better than C on precision and PR-AUC | Average precision ratio K / C |
|---|---|---|
| K1 | 1 of 5 | 0.90: not clear |
| K2 | 1 of 5 | 1.01: not clear |

Reading: if neither K1 nor K2 is a clear improvement, the Chicago model stays, and the next gains must come from new inputs or more months of county reports. If one is, the next step is a fresh pass/fail test on Mondays after 2026-11-24 (spring or summer 2027) before it replaces anything. Reports, not potholes; pass marks are placeholders (PI-20).

Raw summaries: f6-county-model-report.json.
