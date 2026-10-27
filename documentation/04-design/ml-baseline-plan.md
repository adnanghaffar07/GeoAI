# ML Baseline Plan (P8)

**Status:** P8.0 **approved by the owner on 2026-10-16** ("move to next phase lets start"). Sections 3 and 4 are now **frozen** (change control). Pass marks remain PLACEHOLDER until the partner confirms PI-17. P8.1 in progress. Once approved, sections 3 and 4 are **frozen**: changing them after training starts needs a line in `project-decisions.md` with the reason (change control), so we can never "move the goalposts" after seeing results.
**Source:** `02-process/project-phases.md` (P8), `02-process/checkpoints-and-goals.md` (P8 checklist), `04-design/model-output-contract.md`, `03-requirements/partner-inputs.md` (PI-04, PI-05, PI-07, PI-17).
**Machine-readable copy of the pass scores:** `ml/config/acceptance-thresholds.yaml` (the evaluation script in P8.5 reads it).

## In plain words

We want to swap the TEST DETECTOR for a real AI model. Before we touch any data, we write down:
1. **what the model must look for** (its classes),
2. **how we will mark its homework** (the measurement rules), and
3. **the pass mark** (the thresholds).

Writing these first matters. If we chose the pass mark after seeing results, we could always make a weak model "pass".

The AI stays what it is today: it only **suggests** candidates. People still verify every finding, choose severity, and confirm locations. Nothing in this plan changes that.

---

## 1. Sub-phases

| Step | What | Owner's part | Result |
|------|------|--------------|--------|
| **P8.0** | Ground rules (this document) | Approve classes, rules, pass marks | This plan + thresholds file |
| P8.1 | Get a public dataset; check its licence; dataset card | Accept the licence terms | Data in `ml/data/` (never in git) |
| P8.2 | Clean (remove near-duplicates) and split by country / time; lock the test set | — | Frozen splits + count table |
| P8.3 | Labelling guide; Label Studio; small "real roads" check set | Label or find a reviewer | Guide + check set |
| P8.4 | Training scripts; run on Google Colab GPU | Sign in to Colab and run the notebook | Model files + run log |
| P8.5 | Honest evaluation; robustness breakdown; report | Read the report | Evaluation report + model card |
| P8.6 | Gate decision against section 4 | Decide | Pass / partial pass / fail recorded |
| P8.7 | Put the model into the app (only after a pass) | Rebuild Docker, try it | New model version in the app |
| P8.8 | Documents and sign-off | Sign off | P8 checklist ticked |

## 2. What the model looks for (classes)

The model learns **only the app's three AI road classes** (PI-05 placeholder). Sidewalks stay **manual** (project rule: no automated sidewalk classification without a suitable dataset and validation).

The first dataset we plan to use is **RDD2022** (Road Damage Dataset 2022: 47,420 photos from Japan, India, Czech Republic, Norway, United States and China, with boxes for 4 damage types). **The United States part (about 6,000 Google Street View photos) is never used** (section 6), leaving about 41,400 photos. Its labels map to our classes like this:

| App class (`class_key`) | Trained from RDD2022 label | Meaning used for this model |
|-------------------------|----------------------------|-----------------------------|
| `pothole` | D40 Pothole | A bowl-shaped hole in the road surface |
| `surface_cracking` | D00 Longitudinal crack + D10 Transverse crack | Single line cracks, along or across the road |
| `pavement_deterioration` | D20 Alligator crack | Connected "crocodile skin" cracking over an area |

Notes:
- **`pavement_deterioration` is narrower for this model** than the word suggests. The model learns alligator cracking only, not ravelling, rutting or patch failure. The model card and the app's model description will say so.
- The dataset card (P8.1) keeps the original RDD2022 codes, so the mapping can be changed later without re-labelling.
- RDD2022's own test labels were never published. We therefore build our own test set from its labelled training images (P8.2).
- If another dataset is used (licence or quality reasons), this table is updated with a decision-log line **before** training.

## 3. How we mark the model (measurement rules)

These are the rules the evaluation script (P8.5) follows. They match the common road-damage benchmark (CRDDC 2022), so our numbers are comparable with published work.

1. **What counts as a correct find:** the model's box has the **same class** as a real box and overlaps it by **at least 50%** (IoU ≥ 0.5). Each real box can be "found" only once.
2. **Recall** ("how much does it find?") = correct finds ÷ all real problems in the photos.
   **Precision** ("how often is it right?") = correct finds ÷ everything it flagged.
   Both are reported **per class**, always **with the number of examples** they were measured on.
3. **The confidence cut-off** (the lowest score the model reports, the registry's `reporting_threshold`) is chosen **on the validation set only**, never on the test set. It is the cut-off that gives the best F1 score (a balance of recall and precision). If several cut-offs tie, we pick the lower one, so the model finds more.
4. **The test set is used once**, after the model and the cut-off are fixed. Re-running the test after changing anything means the test is "spent". We then report it as such and must build a fresh test set.
5. **Test images come from places the model never trained on.** **Decided 2026-10-16: the Czech Republic** (2,829 labelled photos; 1,387 surface cracking, 161 pavement deterioration and 197 pothole boxes, all above rule 6's minimum of 100). Recorded in the decision log before training. Everything else is training and validation. No near-duplicate photo may appear in both. (The US subset was the first idea but is excluded for licence reasons, section 6.)
6. **Too few examples means "not enough evidence", not "pass".** A class with fewer than **100 real boxes** in the test set cannot pass.
7. **Robustness is reported, not hidden.** Recall is also shown separately for dark photos, blurry photos (using the app's own quality checks), and by country and camera where known. A group that is more than **0.15** below the overall recall is listed as a **weak condition** in the report and the model card.
8. **Confidence is never severity.** The evaluation reports nothing about severity, size or repair.

## 4. The pass mark (thresholds): PLACEHOLDER

PI-17 says only the partner can set the real pass mark, and it is still **BLOCKED**. To keep working, the owner sets **placeholder** pass marks now, before training. They are labelled PLACEHOLDER everywhere.

| Class | Minimum recall | Minimum precision | Minimum test boxes |
|-------|---------------:|------------------:|-------------------:|
| `pothole` | 0.70 | 0.50 | 100 |
| `surface_cracking` | 0.60 | 0.40 | 100 |
| `pavement_deterioration` | 0.60 | 0.40 | 100 |

Why these numbers:
- **Recall is set higher than precision on purpose.** Every suggestion is checked by a reviewer, so a false alarm costs a few seconds of review. A missed pothole is never seen at all.
- **Potholes get the strictest mark.** They are the most safety-relevant class and the easiest to see.
- These are **realistic, not hopeful**. The best CRDDC 2022 competition entry reached an F1 of about 0.76 over all classes, using a large ensemble of several models. A single Faster R-CNN baseline trained on a free GPU will most likely score lower. Our marks are set near what a baseline can honestly reach, not far above it. If it falls short, that is a valid, honest result (see section 5).

Not part of the pass mark, but reported every time:
- results on the small "real roads" check set from P8.3 (too small to pass or fail, but it shows how well the model transfers to the pilot's roads);
- processing time per photo on a normal computer's processor (CPU). **Placeholder target: 5 seconds or less**, so the worker stays responsive.

## 5. The gate (P8.6): what happens with each result

| Result | What we do |
|--------|-----------|
| **All classes pass** | The model may go into the app (P8.7) under a new version name (for example `frcnn-rdd2022-0.1`). |
| **Some classes pass** | The model goes in **declaring only the classes that passed**. The others are left out of its class list, so it can never suggest them. |
| **No class passes** | The TEST DETECTOR stays. The report and the decision log say why, and what would help (more or better data, partner photos once PI-04 allows it). |

**CR-003 (2026-10-22):** `frcnn-rdd2022-0.1` passed no class, but the owner allowed it to run as a labelled **TRIAL model**, off by default and switchable back with one setting. It never becomes the default without passing a fresh final test. See `project-decisions.md`.

**Placeholder versus partner pass mark.** Passing the **placeholder** mark lets the model into the app, but **only switched on by a setting**. The model is shown in the app as "Baseline model: pass mark not yet confirmed by the partner". It becomes the pilot's default detector only after the partner confirms PI-17 and the model still passes the confirmed mark. Switching back to the TEST DETECTOR is one setting change. Old findings always keep the model version that made them.

## 6. Data and rights rules

- **No partner photos are used for training** until PI-04 is confirmed in writing. Until then, only public data whose licence we have checked is used.
- **RDD2022 licence (checked 2026-10-15):**
  - The official download record (figshare, DOI 10.6084/m9.figshare.21431547) states **CC BY 4.0**: free to use, change and use commercially, with credit to the authors (they ask to be cited).
  - The authors' GitHub page states **CC BY-SA 4.0** for "this dataset" (adds share-alike). We follow the **stricter** reading: credit the authors everywhere (dataset card, model card, the app's model description), **never republish the images**, and share any changed images only under the same licence. Whether trained model weights count as a changed version is legally unsettled; the partner accepts this in writing before the pilot. (Not legal advice; a quick legal check before selling is recommended.)
  - **The United States subset is excluded completely** (not for training, validation or testing). Its photos are Google Street View images, and the Google Maps Platform Terms (section 3.2.3(c)(vii)) forbid using Google Maps content to "train, test, validate or fine-tune" AI models. The dataset authors cannot grant rights Google holds. It comes inside the single official zip file, so it cannot be left out of the download; the P8.1 script skips it while unpacking (it is never written to disk as photos) and deletes the zip afterwards.
  - Faces and licence plates are said to be blurred by the authors; the images stay in the training workspace and are never shown in the app.
- Datasets and model files are **never committed** (`ml/data/`, `ml/models/`, `*.pt`, `*.pth` are in `.gitignore`). The dataset card records the source, version, download date and licence instead.
- Photos uploaded to the app are **never** sent to Colab or any other outside service for training.

## 6a. Long-term approach (owner decision, 2026-10-15)

1. **Now:** train a baseline on RDD2022 (without the US subset) to prove the whole pipeline: data, training, scoring, app integration. Expect it to do worse on the pilot's roads than on its own test set.
2. **Later:** once PI-04 allows, fine-tune that model on the partner's own labelled photos. This usually needs far fewer photos than starting from scratch.
3. Rules kept from day one so step 2 works: the **same labelling definitions** for both datasets (section 2 and the P8.3 guide); a **held-back test set of real pilot photos** that is never trained on; **a new model version name** for every model, with its scores kept (e.g. `frcnn-rdd2022-0.1`, then `frcnn-pilot-0.2`).

## 7. Tools (all free)

| Tool | Use | Licence |
|------|-----|---------|
| PyTorch + torchvision Faster R-CNN (ResNet-50 FPN, starting from COCO-pretrained weights) | The model | BSD-3 |
| Google Colab (free GPU) | Training runs. Scripts save progress so a disconnected session can resume | Free tier |
| Label Studio (Community, runs in Docker on the owner's computer) | Labelling the real-roads check set (P8.3) | Apache-2.0 |
| pycocotools or an equivalent small script | Precision and recall calculation | BSD-2 |

ML code and its packages live in `ml/` with their **own** requirements file. The API server never installs PyTorch until the model is actually integrated (P8.7).

## 8. Owner decisions for P8.0

- [x] Classes and mapping in section 2 approved
- [x] Measurement rules in section 3 approved (test country: Czech Republic or Norway; US subset excluded)
- [x] Placeholder pass marks in section 4 approved
- [x] Gate behaviour in section 5 approved (switched on by a setting until the partner confirms)
- [x] Approach agreed: public-data baseline now, fine-tune on partner photos later (section 6a)
- [x] Licence checked: usable with credit; US subset excluded (section 6)
- [ ] Still open: Colab free or Colab Pro (needed at P8.4)

Approved 2026-10-16. P8.1 outputs: `ml/data_prep/fetch_rdd2022.py`, `ml/notebooks/p8_1_get_rdd2022.ipynb`, `07-ml/dataset-card-rdd2022.md`.
