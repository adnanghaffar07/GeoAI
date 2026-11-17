# GeoInfraLens AI: the whole project on one page

**Written:** 2026-11-17, after reading all 62 documents in the Claude project and walking the code on the laptop (`C:\Users\Developer2025\Desktop\GeoInfraLens AI`, branch `development`, 21 commits). Read this first, then `CURRENT_PHASE.md`.
**Owner:** Farhan (took over from Adnan). **Claude's role:** senior engineer and mentor. Rules are in section 12.

## 1. What it is

A web app that turns road and sidewalk **photos with GPS** into a map of **suspected** defects. An AI suggests, a qualified person confirms, and the confirmed findings help plan inspections. A second part, **road-risk forecasting**, says which road sections are most likely to get a pothole report in the next 30 days.

It is a screening and planning tool. It does **not** certify safety or accessibility, measure exact sizes, or give repair costs. AI confidence is never severity.

```
Photo + GPS -> AI candidate -> Human review -> Verified finding -> Inspection priority -> Reports
Road data + weather + past reports -> Road-risk levels -> Alerts -> Road inspections
```

## 2. Who uses it

| Role | Main job |
|---|---|
| Platform admin | Above all organizations. Approves "Request access". Given only by a server command |
| Organization admin | Invites people, roles, data storage, deletes projects (only role that can) |
| Project manager | Creates projects and survey areas, priority settings, plans inspections, reports, road risk, share links |
| Technical reviewer | Verifies, edits or rejects AI findings |
| Field collector | Uploads photos, records inspections |
| Viewer | Read-only (verified findings and approved reports) |

Roles exist at two levels (organization and project). Every request is checked on the server against both. Rules: `03-requirements/permission-matrix.md` (policy lives in `backend/app/core/permissions.py`). People never see another organization's data (they get "not found").

## 3. The two AI parts

**A. Photo AI (finds defects in photos).**
- Model `frcnn-rdd2022-0.1` (Faster R-CNN trained on the public RDD2022 data, US photos left out). Classes: pothole, surface cracking, pavement deterioration.
- It **failed its final accuracy test** on unseen Czech roads (pothole recall 8%). It is kept as a **TRIAL** (decision CR-003) and is the model set on this laptop's `.env` (`ANALYSIS_MODEL_VERSION=frcnn-rdd2022-0.1`). The made-up "stand-in" detector is the other choice.
- On screens the TRIAL warnings were removed (team lead, TL-D2) and replaced by the sign-in agreement; they stay in exported reports and the About page.
- Real improvement needs 200–300 local photos plus partner permission (PI-04). Acceptance targets are still PLACEHOLDER (PI-17).

**B. Road-risk forecasting (which roads are likely to get potholes).**
- Road sections of about 100 m from OpenStreetMap. Inputs: past 311 pothole reports, weather (NOAA history, NWS 7-day outlook), elevation, flood zones, traffic, bus routes, road condition (HPMS).
- **Level 2, tested levels** (high = top 1% each Monday, medium = next 9%, otherwise low; never percentages): **Chicago** (model B1, `forecast-chicago-0.2`; locked test was PARTIAL, owner chose B1) and **Naperville** (the Chicago model passed all 5 checks of the transfer test on Naperville's own reports).
- **Level 1, risk factors only** (no levels, no percentages): every other US area, for example Boston and Philadelphia (data loaded as Level 1 areas).
- Daily weather refresh, weekly levels (Monday), monthly check, alerts, and "Ask about road risk" (a small free local model, `qwen2.5:0.5b`, only rewords facts the code worked out).
- Everything here carries the "estimate, not a confirmed defect" idea. Details: `04-design/forecasting-*.md`, `07-ml/model-card-forecast-chicago.md`, `ml/forecasting/README.md`.

## 4. What is built (screens and features)

- **Sign-in and joining:** email and password, invitations (one-time links), password reset links, "Request access" with platform-admin approval, **agreement pop-up at every sign-in** (Sign out or I agree).
- **Projects:** survey area by place search, road by name or route number, **Whole road**, **Find all parts of a road by name**, **Road between two points**, drawing areas and roads, GeoJSON upload, per-place Edit and Remove icons, road width 20/30/50 m. Admin-only soft delete.
- **Photos:** batch upload with progress, duplicate check, EXIF and GPS, quality flags, pick-a-location window, withdraw, "N photos waiting for the AI check" banner.
- **AI results and review:** findings map and list, review screen (type, severity, pin, notes, keyboard shortcuts, conflict check), history, manual observations.
- **Photo map** (pins with the photo), **share links** (managers; expire in 1–30 days; revocable; no location shown), **traffic cameras** (IDOT; view, plus Take snapshot as a normal photo; cameras near the area).
- **Priority and inspections:** transparent priority breakdown (settings are PLACEHOLDER), inspection plan/record/resolve/reopen, "Assigned to me".
- **Reports:** CSV, GeoJSON, PDF built in the background; verified findings only by default.
- **Road risk:** tab, map, list with plain reasons, road page (history, details such as speed limit, lanes, surface), Roads-only view, weather in °F, road inspections, alerts and bell, assistant.
- **Other:** dashboards with charts, My account, Data storage page (client's own storage, 4 ways, files encrypted AES-256-GCM), About page (FAQ, Terms, Accessibility, Privacy, Contact us), history (audit) screens, Back and breadcrumb on every page.
- **Removed:** Finding types page, Data retention page (now in the FAQ).

Screen list and addresses: `04-design/ui-screens.md` (sections 4–7). Router: `frontend/src/router.tsx`.

## 5. How it is built

**Stack (all free):** React + Vite + TypeScript + Tailwind, MapLibre and Terra Draw (frontend); FastAPI, SQLAlchemy (sync), Alembic, PostgreSQL 17 + PostGIS, Celery + Valkey (backend). Photo model with PyTorch (CPU). Forecasting with LightGBM, scikit-learn and a separate `forecast` database. Details: `01-overview/tech-stack.md`.

**Docker services (`docker-compose.yml`):** `db`, `queue`, `api`, `worker`, `beat` (hourly forecast tick at minute 5), `ollama` (assistant). The frontend runs outside Docker (`npm run dev`).

**Folders:**

| Folder | What |
|---|---|
| `backend/app/api` | 17 route files (about 80 requests under `/api/v1`) |
| `backend/app/services` | the logic (projects, images, analysis, findings, priority, reports, forecasting, alerts, assistant, cameras, data storage, share links, geo, whole road, road details, roads view, photo map ...) |
| `backend/app/models`, `schemas`, `core` | database tables, request shapes, permissions/auth/security headers/errors |
| `backend/app/workers` | background tasks: analysis, reports, forecasting set-up and tick |
| `backend/app/ai` | stand-in detector, trial model loader, output contract checker |
| `backend/alembic/versions` | migrations **0001–0017** (add-only except 0010) |
| `backend/tests` | 47 test files (332 tests at last run) |
| `frontend/src` | `pages`, `components` (map, road-risk, findings ...), `api`, `lib`, `auth`; 35 test files (126 tests at last run) |
| `ml/` | photo model (data_prep, training, evaluation, notebooks) and `forecasting/` (areas: chicago, naperville, boston, philadelphia; 88 tests) |
| `scripts/` | double-click `.bat` files (below) |
| `documentation/` | all documents |

**Database (33 tables):** accounts (`users`, `sessions`, `organizations`, `organization_memberships`, `invitations`, `password_resets`, `organization_requests`, `user_agreements`, `organization_storage`), work (`projects`, `project_members`, `images`, `image_share_links`, `analysis_jobs`, `findings`, `finding_images`, `review_events`, `finding_types`, `severity_rubrics`, `priority_configs`, `priority_scores`, `inspections`, `reports`), forecasting (`forecast_settings`, `forecast_sections`, `risk_runs`, `risk_levels`, `risk_factor_values`, `weather_outlooks`, `alerts`, `alert_reads`, `forecast_monitoring`), history (`audit_events`). Bulk forecasting data (reports, weather, features) is in a **separate `forecast` database**; the app database is never touched by the forecasting scripts. Originals and history are protected by database triggers; nothing is hard-deleted.

**Rules that hold everywhere:** permission check on every route; no secrets in code; originals never overwritten; history only added to; levels not percentages for forecasts; missing values shown as missing, never guessed.

## 6. Outside services (all free; no e-mail or contact details sent)

Overpass (three servers), Nominatim (place search), OSRM demo router, OpenFreeMap tiles, IDOT Gateway cameras, Naperville open data, Chicago/Boston/Philadelphia open-data portals, Cook County PCI (checking only), NOAA GHCN-Daily, NWS `api.weather.gov`, USGS elevation, FEMA flood zones, USDA soils (dropped by rule), FHWA HPMS. Licences and terms are recorded per source. Details: `01-overview/tech-stack.md` section 10.

## 7. How to run, test and ship (Windows laptop)

| What | How |
|---|---|
| Backend tests (also applies migrations) | `scripts\backend-tests.bat` |
| Frontend tests | `scripts\frontend-tests.bat` |
| Try it locally | `scripts\start-local.bat` then http://localhost:5173 |
| Forecasting tests | `scripts\forecast-tests.bat` |
| Put it live | `scripts\start-live.bat` (Docker + Cloudflare quick tunnel, writes the address into `frontend\vercel.json`), then `git add -A`, `git commit`, `git push origin development` (Farhan pushes himself). Vercel deploys in 1–2 minutes |
| Live demo | https://geo-ai-liart.vercel.app (screens on Vercel, backend on this laptop). Works only while the laptop, Docker and the tunnel are running; the tunnel address changes at every restart |
| Forecast data | `forecast-*.bat` scripts (downloads run on the laptop; the cloud workspace cannot reach the data sites) |

Editing from Claude: back up first, lint backend in the cloud container (ruff), type-check frontend in `/tmp/fe`, copy files back with a **new unique archive name each time**, then check with `cmp`. Vitest and oxlint cannot run in the device VM, so Farhan runs them. The device shell cannot delete files (use `_to_delete/`). Avoid `pyproject.toml` changes (they rebuild Docker).

## 7a. Where it stands (2026-11-17)

- Phases P0–P9 done (P9 closed 2026-11-05 with owner checks carried forward). P5–P7 owner sign-off still open. **Current phase: team-lead improvements** (Naperville first): phases 1, 2 and 4 built and live as a demo; phase 3 (test environment: sample photos with known answers, accuracy report, written test cases) not started.
- Tests at the last run (2026-11-17, with the whole-road work): backend 337, frontend 150, all passing; forecasting 88 (earlier run).
- **Whole road made to always work** was built 2026-11-17 (fast search, Nominatim backup, our own database, Road between two points, Find all parts by name). Automatic tests **passed on Farhan's laptop 2026-11-17** (backend 337, frontend 150). Trying the three tools by hand on a real road is still to do.

## 8. Open work

1. Run the new tests (`backend-tests`, `frontend-tests`), try the three new whole-road tools locally, then go live.
2. **Per-user function control:** Farhan chooses (a) per-person switches on top of roles (1–2 days, with a migration) or (b) a read-only roles screen.
3. Naperville: N4 (pothole and flooding requests on the map), N5 (rain gauges), N6 (demo project; the earlier plan also named `scripts\demo-naperville.bat`, not seen in `scripts\`).
4. Team-lead plan phase 3 (testing environment) and the accuracy report.
5. Legal team section on Contact us (waits for details).
6. Owner checks carried from P9: keyboard walk-through K1–K11, AC-12, AC-18, AC-60, F4 guided check, usability sessions.
7. US-wide forecasting (steps B–E of `forecasting-us-plan.md`) is paused; Boston and Philadelphia exist as Level 1 areas.
8. P10 pilot hosting: a VPS with at least 4 vCPU, 8 GB RAM, 80 GB SSD, Ubuntu 24.04 and Docker (shared hosting cannot run it); domain, backups with a tested restore, monitoring.
9. Partner inputs still open (`03-requirements/partner-inputs.md`): PI-04 training rights, PI-07 qualified reviewer, PI-17 model thresholds (BLOCKED); PI-20 forecast pass marks, PI-21 suburb data, PI-22 engineering check, PI-23 Cook County permission.

## 9. Risks and gaps worth knowing

- **The demo depends on one laptop** and a tunnel whose address changes. Until P10, it is not always on.
- **Free map servers are unreliable** (Overpass timeouts caused the whole-road problem). The new chain reduces this but cannot remove it.
- **Photo AI accuracy is low** on unseen roads; a person must check every result.
- **311 reports are reports, not inspections**: busy areas report more. Forecast labels say so.
- **Placeholders** (priority weights, severity rubric, pass marks) are not partner decisions yet.
- Git history is short (21 commits) and the tunnel address is committed each time.
- **Documents behind the code** (found 2026-11-17, fixed where noted):
  - The laptop `documentation/` had no notes for 2026-11-09 to 11-17 (fixed 2026-11-17: seven main documents updated, this page and `04-design/whole-road-always-works.md` added).
  - `README.md` index and the status words in it were old (fixed in the same pass).
  - `requirements.md` and `acceptance-checklist.md` had no entries for the team-lead features (FR-62 onward and AC-71 onward added; see them for which tests prove what).
  - The Claude project holds older copies of the seven main documents; the laptop copies are newer. The team-lead design notes (`tl-*`, `naperville-plan.md`, `places-whole-road-nearby-cameras.md`, own-storage guides, the handover and the update page) exist only in the Claude project and are not in the laptop's `documentation/` folder.
  - `permission-matrix.md` and `ui-screens.md` still describe parts that the team lead removed (Finding types, Data retention pages; TRIAL banners): later sections say so, but the older sections were not rewritten.
  - The Word manual (v1.0, 2026-10-28) predates all team-lead work.

## 10. Document map

| Need | Read |
|---|---|
| Where are we, what to do next | `CURRENT_PHASE.md`, `project-decisions.md` (newest first) |
| Product flow, stack | `01-overview/project-flow.md`, `tech-stack.md` |
| Phases and order of work | `02-process/` |
| What it must do, who may do what, tests | `03-requirements/` (requirements, permission matrix, partner inputs, acceptance checklist) |
| Database, API, screens, AI contract | `04-design/database-schema.md`, `api-spec.md`, `ui-screens.md`, `model-output-contract.md` |
| Forecasting | `04-design/forecasting-*.md`, `ml/forecasting/README.md`, `07-ml/` |
| Team-lead phase | `04-design/team-lead-improvements-plan.md`, `tl-*.md`, `naperville-plan.md`, `whole-road-always-works.md` |
| Testing | `06-demo/` (P9 results, guides), `04-design/p9-system-testing-plan.md` |
| Coding rules | `05-standards/coding-conventions.md` |

## 11. Decisions that shape everything

Policy in code, facts in the database. Add-only changes after a design freeze (change control, CR-001 to CR-006). Free resources only. Human review before anything counts. Levels, not percentages, for forecasts; tested levels only after a locked test. The client chooses where photos are stored. The agreement is asked at every sign-in. Project delete is admin-only and soft. Existing Chicago, Boston and Philadelphia data are never disturbed.

## 12. Working rules (Farhan)

Simple non-technical English and short replies. End every reply with the 17-row progress table. Inspect before changing; test before claiming. "Just tell" means explain only and change nothing. Use few tokens. Free resources only. Never put his e-mail in anything sent out (User-Agent, requests, files). He pushes to git himself. Don't disturb existing Chicago, Boston and Philadelphia data.
