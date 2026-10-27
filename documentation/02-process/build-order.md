# 06: Build Order (step-by-step implementation sequence)

This file says **exactly what we build first, second, third...** once coding starts.
`02-process/project-phases.md` says *what each phase delivers*; this file says *in what order we write the code inside those phases*.

Rule: do the steps in order. Do not start a step until the step before it is done and its "Done when" is true.

---

## Why this order (read this first)

A common instinct is "login first, then screens, then database". That order causes rework, because:

- **Login needs the database.** Users and sessions are stored in tables, so the database must exist before login can work.
- **Screens need the API.** A screen built before its API uses fake data, and is usually rewritten when the real API arrives.
- **The API needs the database design.** Endpoints return what the tables hold.

So the correct order is **foundation-up**:

```
Design on paper (P1, P2)  ->  Environment  ->  Database  ->  Login & permissions  ->  App shell screens
  ->  then each feature, one at a time:  Tables -> API -> Tests -> Screen -> Manual check
```

"Screens" appear in two places:
1. **Screen design** (wireframes, list of states) happens in **P2**, on paper, before any code.
2. **Screen code** is written per feature, **after** that feature's API works.

### About OAuth / "Sign in with Google or Microsoft"
- V1 uses **email + password with invitations** and database sessions (see `01-overview/tech-stack.md`). This is free, has no external dependency, and supports "removed users lose access immediately".
- OAuth/SSO (Google, Microsoft) is **deferred**. Municipal partners may later want Microsoft login; it can be added on top of the same `sessions` table without redesign.
- There is **no public sign-up**. The first admin is created with a command-line seed script; everyone else is invited.

---

## Stage 0: Before any code (P1 and P2)

| # | Step | Done when |
|---|------|-----------|
| 0.1 | Requirements, permission matrix, partner inputs, acceptance checklist (P1) | Owner signs off P1 |
| 0.2 | Database schema, API spec, model output contract, screen list and wireframes (P2) | Design frozen, owner signs off P2 |

---

## Stage A: Environment (P3)

| # | Step | Done when |
|---|------|-----------|
| A1 | Git repository, `.gitignore`, folder structure from `01-overview/tech-stack.md` | First commit made; no secrets committed |
| A2 | Docker Compose with PostgreSQL + PostGIS and Valkey | `docker compose up` starts both; PostGIS extension available |
| A3 | Backend skeleton: FastAPI app, settings loaded from `.env`, `/health` endpoint | `/health` returns OK; Ruff, mypy, pytest run clean |
| A4 | Frontend skeleton: Vite + React + TypeScript, Tailwind, shadcn/ui, React Router, TanStack Query | Blank app runs; ESLint and Vitest run clean |
| A5 | Database connection + Alembic, first migration enables PostGIS | Migration applies and rolls back cleanly |

## Stage B: Accounts, login, and permissions (P3)

| # | Step | Done when |
|---|------|-----------|
| B1 | Tables: `organizations`, `users`, `organization_memberships`, `sessions`, `audit_events` | Migration applies; models match the frozen schema |
| B2 | Seed script to create the first organization and admin | Admin can be created from the command line |
| B3 | Login / logout / current-user API: Argon2 password check, session cookie (`httpOnly`, `Secure`, `SameSite=Lax`), Origin check on state-changing requests | Tests: correct login works, wrong password fails, logout ends the session |
| B4 | **Central permission dependency** (organization + role check) | Tests: a user cannot read another organization's data by changing IDs |
| B5 | Invitations with expiry; admin can change roles and remove users; audit events written | Tests: expired invite fails; removed user is blocked on the next request |
| B6 | Screens: login page, app shell (header, navigation, empty pages), protected routes, logout | Logged-out users are redirected to login; manual check passes |
| B7 | Screens: organization users page (invite, change role, remove) | Manual check passes; P3 checkpoints ticked |

## Stage C: Slice 1, Projects and photo upload (P4)

| # | Step | Done when |
|---|------|-----------|
| C1 | Tables: `projects` (with boundary polygon), `project_members` | Migration applies |
| C2 | Projects API: create, list, detail, assign team; permission-checked | Tests: validation errors, cross-organization access blocked |
| C3 | Screens: project list, create project (form + map boundary drawing or GeoJSON upload), project detail | Validation errors keep entered fields; empty state shows upload action |
| C4 | `storage.py` module (save / open / delete on a private folder) | Unit tests pass |
| C5 | Table: `images` (file hash, EXIF time, original location, location source/quality, quality flags) | Unique constraint on file hash per project |
| C6 | Upload API: file type/size validation, hash duplicate check, EXIF + GPS extraction, blur/darkness flags | Tests: duplicate retry does not create a second image; missing GPS is flagged, not invented |
| C7 | Protected image download API | Test: other organization's user gets 403/404 |
| C8 | Screen: batch upload with per-file progress, actionable errors, retry, map pick for missing GPS | Manual check with real photos; P4 checkpoints ticked |

Stage C was built and verified on 2026-10-14:
- [x] C1 tables `projects` (survey area as MultiPolygon, map index), `project_members`, plus `finding_types` and `severity_rubrics` with labelled placeholders (migration 0003; upgrade, downgrade, re-upgrade checked)
- [x] C2 projects API: create, list, details, edit, archive, team (add/remove roles, last project manager protected), project history; permission-checked
- [x] C3 screens: Projects list, Create project (form + draw on map or GeoJSON file), project frame with tabs (Overview, Photos, Upload, Team, Settings), archive
- [x] C4 `app/storage.py` (private folder, no path tricks, safe partial writes)
- [x] C5 table `images` (fingerprint unique per project, original location written once, location source and quality, quality flags)
- [x] C6 upload API: JPEG/PNG only, 20 MB limit, duplicate check, GPS and capture time, blur/darkness/outside-area flags
- [x] C7 protected original and preview downloads (checked on every request)
- [x] C8 upload screen: privacy confirmation, per-file progress, Retry, Already uploaded, GPS indicator, Pick location on map; also Team-page note about project roles (owner request)
- Checks: backend 109 tests, ruff, mypy strict; frontend 28 tests, oxlint, TypeScript, production build; full browser walk-through including phone size.
- Still to do by the owner: test with real phone photos (C8 "manual check").

## Stage D: Slice 2, Analysis jobs and candidate findings (P5)

| # | Step | Done when |
|---|------|-----------|
| D1 | Model output contract in code + **stand-in detector** | Stand-in returns contract-shaped results |
| D2 | Tables: `analysis_jobs`, `findings`, `finding_images` (unique `(image_id, model_version)` on jobs) | Migration applies |
| D3 | Celery worker + analysis task; job state written to PostgreSQL | Job moves queued -> processing -> completed/failed |
| D4 | API: start analysis, job status, list candidates | Tests: retry does not duplicate findings; job status is permission-checked |
| D5 | Screen: start analysis, job status with polling, results list | Manual check; P5 checkpoints ticked |

## Stage E: Slice 3, Review (P6)

| # | Step | Done when |
|---|------|-----------|
| E1 | Tables/fields: `review_events`, corrected location, reviewer type/severity, `version` on findings | Original AI fields remain unchanged by design |
| E2 | Findings list API with filters; review API (verify / reject / needs field check) with optimistic locking | Tests: original preserved; stale save rejected; verify requires type + severity |
| E3 | Screen: map + list kept in sync, filters, finding drawer | Missing-GPS findings still visible in the list, flagged |
| E4 | Screen: review workspace (photo, box overlay toggle, zoom, edit type/severity/pin, notes, unsaved-changes warning) | Keyboard flow works |
| E5 | Manual sidewalk observation (API + form) | Starts at `awaiting_review` |
| E6 | Finding history view (review events + audit) | Manual check; P6 checkpoints ticked |

## Stage F: Slice 4, Priority, inspection, exports (P7)

| # | Step | Done when |
|---|------|-----------|
| F1 | Priority configuration table (PLACEHOLDER weights) + scoring service | Tests: only verified findings scored; missing inputs reported |
| F2 | Screen: priority score breakdown | Inputs, weights, missing values visible |
| F3 | Inspection status API + screen (plan, inspected, resolve with evidence, reopen) | History kept on reopen |
| F4 | CSV and GeoJSON export + export logging | Tests: counts match filters; verified-only by default |
| F5 | PDF report (WeasyPrint) | Report shows date, filters, review status, limitations |
| F6 | Overview dashboard (number cards) | Manual check; P7 checkpoints ticked |
| F7 | *(If time allows)* Road association suggestions, duplicate suggestions + reviewer merge | Suggestions only; reviewer confirms |

## Stage G: ML track (P8, in parallel once data exists)

Data rights -> labeling guide -> Label Studio -> split -> train Faster R-CNN -> evaluate -> swap stand-in for real model under a new model version (only if thresholds are met).

## Stage H: Finish (P9 - P11)

System testing and hardening -> pilot deployment (HTTPS, backups with tested restore, monitoring) -> handover documents.

---

## Per-step working routine

For every step above:
1. Re-read the relevant design doc section.
2. Write or change the migration (if any).
3. Write the API / service code.
4. Write tests and **run them**.
5. Build the screen (if any).
6. Check it manually in the browser.
7. Commit with a clear message.
8. Tick the step here and update `CURRENT_PHASE.md`.

## Progress

Current step: **Stage 0 (P1)** - coding has not started.

Stage A code was written and verified on 2026-10-14 (at the owner's request, during P1):
- [x] A1 folder structure, `.gitignore`, `.gitattributes`, `.editorconfig`, root README. **Owner still runs `git init` and the first commit.**
- [x] A2 `docker-compose.yml` (PostGIS, Valkey, API, worker). **Not yet run on the owner's computer.**
- [x] A3 backend skeleton: settings, standard errors, request IDs, logging, health endpoints, Celery worker; ruff, mypy, pytest (11 tests) pass
- [x] A4 frontend skeleton: routing, API client, error handling, system status page; oxlint, build, vitest (7 tests) pass
- [x] A5 Alembic + PostGIS migration; upgrade, downgrade, re-upgrade verified

Stage B (P3) was built and verified on 2026-10-14:
- [x] B1 tables: organizations, users, organization_memberships, sessions, invitations, password_resets, audit_events (migration 0002; history is append-only by database trigger)
- [x] B2 setup command: `python -m app.cli create-organization`
- [x] B3 sign in / sign out / current user; Argon2 passwords; hashed session tokens; sign-in lockout (5 failures in 15 minutes); Origin check against other websites
- [x] B4 central permission gatekeeper; permission policy in one file (`app/core/permissions.py`)
- [x] B5 invitations (7 days, one use), role changes, removal (sessions end immediately), last-admin protection, admin password reset links (1 hour, one use), audit history
- [x] B6 screens: sign in, accept invitation, set new password, app frame with left menu, sign out
- [x] B7 screens: team page (invite with Copy link, change role, remove with confirmation, reset link, pending invitations), My account
- Checks: backend 61 tests, ruff, mypy strict; frontend 13 tests, oxlint, TypeScript build; full browser walk-through.

Stage D (P5) was built and verified on 2026-10-15:
- [x] D1 AI output contract checker and stand-in test detector (`backend/app/ai/`)
- [x] D2 tables `analysis_jobs`, `findings`, `finding_images` (migration 0004; trigger keeps AI original permanent)
- [x] D3 worker task `analysis.run_job`; job state in PostgreSQL; queued -> processing -> completed/failed
- [x] D4 API: start analysis, list jobs, job status, retry, list findings, one finding; tests for no duplicates and permissions
- [x] D5 screens: Photos tab analysis status with Retry and auto-refresh; AI suggestions tab; overview numbers
- Checks: backend 154 tests, ruff, mypy strict; frontend 38 tests, oxlint, TypeScript; real queue + worker run; browser walk-through on desktop and phone.

Stage E (P6) was built and verified on 2026-10-15:
- [x] E1 `review_events` table (migration 0005; add-only by trigger). Review columns and `version` already existed in `findings` (P5)
- [x] E2 findings filters (status, type, severity, dates, has location) shared by list and `findings.geojson`; review API with version check
- [x] E3 Findings tab: map + list in sync, filters, details panel
- [x] E4 Review screen: zoom, AI box on/off, type, severity, notes, movable pin, keyboard shortcuts, unsaved-changes warning, reload on conflict
- [x] E5 manual observation (API + Add observation dialog), starts `awaiting_review`
- [x] E6 history (review events) in the details panel and review screen
- Checks: backend 173 tests (after the independent code check fixes), ruff, mypy strict; frontend 47 tests, oxlint, TypeScript, build; browser walk-through on desktop and phone.

Stage F (P7) was built and verified on 2026-10-15:
- [x] F1 `priority_configs` (versions, placeholder v1) + `priority_scores` + scoring service (verified only; missing inputs flagged)
- [x] F2 Priority screen with "How this score was calculated" and the settings panel (new version on save)
- [x] F3 `inspections`: plan, inspected, resolved with note or photo, reopen (history kept); collectors see "My inspections"
- [x] F4 CSV and GeoJSON exports in the worker; counts match the filters; verified-only by default; logged
- [x] F5 PDF report (WeasyPrint) with date, filters, review status, settings versions and limitations
- [x] F6 Overview dashboard numbers; History (audit) screens; Data retention page
- [ ] F7 (if time allows) road/facility map layers, road association, duplicate suggestions, merge — not built
- Checks: backend 204 tests, ruff, mypy strict; frontend 57 tests, oxlint, TypeScript, build; real worker run, simultaneous-request check, browser walk-through on desktop and phone; independent code check with fixes.

Next: owner tests P5, P6 and P7 together on their computer (steps in the P7 report), signs them off, then P8 (ML baseline, needs PI-04) / P9 (hardening).
