# Dataset Card: RDD2022 (P8.1)

**Status:** Complete for P8.1, 2026-10-16. Downloaded and counted on Google Colab by the owner with `ml/notebooks/p8_1_get_rdd2022.ipynb`: MD5 matched the official value, 74,995 files unpacked from 6 inner zips, the United States zip skipped unopened.
**Plan:** `04-design/ml-baseline-plan.md`.

## In plain words

RDD2022 is a free, public collection of road photos with boxes drawn around cracks and potholes, made by researchers (University of Tokyo and partners) for a road-damage detection competition in 2022. We use it to train our **first** AI model. We do **not** use its United States photos.

## 1. Source

| Item | Value |
|------|-------|
| Name | RDD2022: The multi-national Road Damage Dataset released through CRDDC'2022 |
| Official record | figshare, DOI [10.6084/m9.figshare.21431547](https://figshare.com/articles/dataset/RDD2022_-_The_multi-national_Road_Damage_Dataset_released_through_CRDDC_2022/21431547) (published 2022-10-29) |
| File | `RDD2022_released_through_CRDDC2022.zip`, 13,264,172,619 bytes, MD5 `b62bd51d2ffcfaa76c60f234f0cc2bb3` (the script refuses any other file) |
| Paper | Arya et al., "RDD2022: A multi-national image dataset for automatic Road Damage Detection", arXiv:2209.08538 |
| Authors' page | github.com/sekilab/RoadDamageDetector |
| Downloaded | 2026-10-16 on Google Colab (temporary disk; not kept). Counts: `ml/reports/inventory.json` |

## 2. Licence and how we follow it

- **Official record: CC BY 4.0** (use, change and use commercially, with credit). **Authors' GitHub page: CC BY-SA 4.0** (adds share-alike). We follow the stricter one.
- **We must:** credit the authors (this card, the model card, the app's model description); not republish the images; share any changed images only under the same licence.
- **Open question:** whether trained model files count as a "changed version" under share-alike is legally unsettled. The partner accepts this in writing before the pilot. Not legal advice.
- **Citation:** Arya, D., Maeda, H., Sekimoto, Y., Omata, H., Ghosh, S. K., Toshniwal, D., et al. (2022). RDD2022: A multi-national image dataset for automatic Road Damage Detection. arXiv:2209.08538. Data: doi:10.6084/m9.figshare.21431547.

## 3. What is inside (from the paper)

| Part | Photos | How taken | Used by us? |
|------|-------:|-----------|-------------|
| Japan | 13,133 | Phone in a car, 600×600 | Yes |
| India | 9,665 | Phone in a car, resized to 720×720 | Yes |
| Czech Republic | 3,538 | Phone in a car, 600×600 | Yes (candidate test country) |
| Norway | 10,201 | High-resolution camera in a special road-survey vehicle; vehicles masked | Yes (candidate test country) |
| China (motorbike) | 2,477 | Camera on a motorbike | Yes |
| China (drone) | 2,401 | Drone looking down | Yes, but flagged: a very different viewpoint from phone photos; P8.2 decides whether to keep it |
| **United States** | 6,005 | **Google Street View** | **No. Never unpacked, trained or tested on.** It arrives inside the single official zip, is skipped while unpacking, and the zip is deleted afterwards (Google Maps Platform Terms 3.2.3(c)(vii)) |
| **Total used** | **about 41,400** | | |

- **Labels:** boxes in Pascal VOC XML files (one per photo). Damage codes: D00 longitudinal crack, D10 transverse crack, D20 alligator crack, D40 pothole. Some files may contain other codes; the inventory counts them and they are **ignored** for training.
- **The official "test" photos have no published labels**, so they cannot be used to score the model. We build our own test set from labelled photos (P8.2).
- **Privacy:** the authors state that clearly visible faces and licence plates were blurred (Norway: vehicles masked). The images stay in the training workspace and are never shown in the app.

## 4. How it maps to the app's types

| App type | RDD2022 code(s) |
|----------|-----------------|
| `pothole` | D40 |
| `surface_cracking` | D00 + D10 |
| `pavement_deterioration` | D20 (alligator cracking only) |

## 5. Counts (measured 2026-10-16)

Photos per country match the paper exactly (train + test). "Test" photos have **no labels** and cannot be used for scoring.

| Country | Labelled photos (train) | Unlabelled (test) | D00 | D10 | D20 | D40 | Other codes (ignored) |
|---------|------------------------:|------------------:|----:|----:|----:|----:|-----------------------|
| Japan | 10,506 | 2,627 | 4,049 | 3,979 | 6,199 | 2,243 | D43 736, D44 3,995, D50 3,553 |
| India | 7,706 | 1,959 | 1,555 | 68 | 2,021 | 3,187 | D01 179, D11 45, D43 57, D44 1,062, D50 28, D0w0 1 |
| Norway | 8,161 | 2,040 | 8,570 | 1,730 | 468 | 461 | — |
| Czech | 2,829 | 709 | 988 | 399 | 161 | 197 | — |
| China_MotorBike | 1,977 | 500 | 2,678 | 1,096 | 641 | 235 | Repair 277 |
| China_Drone | 2,401 | 0 | 1,426 | 1,263 | 293 | 86 | Repair 769, Block crack 3 |
| **Total** | **33,580** | **7,835** | **19,266** | **8,535** | **9,783** | **6,409** | |

**In our three app types** (D00 + D10 = surface cracking, D20 = pavement deterioration, D40 = pothole):

| Country | Surface cracking | Pavement deterioration | Pothole |
|---------|-----------------:|-----------------------:|--------:|
| Japan | 8,028 | 6,199 | 2,243 |
| India | 1,623 | 2,021 | 3,187 |
| Norway | 10,300 | 468 | 461 |
| Czech | 1,387 | 161 | 197 |
| China_MotorBike | 3,774 | 641 | 235 |
| China_Drone | 2,689 | 293 | 86 |

What the numbers tell us:
- **Every class has thousands of examples**, enough for a baseline.
- **Not balanced:** surface cracking (27,801 boxes) far outnumbers potholes (6,409). Potholes come mostly from India and Japan.
- **Other codes** (D43 crosswalk blur, D44 white-line blur, D50 manhole, Repair, etc.) are not road damage in our sense and are ignored. Photos that contain only those count as photos with no damage.
- **Test country:** Czech Republic is the only single country with at least 100 boxes of every class (pavement deterioration 161, pothole 197) **and** phone-in-car photos like a typical pilot. Norway also qualifies but holds a third of all D00 boxes and uses a special survey camera. **Approved by the owner 2026-10-16.**
- **Photos with no damage boxes at all** (useful as "nothing here" examples): Czech 1,757 of 2,829, Norway 5,247 of 8,161, India 3,921 of 7,706, Japan 794, China_Drone 5, China_MotorBike 0. So the Czech test set has about 1,070 photos with damage. All 33,580 label files could be read.
- **Photo sizes:** Czech and most of Japan 600×600, India 720×720, China 512×512, Norway about 3,650×2,040 (large, very wide road-survey photos; P8.2 shrinks them for training).
- **China_Drone** looks straight down from the air, unlike phone photos. **Left out of model 0.1 (owner approved 2026-10-16).**
## 6. Known gaps (honest list)

- No photos from the pilot city; road surfaces, markings, cameras and lighting will differ.
- No sidewalks, patches, ruts, manholes or ravelling.
- Box labels were drawn by different teams per country; label quality and style may differ (checked in P8.2/P8.3).
- Mostly daytime photos; night and rain are rare or missing (reported in P8.5).
- Box sizes say nothing about real-world size or depth; the model never reports measurements.

## 7. The split used for model 0.1 (P8.2, run 2026-10-16 on Colab)

Made by `ml/data_prep/split_rdd2022.py` (split version 1, seed 2026). Fingerprints of each list and annotation file are in `ml/splits/v1/split-manifest.json` (with the three photo lists), which locks the test set; verified 2026-10-16: lists match their fingerprints and no photo is in two sets. The prepared photos and COCO annotations are saved as `My Drive/GeoInfraLens/rdd2022-prepared-v1.zip` (4.42 GB) so later sessions never re-download.

| Set | Photos | Photos with no damage | Pothole | Surface cracking | Pavement deterioration |
|-----|-------:|----------------------:|--------:|-----------------:|-----------------------:|
| Training | 25,513 | 11,150 | 5,508 | 21,301 | 8,420 |
| Validation (10.0%) | 2,837 | 1,229 | 618 | 2,424 | 908 |
| **Test (Czech, locked)** | **2,829** | 1,757 | **197** | **1,387** | **161** |

Checks that passed:
- Training + validation (28,350) + test (2,829) = all 31,179 labelled photos used; box totals match section 5 minus China_Drone exactly (one 1-pixel box dropped).
- No exact duplicate photos; 28 small groups of near-duplicates (59 photos, largest group 3), each kept inside one set; no training photo resembled a test photo.
- Every test class has more than 100 boxes (plan rule 6).
- Ignored codes: D44 5,057, D50 3,581, D43 793, Repair 277, D01 179, D11 45, D0w0 1 (these photos count as "no damage" for our three types).
