# 05: Checkpoints and Goals

## Project goals

### Product goals
1. Turn geotagged road photos into a map of **candidate** defects that a human reviews.
2. Produce trustworthy records: preserved AI output, reviewer decisions, and full audit history.
3. Help managers plan inspections with a transparent, configurable **inspection priority**.
4. Export verified results (CSV, GeoJSON, PDF) for partner workflows.
5. Keep every organization's data fully isolated and protected.

### Technical goals
1. One central permission check, used by every protected route.
2. Retries never create duplicate images, jobs, or findings.
3. Original data (AI predictions, GPS, images) is never overwritten.
4. Every phase ships with tests that were actually run.
5. The whole system starts locally with one command (Docker Compose).

### Personal goals (solo developer)
1. Understand every part of the code you ship, not just have it generated.
2. Keep the system simple enough for one person to run and debug.

## Phase checkpoints

A phase passes only when **all** its boxes are ticked **and** the project owner signs off.

### P0: Documentation
- [x] Project flow documented
- [x] Tech stack documented with reasons
- [x] Development model documented
- [x] Phases defined
- [x] Checkpoints and goals defined
- [x] Agent instruction file (`CURRENT_PHASE.md`) created
- [x] Source PDFs stored in `documentation/source-documents/`
- [x] Build order documented (`02-process/build-order.md`)
- [x] Owner has reviewed and approved all documentation (2026-10-13)

### P1: Requirements
- [x] V1 in-scope and out-of-scope lists confirmed (`03-requirements/requirements.md`, 2026-10-14)
- [x] Role permission matrix written and accepted (2026-10-14)
- [x] Every partner input marked CONFIRMED, PLACEHOLDER, or BLOCKED (2026-10-14; none confirmed yet)
- [x] Acceptance criteria rewritten as a testable checklist (`03-requirements/acceptance-checklist.md`)
- [x] Rough timeline estimated (`02-process/timeline.md`)
- [x] Owner sign-off (2026-10-14)

### P2: Design
- [x] Database schema designed, with diagram (approved 2026-10-14)
- [x] Original vs. corrected fields, both status fields, and version column defined
- [x] Unique constraints for idempotency defined
- [x] Audit event types listed (2026-10-14)
- [x] API endpoint list with request/response shapes and a standard error format (approved 2026-10-14)
- [x] Model output contract written (approved 2026-10-14)
- [x] Screen list with loading, empty, error, and success states (2026-10-14)
- [x] Design reviewed and **frozen** (2026-10-14)
- [x] Owner sign-off (2026-10-14)

### P3: Foundation
- [x] `docker compose up` starts the database, queue, API, and worker on the owner's computer; `npm run dev` starts the frontend (owner confirmed 2026-10-14)
- [x] Linting and type checks pass (Ruff, mypy, oxlint, TypeScript) (verified 2026-10-14)
- [x] First migration applies and rolls back cleanly (verified on PostgreSQL 16 + PostGIS 3.4, 2026-10-14)
- [x] Login and logout with session cookies work (tests + browser check, 2026-10-14)
- [x] A removed user loses access immediately (test)
- [x] Invitations expire (test)
- [x] Central permission dependency is in place (`app/core/auth.py` + `app/core/permissions.py`)
- [x] Cross-organization access by changing IDs is blocked (test; organization level. Project-level tests are added in P4)
- [x] No secrets in git; `.env.example` present
- [x] Owner sign-off (2026-10-14, tested on owner's computer)

### P4: Slice 1, Upload
- [x] Project create/list with boundary works; validation errors keep the entered fields (tests + browser walk-through)
- [x] Batch upload shows per-file progress and an actionable failure for each file (tests + browser walk-through)
- [x] Retrying does not duplicate successful uploads (test)
- [x] EXIF GPS and capture time extracted; missing GPS flagged, not invented (test)
- [x] Quality flags shown with reasons
- [x] Images downloadable only through the API with a permission check (test)
- [x] Owner sign-off (2026-10-15, owner moved on to P5)

### P5: Slice 2, Analysis
- [x] Job states visible: queued, processing, completed, failed (Photos tab, refreshes every 3 seconds while running)
- [x] Job state stored in PostgreSQL (the queue only carries the job ID)
- [x] Retrying a failed job does not duplicate findings (test)
- [x] Each candidate links to its image, model version, box, and confidence (AI suggestions tab)
- [x] Job status endpoint enforces permissions (test)
- [ ] Owner sign-off

### P6: Slice 3, Review
- [x] Map and list selection and filters stay in sync (tests + browser walk-through)
- [x] Records with missing GPS still appear in the list, flagged
- [x] Verification requires explicit type and severity (test)
- [x] Original prediction is preserved after an edit (test)
- [x] A concurrent stale save is rejected with a reload prompt (test + browser)
- [x] Review events record user, time, roles, changes, and decision (test)
- [x] Manual sidewalk observations work (test + browser)
- [x] Keyboard navigation works in the review flow (V / R / F shortcuts, all fields reachable with Tab; moving the pin needs a mouse or touch)
- [ ] Owner sign-off

### P7: Slice 4, Priority, inspection, reports
- [x] Only verified findings are scored (test)
- [x] Score breakdown shows inputs, weights, and missing values (test + browser)
- [x] Priority configuration changes are audited (test)
- [x] Inspection plan, complete, resolve (with evidence), and reopen work, with history kept (test + browser)
- [x] Export counts match the filters (test)
- [x] Exports are verified-only by default; unreviewed data is labelled (test)
- [x] Unconfirmed locations are excluded or flagged in geographic exports (test: left out when missing, `location_confirmed` flag otherwise)
- [x] Exports are logged (test: request and every download in the history)
- [ ] Owner sign-off

### P8: ML baseline
- [ ] Data rights confirmed in writing
- [ ] Labeling guide approved by a qualified reviewer
- [ ] Train/validation/test split is geographically and temporally separated
- [ ] Per-class precision and recall reported with sample counts
- [ ] Weak conditions documented
- [ ] Thresholds agreed with the partner **before** tuning
- [ ] Model meets thresholds; integrated under a new model version
- [ ] Owner sign-off

### P9: System testing
- [ ] Every acceptance criterion below is checked and passed
- [ ] Security, failure-path, and accessibility tests run
- [ ] Performance measured at expected volume
- [ ] Usability sessions done; blocking issues fixed
- [ ] Owner sign-off

### P10: Pilot deployment
- [ ] Production secrets kept outside source control
- [ ] HTTPS enabled
- [ ] Backup **and restore** tested
- [ ] Monitoring and alerts working
- [ ] Retention configured
- [ ] Pilot run completed; feedback recorded
- [ ] Owner sign-off

### P11: Handover
- [ ] All handover documents delivered (see `02-process/project-phases.md`)
- [ ] Limitations register published
- [ ] Owner sign-off

## Acceptance criteria (from the specification)

| Area | Condition | Delivered in |
|------|-----------|--------------|
| Organization isolation | No access to another organization's projects, images, findings, jobs, or reports, including by changing IDs | P3, verified in P9 |
| Upload reliability | Each file shows success or an actionable failure; retries don't duplicate images or jobs | P4, P5 |
| Analysis traceability | Each result identifies its source image, model version, and state; failed jobs retry without duplicates | P5 |
| Review integrity | Verification records user, time, type, severity, and decision; originals kept; no silent overwrite | P6 |
| Map behavior | Map and list filters and selection match; missing-GPS records stay accessible and flagged | P6 |
| Priority rules | Only eligible reviewed findings are scored; weights, inputs, and missing context are visible; configuration changes recorded | P7 |
| Reporting | Counts match filters; reports show date, review status, and geographic limitations | P7 |
| Inspection updates | Plan, complete, and reopen; evidence and history stay linked | P7 |
| Model readiness | Per-class results meet pre-agreed thresholds on held-out pilot data | P8 |
| Usability and accessibility | Users complete upload, review, and export; keyboard and list flows work | P9 |
| Operations | Volume measured; monitoring, backup restore, retention, and support ownership verified | P10 |
