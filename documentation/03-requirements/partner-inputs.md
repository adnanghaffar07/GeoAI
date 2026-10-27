# Partner Inputs (P1)

**Status:** All inputs are **PLACEHOLDER** as of 2026-10-14. No pilot partner has confirmed anything yet.
**Source:** spec "Inputs needed before kickoff", "Project setup fields", "Validation plan", "Privacy", GIS steps 4–6, and step 7 (priority).

These are decisions **only the pilot partner can make**. We never invent them. Until a partner confirms an input,
the build uses the placeholder shown here. Placeholders are always labelled as placeholders in the app and in exports.

Status values: **CONFIRMED** (partner agreed, with date and source) · **PLACEHOLDER** (safe temporary value; build continues) · **BLOCKED** (no safe placeholder exists; the listed phase cannot finish without it)

---

## 1. Summary

| ID | Input | Status | Needed before |
|----|-------|--------|---------------|
| PI-01 | Pilot partner organization | PLACEHOLDER | P10 pilot |
| PI-02 | Survey area | PLACEHOLDER | P8 data, P10 |
| PI-03 | Photo source and capture devices | PLACEHOLDER | P4 tuning, P8 |
| PI-04 | Image rights: platform use and model training | **BLOCKED** for training | P8 |
| PI-05 | Finding classes and definitions | PLACEHOLDER | P6, P8 labeling |
| PI-06 | Severity rubric | PLACEHOLDER | P6 go-live, P10 |
| PI-07 | Qualified reviewer(s) | **BLOCKED** | P8 labeling, P9 |
| PI-08 | Inspection priority inputs and weights | PLACEHOLDER | P7 go-live |
| PI-09 | Road categories | PLACEHOLDER | P7 |
| PI-10 | Facility layers and distances | PLACEHOLDER | P7 |
| PI-11 | Road centerline source | PLACEHOLDER | P7 road association |
| PI-12 | Location accuracy needs | PLACEHOLDER | P6, P9 |
| PI-13 | Retention rules | PLACEHOLDER | P10 |
| PI-14 | Face and licence-plate masking policy | PLACEHOLDER | Any external sharing; P10 |
| PI-15 | Expected volume and file limits | PLACEHOLDER | P4, P10 hosting |
| PI-16 | Report and export format | PLACEHOLDER | P7 |
| PI-17 | Model acceptance thresholds | **BLOCKED** | P8 training and integration |
| PI-18 | Hosting and data-residency requirements | PLACEHOLDER | P10 |
| PI-19 | Coordinate reference system for exports | PLACEHOLDER | P7 |

---

## 2. Details

### PI-01 Pilot partner organization
- **Affects:** organization record, branding on reports, who signs off gates.
- **Placeholder:** a seeded test organization, "Demo Municipality (TEST DATA)".
- **Confirmed:** —

### PI-02 Survey area
- **Affects:** project boundary, which photos are inside the project area, map start position.
- **Placeholder:** any small public area drawn for development. No real partner geography is assumed.
- **Confirmed:** —

### PI-03 Photo source and capture devices
- **Affects:** upload validation (formats, size), EXIF/GPS availability, blur/darkness thresholds, model robustness.
- **Placeholder:** phone photos, JPEG/PNG, with EXIF GPS when available. Quality thresholds are provisional until tuned on pilot photos (spec: "quality rules are tuned on pilot imagery").
- **Confirmed:** —

### PI-04 Image rights: platform use and model training
- **Affects:** whether partner photos may be stored in the platform, and **separately** whether they may be used to train models.
- **Placeholder (platform use):** only photos the partner explicitly authorizes are uploaded.
- **Training:** **BLOCKED.** Spec: "Never use partner photos for model training without the necessary rights and explicit project authorization." Until this is confirmed in writing, ML work uses only a public dataset whose license has been checked.
- **Confirmed:** —

### PI-05 Finding classes and definitions
- **Affects:** AI classes, manual finding types, filters, labeling guide, exports.
- **Placeholder:**
  - AI road classes (from the spec's proposal): `pothole`, `surface_cracking`, `pavement_deterioration`.
  - Manual sidewalk type: a single `sidewalk_observation` with a required note. No sidewalk sub-types are invented.
- **Still needed:** written definitions, example images, and ambiguous cases, agreed with the qualified reviewer.
- **Confirmed:** —

### PI-06 Severity rubric
- **Affects:** what reviewers choose when verifying, the priority score, reports.
- **Placeholder:** three levels, `low`, `medium`, `high`, with **no engineering definitions**. The review screen shows "Placeholder rubric: not partner-approved". "Needs field check" is always available.
- **Rule:** AI confidence is never used as severity.
- **Confirmed:** —

### PI-07 Qualified reviewer(s)
- **Affects:** who holds the `technical_reviewer` role; labeling guide sign-off; reviewer-agreement measurement.
- **BLOCKED:** a qualified reviewer must be named by the partner. Development testing uses test accounts only, and their decisions are test data.
- **Confirmed:** —

### PI-08 Inspection priority inputs and weights
- **Affects:** the priority score and its breakdown.
- **Placeholder:** inputs are reviewed severity, road category, and proximity to selected facilities (spec). Placeholder weights: severity 0.5, road category 0.3, facility proximity 0.2. Shown in the UI as "Placeholder weights".
- **Rule:** missing inputs are flagged, never assumed.
- **Confirmed:** —

### PI-09 Road categories
- **Affects:** priority input, project setup, filters.
- **Placeholder:** `arterial`, `collector`, `local`, `other`, set manually or mapped from the road layer.
- **Confirmed:** —

### PI-10 Facility layers and distances
- **Affects:** "nearby facilities" context and priority.
- **Placeholder:** schools and hospitals from the development road/facility data, within 200 m. The facility types and radius are configuration, not code.
- **Confirmed:** —

### PI-11 Road centerline source
- **Affects:** suggested road association, road category, duplicate suggestions.
- **Placeholder:** an OpenStreetMap extract for development (ODbL: attribution required, share-alike on derived databases). Source, date, and license are recorded for every imported layer.
- **Confirmed:** —

### PI-12 Location accuracy needs
- **Affects:** how locations are labelled, export rules, location-quality evaluation.
- **Placeholder:** **no accuracy is promised.** All photo-GPS pins are shown as "approximate" until a reviewer confirms or corrects them.
- **Confirmed:** —

### PI-13 Retention rules
- **Affects:** how long photos, findings, and exports are kept; archive and delete behaviour.
- **Placeholder:** keep everything; **automatic deletion is off.** Nothing is deleted until rules are confirmed.
- **Confirmed:** —

### PI-14 Face and licence-plate masking policy
- **Affects:** whether photos can be shared outside the team (reports, viewers outside the partner).
- **Placeholder:** no external sharing of photos. Viewers inside the partner organization only see photos of verified findings (permission matrix Q4). Masking is not built until the policy is defined.
- **Confirmed:** —

### PI-15 Expected volume and file limits
- **Affects:** storage size, processing time, hosting cost, upload limits.
- **Placeholder:** up to 5,000 photos for the pilot; up to 20 MB per file; batches of up to 100 files.
- **Confirmed:** —

### PI-16 Report and export format
- **Affects:** CSV columns, GeoJSON properties, PDF layout.
- **Placeholder:** the "finished record" fields from the spec: finding ID, project, asset link, image reference, prediction and model version, original and corrected location, location quality, reviewed type and severity, reviewer decision, contextual inputs. Every export states its filters, date, review status, and limitations.
- **Confirmed:** —

### PI-17 Model acceptance thresholds
- **Affects:** whether the trained model may replace the stand-in detector.
- **BLOCKED:** per-class precision/recall thresholds must be agreed **before** training or tuning (spec). Until then, only the stand-in detector runs, clearly labelled as such.
- **Confirmed:** —

### PI-18 Hosting and data-residency requirements
- **Affects:** where the pilot runs, backups, cost.
- **Placeholder:** development runs locally only. No partner data is placed on any hosted service until requirements are confirmed.
- **Confirmed:** —

### PI-19 Coordinate reference system for exports
- **Affects:** GeoJSON and CSV coordinates.
- **Placeholder:** WGS 84 longitude/latitude (EPSG:4326), which is the GeoJSON standard. A partner-specific projected system can be added as an extra CSV export option.
- **Confirmed:** —

---

## 3. How placeholders stay changeable without affecting data

This follows the owner's rule that decisions can change later without touching stored data.

1. **Configurable, not hard-coded.** Finding classes, the severity rubric, priority weights, road categories, facility layers, and radii are stored as configuration in the database. None of them are hard-coded in the code.
2. **Versioned.** Each configuration change creates a new version; old versions are kept. For example, rubric v1 (placeholder) is followed by rubric v2 (partner-approved).
3. **Records point to the version they used.** A review stores the rubric version, and a priority score stores the weights version. Confirming the real rubric later never rewrites old reviews; they still show which rubric they were made under.
4. **Placeholder flag.** Each configuration version has `is_placeholder`. The UI shows a banner while it is true, and exports include it.
5. **Safe by default.** Where no safe placeholder exists (training rights, qualified reviewer, model thresholds), the feature stays off rather than guessing.

---

## 4. Questions to send the partner

1. Which organization and contact will run the pilot, and who signs off results?
2. Which area (map boundary) should the pilot survey cover?
3. How will photos be captured (phones, dashcam, vendor), and roughly how many?
4. Do we have written permission to (a) store your photos in the platform and (b) use them to train the AI model?
5. Which defect types matter, with definitions and example photos?
6. What severity scale do your engineers use, and how is each level defined?
7. Who is the qualified reviewer, and how much time can they give?
8. How should inspection priority weigh severity, road type, and nearby facilities? Which facilities?
9. Which road network data should we use (your GIS layer or OpenStreetMap)?
10. How accurate must locations be for your workflow?
11. How long must photos and records be kept, and when must they be deleted?
12. Must faces and licence plates be masked, and when?
13. What should the reports and exports contain, and in which coordinate system?
14. What minimum per-class accuracy must the AI reach before it is used?
15. Are there hosting, security, or data-residency requirements?
