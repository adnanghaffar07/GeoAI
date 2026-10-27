# 04: Project Phases

Phases run in order. Phase 8 (ML) is a parallel track. Exit criteria for each phase are in `02-process/checkpoints-and-goals.md`. The step-by-step coding order inside the phases is in `02-process/build-order.md`.

```
P0 Documentation
 -> P1 Requirements
 -> P2 Design
 -> P3 Foundation
 -> P4 Slice 1: Upload
 -> P5 Slice 2: Analysis
 -> P6 Slice 3: Review
 -> P7 Slice 4: Priority, inspection, reports
 -> P9 System testing
 -> P10 Pilot deployment
 -> P11 Handover

P8 ML baseline: starts after P2 (once authorized data exists); joins the main line at its integration gate.
```

No calendar dates yet. A realistic timeline is estimated at the end of P1, once partner inputs and data availability are known.

---

## P0: Project documentation
- **Goal:** a shared, written understanding of the project.
- **Work:**
  - Product flow
  - Tech stack
  - Development model
  - Phases
  - Checkpoints
  - Agent instruction file
- **Deliverables:** the `documentation/` folder.

## P1: Requirements confirmation
- **Goal:** know exactly what V1 must do, and which inputs are confirmed or placeholders.
- **Work:**
  - Confirm V1 scope and out-of-scope items.
  - Write the role permission matrix (who can do what).
  - Record every partner input as CONFIRMED or PLACEHOLDER: pilot partner, survey area, photo source, class definitions, severity rubric, priority weights, road categories, facility layers, road centerline source, location accuracy, retention, face/plate masking, volume, report format.
  - Turn the specification's acceptance criteria into a testable checklist.
- **Deliverables:**
  - `03-requirements/requirements.md`
  - `03-requirements/permission-matrix.md`
  - `03-requirements/partner-inputs.md`
  - `03-requirements/acceptance-checklist.md`

## P2: System design
- **Goal:** design the system before code, then freeze it.
- **Work:**
  - Database schema: tables, relationships, original vs. corrected fields, statuses, constraints, indexes, audit events
  - API endpoint list with request/response shapes and error format
  - Model output contract
  - Screen list and key states (loading, empty, error)
  - Storage layout
  - Job states
- **Deliverables:**
  - `04-design/database-schema.md` (with diagram)
  - `04-design/api-spec.md`
  - `04-design/model-output-contract.md`
  - `04-design/ui-screens.md`

## P3: Foundation
- **Goal:** a running, secure skeleton.
- **Work:**
  - Repository and Docker Compose setup
  - Linters and test runners
  - Configuration and `.env.example`
  - First Alembic migration
  - Users and sessions (login, logout)
  - Organizations and memberships, invitations with expiry
  - Central permission dependency
  - Audit event table
  - Frontend shell: layout, navigation, login
- **Deliverables:** an app where users log in and see only their organization's data, with cross-organization access tests passing.

## P4: Slice 1, Project to upload to stored photo
- **Goal:** managers create projects; collectors upload photos reliably.
- **Work:**
  - Project create/list with boundary drawing or GeoJSON upload, team, and finding types
  - Storage module
  - Batch upload with per-file progress and retry
  - Hash-based duplicate detection
  - EXIF capture time and GPS extraction
  - Missing-GPS flag and manual location selection
  - Quality flags: blur, darkness, unsupported file
  - Protected image download through the API

## P5: Slice 2, Photo to candidate finding
- **Goal:** analysis runs in the background and produces traceable candidates.
- **Work:**
  - Analysis job table and state machine
  - Celery worker
  - Stand-in detector that follows the model output contract
  - Idempotent job creation and retry
  - Candidate findings linked to image, model version, box, and confidence
  - Job status polling in the UI

## P6: Slice 3, Candidate to verified finding
- **Goal:** reviewers verify, reject, or edit candidates with full history.
- **Work:**
  - Map with pins and a list, kept in sync
  - Filters
  - Finding drawer
  - Review workspace: photo, overlay toggle, zoom, editable type, severity, pin, and notes
  - Verify / reject / needs field check
  - Optimistic locking
  - Review events and audit history
  - Manual sidewalk observations
  - Unsaved-changes warning

## P7: Slice 4, Verified finding to report
- **Goal:** managers prioritize, track inspections, and export.
- **Work:**
  - Priority configuration (PLACEHOLDER weights) with a score breakdown and missing-input flags
  - Inspection tracking (planned, inspected, resolved with evidence, reopen)
  - CSV and GeoJSON exports, then PDF
  - Export logging
- **Later in P7, if time allows:**
  - Road-segment association suggestions
  - Duplicate-merge suggestions and reviewer merge

## P8: ML baseline (parallel track)
- **Goal:** a measured, honest baseline model.
- **Work:**
  - Obtain authorized data (or a licensed public dataset for early experiments)
  - Labeling guide with the qualified reviewer
  - Label Studio setup
  - Geographic and time-separated train/validation/test split, with no near-duplicate leakage
  - Fine-tune torchvision Faster R-CNN
  - Per-class precision and recall
  - Robustness breakdown (lighting, blur, device)
  - Evaluation report and limitations
- **Integration gate:** the model meets the per-class thresholds agreed in advance, then replaces the stand-in detector under a new model version.

## P9: System testing and hardening
- **Goal:** prove the acceptance criteria.
- **Work:**
  - Full acceptance checklist
  - Security tests: cross-organization access by changing IDs, removed-user access, downloads, exports
  - Failure paths: missing GPS, failed jobs, conflicting reviews, duplicates
  - Accessibility: keyboard navigation, list alternative to the map
  - Performance at expected volume
  - Usability sessions

## P10: Pilot deployment
- **Goal:** a running pilot on approved hosting.
- **Work:**
  - Production environment and secrets handling
  - HTTPS
  - Backups and a **tested restore**
  - Monitoring: job errors, queue age, API failures, storage use
  - Retention settings
  - Pilot run with real authorized data, then feedback

## P11: Handover
- **Goal:** the project can be run and maintained without guesswork.
- **Deliverables:**
  - Deployment instructions
  - Configuration reference
  - API specification
  - Dataset and model documentation
  - QA results
  - Pilot evaluation
  - Admin guide
  - User walkthrough
  - Limitations register
  - Support procedures
