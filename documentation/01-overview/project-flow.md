# 01: Project Flow

## 1. What the product is

A web platform that turns geotagged road and sidewalk photos into a map of **suspected** defects.

- AI suggests what it might see in a photo.
- A qualified human reviewer confirms, corrects, or rejects each suggestion.
- Verified findings help municipal and engineering teams plan inspections and export condition records.

It is a **screening and inspection-planning tool**. It does **not** certify accessibility compliance, structural safety, exact defect dimensions, repair specifications, or repair costs.

```
Photo + GPS  ->  AI candidate  ->  Human review  ->  Verified finding  ->  Inspection priority  ->  Export / report
```

## 2. Users and roles

| Role | Main tasks | Access |
|------|-----------|--------|
| Organization admin | Invite staff, manage roles, organization settings | All projects in their organization |
| Project manager | Create projects, set survey area, configure priorities, plan inspections, export reports | Assigned projects |
| Field collector | Upload photos, add notes, confirm location, retry failed uploads | Uploads to assigned projects; own submissions |
| Technical reviewer | Verify, edit, reject, or merge candidate findings; set severity and location | Assigned review queues and finding history |
| Viewer | Explore verified findings and approved reports | Read-only, assigned projects |

Roles exist at **two levels**:
- **Organization membership**: which organization you belong to, and whether you are an org admin.
- **Project assignment**: your role inside a specific project.

Every request is checked on the server against both. This includes image downloads, job status, and exports.

## 3. End-to-end workflow

| Step | User action | System behavior |
|------|-------------|-----------------|
| 1. Create project | Manager draws or uploads the survey boundary, picks finding types, team, and dates | Saves the boundary and configuration; shows an empty project with an upload action |
| 2. Submit photos | Collector selects photos and confirms consent and location | Validates files, extracts EXIF metadata and GPS, flags missing GPS, shows per-file progress, skips exact duplicates |
| 3. Analyze | Manager or collector starts analysis | Creates background jobs; shows queued / processing / completed / failed |
| 4. Generate findings | User opens the results | Stores candidate type, confidence, bounding box, source location, model version |
| 5. Human review | Reviewer inspects photo, overlay, type, location, and context | Saves verified / rejected / needs field check; keeps original AI output and reviewer identity |
| 6. Prioritize | Manager selects verified findings | Calculates a transparent **inspection priority** and shows every contributing input |
| 7. Share and revisit | Manager exports, or returns after field inspection | Creates a dated export snapshot; records inspection notes and resolution evidence |

## 4. Upload and analysis flow

```
File selected
  -> upload (per-file progress)
  -> server validation: file type, size, file hash (exact duplicate check)
  -> metadata extraction: capture time, EXIF GPS, dimensions
  -> quality flags: missing GPS, blur, too dark, unsupported/corrupt file
  -> image stored (private storage) + database record
  -> analysis job: queued -> processing -> completed | failed
  -> zero or more candidate findings
```

Rules:
- Retrying a failed upload never duplicates a successful one, because duplicates are matched by file hash.
- Retrying a failed analysis job never duplicates findings. A unique constraint on `(image_id, model_version)` enforces this.
- PostgreSQL holds the job state. Celery only executes the work.
- "No detection" means the model produced no candidate. It does **not** prove the road is defect-free.
- Blurry or unsupported images get a reason and a replace action.

## 5. Finding lifecycle

A finding has **two separate status fields**.

### Review status
```
ai_generated -> awaiting_review -> verified
                                -> rejected
                                -> needs_field_check -> verified | rejected
```
- **Manual findings**, including all sidewalk observations in V1, start at `awaiting_review`.
- To verify a finding, the reviewer must choose a type and a severity explicitly.
- If the image cannot establish the condition, choose `needs_field_check`.
- Rejected findings are hidden by default but never deleted.

### Inspection status (verified findings only)
```
none -> planned -> inspected -> resolved
```
- `resolved` requires an authorized user plus a note or an evidence photo.
- Reopening a finding keeps its full history.

### Data that is always preserved
- The original AI prediction (class, confidence, box, model version) is never overwritten. Reviewer edits are stored separately.
- Every review decision is saved as a review event: who, when, what changed, and the decision.
- Each finding has a version number. If two people edit the same finding, the second, stale save is rejected with a "reload" prompt.

## 6. Location flow

| Field | Meaning |
|------|---------|
| Original location | From photo EXIF GPS, device GPS, or a manual map click. Never changed. |
| Location source | `photo_gps` / `device_gps` / `manual` |
| Location quality | e.g. `approximate`, `missing`, `reviewer_confirmed` |
| Corrected location | Set by a reviewer who moves the pin. Stored separately. |

Rules:
- Photo GPS is where the **camera** was, so it is only an approximate observation point, not the exact defect point.
- Missing GPS is flagged and the user is asked to pick a point. Coordinates are never invented.
- A finding with a missing or unconfirmed location must be confirmed before it is included in a geographic export.
- Image pixel coordinates (the bounding box) and geographic coordinates (lat/lon) are separate fields.

## 7. How AI and GIS work together

- **AI** answers: "What might be wrong in this photo?"
  - Output contract: class, confidence, bounding box in pixels, model version, linked image, failure reason.
- **GIS** answers: "Where was it observed, which road does it relate to, and what is nearby?"
  - Spatial queries use PostGIS, with geographic distances in meters (`ST_DWithin` on geography).
- **The reviewer** confirms condition and location before the record drives planning.

Additional rules:
- Road association is **suggested**, never silently snapped to the nearest road. Parallel roads and weak GPS cause errors, so the reviewer confirms.
- Possible duplicates are **suggested** using type, road segment, time, distance, and image evidence. GPS proximity alone is not enough, because two adjacent potholes are two findings. Only a reviewer can merge. A merged finding links to multiple images.
- AI confidence is a review aid. It is **never** severity.

## 8. Inspection priority

- Only **verified** findings are scored.
- Inputs (PLACEHOLDER weights until the partner confirms them):
  - reviewed severity,
  - road category,
  - proximity to selected public facilities.
- The UI shows each input, its weight, any missing values, and the resulting score.
- It is always labelled **"inspection priority"**. It ranks attention; it does not decide repairs or compliance.
- Changes to the priority configuration are recorded in the audit log.

## 9. Exports and reports

- Formats: CSV, GeoJSON, and a PDF summary.
- Default content is verified findings only. Optional unreviewed data is labelled prominently.
- Each export records its filters, generation time, user, and geographic limitations. The export counts must match the filters.
- Exports are logged in the audit history.

## 10. System components

```
Browser (React app)
   |  HTTPS, session cookie
   v
FastAPI application API  ---- central permission check on every route
   |            |
   |            +--> Private photo storage (via storage module, served only through API)
   v
PostgreSQL + PostGIS  (source of truth: records, job state, audit events)
   ^
   |
Celery workers (via Valkey queue): quality checks, AI inference, report/export generation
   |
   +--> AI detector (stand-in first, real model once validated)
```

## 11. V1 scope

**In V1:**
- Organization roles and project setup
- Batch JPEG/PNG upload with GPS confirmation and retry
- Quality flags
- AI road screening: pothole, surface cracking, pavement deterioration
- Manual sidewalk observations
- Synchronized map and list
- Review workspace
- Inspection priority
- Inspection tracking
- CSV/GeoJSON/PDF export
- Audit history

**Later:**
- Offline or native app
- Video ingestion
- Automated sidewalk AI
- Temporal comparison
- Route optimization
- Budget and cost estimates
- Work orders
- Asset-system integrations
