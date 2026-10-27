# AI Model Output Contract (P2)

**Status:** Approved by owner and **frozen**, 2026-10-14.
**Source:** spec section 7 "Model output contract", step 3 "AI detects candidate defects", and the confidence/severity rules.

## In plain words

The AI is like an **outside worker** who looks at a photo and hands back a note.
This document fixes **exactly what that note must contain**, so:
- the app knows how to read it,
- we can swap the AI for a better one later **without changing the app**: any AI that writes the same kind of note fits in,
- a broken or confused AI can't put rubbish into the database.

---

## 1. What the app gives the AI

| Item | Meaning |
|------|---------|
| The photo file | Read from private storage |
| `image_id` | Which photo this is |
| `model_version` | Which AI version should run |

The AI is **not** given the location, project, or user. It only looks at pixels.

## 2. What the AI must hand back (one note per photo)

```json
{
  "contract_version": 1,
  "model_version": "stand-in-0.1",
  "image_id": "8d2f…",
  "status": "ok",
  "failure_reason": null,
  "image_width_px": 4032,
  "image_height_px": 3024,
  "candidates": [
    {
      "detection_index": 0,
      "class_key": "pothole",
      "confidence": 0.87,
      "bbox_px": [1210, 1830, 1640, 2120]
    }
  ],
  "processing_ms": 412
}
```

| Field | Meaning | Rules |
|-------|---------|-------|
| `contract_version` | Version of this note format | Currently `1` |
| `model_version` | Exact AI version | Must match what was requested |
| `image_id` | The photo | Must match the photo given |
| `status` | `ok` or `failed` | |
| `failure_reason` | Why it failed, in plain words | Required when `failed` |
| `image_width_px`, `image_height_px` | Photo size the AI saw | Positive whole numbers |
| `candidates` | Possible problems found; may be empty | |
| `detection_index` | 0, 1, 2… position in the list | Unique within the note |
| `class_key` | Problem type | Must be one of the types this model version declares (e.g. `pothole`, `surface_cracking`, `pavement_deterioration`) |
| `confidence` | The AI's score | Between 0 and 1. A score, **not** a real-world probability, and **never** severity |
| `bbox_px` | Box around the problem: `[left, top, right, bottom]` in photo pixels | Inside the photo; left < right, top < bottom |
| `processing_ms` | How long it took | For monitoring |

## 3. What the AI must NOT hand back

From the spec, the AI never reports:
- **severity**: only a qualified reviewer decides that,
- **size, depth, or measurements**,
- **map location**: the app attaches the photo's location itself, as an approximate observation point,
- **repair advice, cost, or compliance**.

If a future AI adds such fields, the app **ignores** them.

## 4. What the app does with the note

1. **Checks the note** against every rule in section 2. If anything is wrong (unknown type, box outside the photo, confidence above 1…), the job is marked **failed** with the reason "invalid model output", and **nothing** from that note is saved. No partial rubbish.
2. For each candidate, creates one **finding** with status `ai_generated`:
   - the AI's type, confidence, box, and model version go into the **"AI original"** columns, which can never be changed later,
   - the location is copied from the photo and marked "approximate".
3. `detection_index` + the job make each finding unique, so a retry can never create duplicates.
4. An empty `candidates` list means "the AI found nothing". The screen says **"no candidates found"**, never "road is fine".

## 5. The model list ("model registry")

Each AI version is declared once in code (`ml/contract/`), with:

| Item | Example |
|------|---------|
| `model_version` | `stand-in-0.1` |
| Declared classes | `pothole`, `surface_cracking`, `pavement_deterioration` |
| Reporting threshold | Lowest confidence it reports (chosen from validation results, never a guess; the stand-in uses none) |
| `is_stand_in` | `true` for the test detector |
| Evaluation report | Link to its accuracy results (real models only) |

A model version is **never edited** once used. A better model gets a **new** version name.

## 6. The test detector ("stand-in")

Until a real model passes its accuracy check (PI-17), the app uses a **stand-in**:
- it follows this contract exactly, so the whole app can be built and tested,
- it gives the **same answer every time for the same photo** (based on the photo's fingerprint), so tests are repeatable,
- it returns 0–2 made-up candidates per photo,
- every finding it creates is labelled **"TEST DETECTOR: not a real detection"** on screen and in exports.

## 7. Changing the AI later, safely

| Change | What happens to existing data |
|--------|-------------------------------|
| New, better model | Gets a new `model_version`. Running it creates **new** jobs and candidates. Old findings, reviews, and history are untouched and still show which model made them. |
| Model adds a new problem type | Declared in the registry and added as a finding type. Existing findings unaffected. |
| Future model adds more detail (e.g. an exact outline/mask instead of a box) | Added as a **new optional field** in contract version 2. Version 1 notes still work. |
| Model withdrawn | Marked inactive in the registry. Its past findings stay, labelled with its version. |
