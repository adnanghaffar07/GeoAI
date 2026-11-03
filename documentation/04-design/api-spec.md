# API Specification (P2)

**Status:** Approved by owner and **frozen**, 2026-10-14 (includes CR-001). Changes go through change control.

## In plain words

The **API** is the list of requests the screens can send to the server, like a **menu in a restaurant**.
The screen (the customer) orders from the menu: "upload this photo", "save this review", "give me the findings for this map area".
The server (the kitchen) checks you're allowed to order it, does the work, and sends back the result.

Each request has:
- a **method**: `GET` = read something, `POST` = create or do something, `PATCH` = change something, `DELETE` = remove a link (never real data),
- a **path**: the address, e.g. `/api/v1/projects/{project_id}`,
- a **permission key**: who may use it (from `03-requirements/permission-matrix.md`).

---

## 1. Rules that keep later changes safe

The owner's rule: *changing something later must not affect existing data or features.* The API follows these rules:

| # | Rule | What it means in practice |
|---|------|---------------------------|
| 1 | **Version in the address** | All feature requests start with `/api/v1/`. If a change would ever break existing screens or partner integrations, it goes into `/api/v2/` **alongside** v1. v1 keeps working. |
| 2 | **Add, never remove or rename** | Within v1, new fields and new requests may be **added**. Existing fields are never renamed, removed, or given a new meaning. |
| 3 | **Tolerant readers** | The frontend ignores fields it doesn't know, and shows unknown status values as plain text instead of crashing. New values can be added without breaking old screens. |
| 4 | **Lists are wrapped** | Lists come back as `{"items": [...], "page": ..., "total": ...}`, never a bare list, so extra information can be added later without breaking anything. |
| 5 | **Stable error codes** | Error `code` values (`not_found`, `conflict`…) never change meaning. Screens react to the code, not the message text. |
| 6 | **Settings are versioned** | Changing a rubric or priority weights creates a new version; it never rewrites old records (see `04-design/database-schema.md`). |
| 7 | **Permission keys, not role names** | Each request checks a permission key. Changing which roles have that key (a policy change) needs no API change. |

---

## 2. Conventions for every request

| Topic | Convention |
|-------|-----------|
| Base address | `/api/v1` (health checks stay at `/api/health`) |
| Format | JSON, field names in `snake_case` |
| IDs | Random UUIDs |
| Dates and times | ISO 8601 in UTC, e.g. `2026-10-14T15:30:00Z` |
| Map shapes | GeoJSON, longitude/latitude (EPSG:4326) |
| Sign-in | Session cookie (`httpOnly`, `Secure`, `SameSite=Lax`). Requests that change data must come from our own site (Origin check). |
| Errors | Standard format `{ "error": { "code", "message", "details", "request_id" } }` (see `05-standards/coding-conventions.md`) |
| Not allowed | `404 not_found` if you can't see the project at all; `403 permission_denied` if you can see it but not do the action |
| Paging | `?page=1&page_size=50` (maximum 200). Responses include `page`, `page_size`, `total` |
| Safe retries | Repeating a request never creates duplicates where it matters: photo uploads (file fingerprint), analysis jobs (photo + model version), AI findings (job + position) |
| Editing findings | The request must include the finding's `version`. If someone else saved first: `409 conflict`, so reload |

---

## 3. Requests

### 3.1 Health (built)
| Method | Path | Who | Purpose |
|--------|------|-----|---------|
| GET | `/api/health` | anyone | Is the server running? |
| GET | `/api/health/ready` | anyone | Are the database and queue reachable? |

### 3.2 Sign-in and invitations (P3)
| Method | Path | Permission | Purpose |
|--------|------|-----------|---------|
| POST | `/auth/login` | public | Email + password → sets session cookie. Same error for "unknown email" and "wrong password", so accounts can't be discovered. Rate-limited. |
| POST | `/auth/logout` | signed in | Ends this session |
| GET | `/auth/me` | signed in | Current user, their organizations and roles, their permission keys |
| GET | `/auth/invitations/{token}` | public | Check an invite link: shows the organization name, or "expired" / "already used" |
| POST | `/auth/invitations/{token}/accept` | public | Set name and password, join the organization, sign in |
| GET | `/auth/password-resets/{token}` | public | Check a reset link: valid, expired, or already used (CR-001) |
| POST | `/auth/password-resets/{token}` | public | Set a new password; ends all the person's other sign-ins (CR-001) |

### 3.3 Organization, team, settings (P3–P4)
All paths start with `/organizations/{org_id}`.
| Method | Path | Permission | Purpose |
|--------|------|-----------|---------|
| GET | `` | member | Organization details |
| PATCH | `` | `org.settings.edit` | Change name and settings (audited) |
| GET | `/members` | `org.members.view` | List members and roles |
| PATCH | `/members/{user_id}` | `org.members.change_role` | Change org role (audited; cannot remove the last admin) |
| DELETE | `/members/{user_id}` | `org.members.remove` | Remove from organization; their sessions end immediately (audited) |
| POST | `/members/{user_id}/password-reset` | `org.members.reset_password` | Create a one-time reset link (1 hour); response includes `reset_url`, shown once (audited) (CR-001) |
| GET | `/invitations` | `org.members.invite` | List pending invitations |
| POST | `/invitations` | `org.members.invite` | Invite by email with a role; expires in 7 days. The response includes `invite_url`, shown once with a Copy button (CR-001) |
| DELETE | `/invitations/{invitation_id}` | `org.members.invite` | Cancel an invite |
| GET | `/finding-types` | member | List finding types (with placeholder flag) |
| POST | `/finding-types` | `org.settings.edit` | Add a finding type |
| PATCH | `/finding-types/{id}` | `org.settings.edit` | Change label or hide it. The key never changes |
| GET | `/severity-rubrics` | member | All rubric versions; the current one is marked |
| POST | `/severity-rubrics` | `org.settings.edit` | Save a **new** rubric version (old versions stay) |
| GET | `/audit-events` | `org.audit.view` | Organization history, filterable by date, person, action |

### 3.4 Projects (P4)
| Method | Path | Permission | Purpose |
|--------|------|-----------|---------|
| GET | `/organizations/{org_id}/projects` | member | Projects the user can see (filter: archived). *(CR-002: path was `/projects`)* |
| POST | `/organizations/{org_id}/projects` | `project.create` | *(CR-002: path was `/projects`)* Create a project (name, boundary as GeoJSON, finding types, manager, reviewers, optional fields). The creator becomes project manager |
| GET | `/projects/{project_id}` | `project.view` | Project details, counts, the user's roles on it |
| PATCH | `/projects/{project_id}` | `project.edit` | Change details (not allowed when archived) |
| POST | `/projects/{project_id}/archive` | `project.archive` | Archive (read-only; nothing deleted) |
| GET | `/projects/{project_id}/members` | `project.view` | Team and roles |
| POST | `/projects/{project_id}/members` | `project.members.manage` | Give an organization member a project role |
| DELETE | `/projects/{project_id}/members/{member_id}` | `project.members.manage` | Remove one role from a person (audited) |
| GET | `/projects/{project_id}/eligible-members` | `project.members.manage` | *(CR-002)* Organization members who can be added to the project |
| GET | `/projects/{project_id}/audit-events` | `project.audit.view` | Project history |

### 3.5 Photos (P4)
| Method | Path | Permission | Purpose |
|--------|------|-----------|---------|
| POST | `/projects/{project_id}/images` | `image.upload` | Upload **one** photo (the screen sends a batch as several requests, so each file has its own progress). Returns `201` for a new photo, or `200` with `"duplicate": true` and the existing photo if the same file was already uploaded |
| GET | `/projects/{project_id}/images` | `image.status.view` | List photos with status and quality flags. Collectors see only their own |
| GET | `/images/{image_id}` | `image.status.view` | One photo's details |
| GET | `/images/{image_id}/file` | `image.view` | The original photo file (permission-checked every time) |
| GET | `/images/{image_id}/preview` | `image.view` | A smaller version for screens |
| PATCH | `/images/{image_id}/location` | `image.location.set` | Pick a location for a photo **without** GPS. A photo that already has GPS keeps its original; corrections happen on the finding |
| POST | `/images/{image_id}/withdraw` | `image.withdraw` | Withdraw (collectors: own photo, before analysis) |

### 3.6 AI analysis (P5)
| Method | Path | Permission | Purpose |
|--------|------|-----------|---------|
| POST | `/projects/{project_id}/analysis-jobs` | `analysis.run` | Start analysis for chosen photos (or "all not yet analysed"). Existing jobs for the same photo and model are reused, never duplicated |
| GET | `/projects/{project_id}/analysis-jobs` | `analysis.status.view` | Job list with status counts (the screen checks this every few seconds) |
| GET | `/analysis-jobs/{job_id}` | `analysis.status.view` | One job: status, failure reason |
| POST | `/analysis-jobs/{job_id}/retry` | `analysis.run` | Retry a failed job |

### 3.7 Findings and review (P5–P6)
| Method | Path | Permission | Purpose |
|--------|------|-----------|---------|
| GET | `/projects/{project_id}/findings` | `finding.view_verified` (+ `finding.view_candidates`, `finding.view_rejected` to widen) | List with filters: status, type, severity, date, map area, "has location". Rejected hidden unless asked. Results are limited to what the user's role may see |
| GET | `/projects/{project_id}/findings.geojson` | same | Same list as map data, so the map and list always match |
| GET | `/findings/{finding_id}` | as above | Full detail: photos, AI original, corrections, location source and quality, current status |
| POST | `/projects/{project_id}/findings` | `finding.create_manual` | Add a manual finding (e.g. sidewalk). Starts as "awaiting review" |
| POST | `/findings/{finding_id}/review` | `finding.review` | One request for review actions: `verify` / `reject` / `needs_field_check` / `edit`, with `version` and changed fields (type, severity, corrected location, notes, confirmed road). Verify requires type and severity. Stale `version` → `409` |
| POST | `/findings/{finding_id}/merge` | `finding.merge` | Merge other findings into this one; their photos are linked here; history kept |
| GET | `/findings/{finding_id}/history` | `finding.history.view` | All review events |

### 3.8 Priority and inspections (P7)
| Method | Path | Permission | Purpose |
|--------|------|-----------|---------|
| GET | `/projects/{project_id}/priority-configs` | `priority.view` | Settings versions; the current one is marked, placeholders flagged |
| POST | `/projects/{project_id}/priority-configs` | `priority.configure` | Save a **new** settings version (audited); scores are recalculated as new rows |
| GET | `/projects/{project_id}/priority-list` | `priority.view` | Verified findings ranked by inspection priority, with breakdown and missing inputs |
| POST | `/findings/{finding_id}/inspections` | `inspection.plan` | Plan an inspection (owner, date) |
| GET | `/findings/{finding_id}/inspections` | `priority.view` | Inspection history |
| PATCH | `/inspections/{inspection_id}` | `inspection.record` | Record outcome: inspected, or resolved with a note |
| POST | `/inspections/{inspection_id}/evidence` | `inspection.record` | Upload a resolution photo |
| POST | `/inspections/{inspection_id}/reopen` | `inspection.reopen` | Reopen; a new inspection is created, old one kept |

### 3.9 Reports and exports (P7)
| Method | Path | Permission | Purpose |
|--------|------|-----------|---------|
| POST | `/projects/{project_id}/reports` | `report.generate` | Request CSV / GeoJSON / PDF with filters. Runs in the background |
| GET | `/projects/{project_id}/reports` | `report.view_shared` or `report.view_all` | Reports the user may see (viewers: shared only) |
| GET | `/reports/{report_id}` | same | Status, record count, filters, settings versions used |
| GET | `/reports/{report_id}/file` | same | Download (permission-checked; download is logged) |
| POST | `/reports/{report_id}/share` | `report.share` | Share with viewers |

---

## 4. Example: saving a review

Request:
```json
POST /api/v1/findings/7c1e…/review
{
  "action": "verify",
  "version": 3,
  "type_key": "pothole",
  "severity_key": "medium",
  "corrected_location": { "type": "Point", "coordinates": [-122.4194, 37.7749] },
  "notes": "Edge of lane, near drain."
}
```

Success (`200`): the updated finding, now at `"version": 4`, with `"review_status": "verified"`.

If another reviewer saved first (`409`):
```json
{ "error": { "code": "conflict", "message": "This finding was changed by someone else. Reload to see the latest version.", "details": { "current_version": 4 }, "request_id": "…" } }
```

---

## 5. Things decided in this document

- *(CR-002, 2026-10-14)* Project list and create are organization-scoped (`/organizations/{org_id}/projects`), like the other organization lists; `GET /projects/{project_id}/eligible-members` added; upload errors `413 payload_too_large` and `415 unsupported_media_type` added. Purely additive for any existing client.

- The current health checks stay at `/api/health`; all feature requests use `/api/v1/` (the frontend client will be updated in P3).
- Photos upload one file per request (simpler, per-file progress and retry). This replaces the spec's "request upload, then confirm completion" two-step flow, which is only needed for direct-to-cloud uploads; it can be added later as a new request without changing existing ones.

## Implementation notes (P5, 2026-10-15, additive)

- `POST /projects/{id}/analysis-jobs` body `{"image_ids": [...]}` (optional; empty = every photo not yet analysed). Answers `202` with `{created, reused, jobs}`. A photo that already has a job for the current model reuses it.
- `GET /projects/{id}/analysis-jobs?status=` answers the usual list plus `status_counts`.
- `GET /analysis-jobs/{id}` and `POST /analysis-jobs/{id}/retry` (`202`; `409` unless the job failed).
- `GET /projects/{id}/findings?review_status=&image_id=&include_rejected=` and `GET /findings/{id}`. Collectors and viewers never receive unreviewed AI suggestions.
- `candidate_count` on jobs and on a photo's `analysis` is `null` for people who may not see suggestions.
- Added fields: `ProjectCounts.images_analysed`, `ProjectCounts.findings_to_review`, `Image.analysis`.

## Implementation notes (P6, 2026-10-15, additive)

- Findings endpoints moved to their own module; paths unchanged.
- `GET /projects/{id}/findings` and `GET /projects/{id}/findings.geojson` take the same filters: `review_status` (repeatable), `type_key` (repeatable; matches the reviewer's type, or the AI's if none), `severity_key` (repeatable), `created_from`, `created_to` (dates), `has_location`, `include_rejected`, `image_id`. The map answer is a GeoJSON FeatureCollection plus `truncated` (more than 5,000 located findings).
- `POST /findings/{id}/review` body: `action` (`verify` / `reject` / `needs_field_check` / `edit`), `version`, and only the fields to change: `type_key`, `severity_key`, `corrected_location` (`{latitude, longitude}` or `null` to remove a correction), `notes`, `reason` (kept in the history). Stale `version` → `409` with `details.current_version`. Verify without type and severity → `422`.
- `POST /projects/{id}/findings` (manual observation) body: `type_key`, `notes` (required), optional `location` `{latitude, longitude}`, optional `image_id` (a project photo the person may open). Answers `201`, status `awaiting_review`.
- `GET /findings/{id}/history` answers a list (oldest first) of `{action, actor_name, actor_roles, changes, note, finding_version, created_at}`.
- New: `GET /projects/{id}/review-options` (active finding types with `in_project`, and the current severity scale) and `GET /organizations/{id}/severity-rubrics` (all scale versions, read-only).
- Added finding fields: `type_key`, `severity_key`, `severity_rubric_id`, `severity_rubric_version`, `notes`, `reviewed_by_name`, `reviewed_at`, `created_by_name`, `original_location`, `corrected_location`, `updated_at`. `location` = the point to show (corrected if set, else original).

## Implementation notes (P7, 2026-10-15, additive)

- `GET /projects/{id}/priority-list?inspection_status=&page=&page_size=`: verified findings, highest first; each item `{finding, score, breakdown: {inputs: [{key, label, value, points, weight, contribution, missing, reason}], weight_covered, missing}, inspection}` plus the current `config`.
- `GET|POST /projects/{id}/priority-configs`: body `{weights: {severity, road_category, facility_proximity} (sum 1), severity_points, road_category_points (0-100), facility_types, facility_radius_m, is_placeholder}`. `201` = new version.
- `GET /projects/{id}/inspections?mine=&include_closed=`: open inspections with their findings (collectors: only their own).
- `POST /findings/{id}/inspections` `{owner_user_id, planned_date}`; `GET /findings/{id}/inspections`; `PATCH /inspections/{id}` `{status: inspected|resolved, outcome_note}`; `POST|GET /inspections/{id}/evidence` (JPEG/PNG); `POST /inspections/{id}/reopen` `{reason, owner_user_id, planned_date}` (`201`, new inspection).
- `POST /projects/{id}/reports` `{format: csv|geojson|pdf, filters: {type_key[], severity_key[], created_from, created_to, has_location}, include_unreviewed}` answers `202`; `GET /projects/{id}/reports`, `GET /reports/{id}`, `GET /reports/{id}/file` (logged), `POST /reports/{id}/share` `{shared: true|false}` (`409` for reports with unreviewed data).
- `GET /projects/{id}/audit-events` now also takes `action`, `actor_user_id`, `until`.
- Project counts add `findings_needs_field_check`, `findings_verified`, `verified_location_unconfirmed`, `verified_by_type`, `inspections_open`.

## Implementation notes (Dashboard, 2026-10-15, additive)

- `GET /organizations/{org_id}/dashboard?project_id=&days=` (needs `org.view`): `days` is 7, 30 or 90, or left out for all time (anything else answers `422 validation_failed`); `project_id` narrows to one project (`404` if the person cannot see it).
- Answer: `scope {project_id, days, date_from, date_to}`, `access {photos, photos_own_only, candidates, verified, rejected, priority, own_inspections}` (what the screen may show), `totals`, `review_status`, `verified_by_type`, `verified_by_severity`, `inspection_status`, `activity [{date, photos, suggestions, verified}]` (at most 366 days), `top_priority` (5, unresolved), `map_points` (verified with a location, at most 2000, `map_truncated`), `projects [{id, name, my_roles, photos, waiting_review, verified, rejected, inspections_open}]`, `finding_types`, `severity_levels`.
- Each number counts only what the person may see on each project; numbers they may not see are left out (not zero-filled).

## Implementation notes (2026-10-19 to 2026-10-28, additive)

**Trial model (CR-003):** analysis jobs, image `analysis`, findings and reports gain `is_trial_model` (bool) next to `is_test_detector`; reports gain `includes_trial_model`. `POST /projects/{id}/analysis-jobs` answers `503 service_unavailable` with a plain reason when the trial model file is missing or is not the tested file.

**New photos waiting for the AI (FR-60):** `GET /projects/{id}` `counts.images_waiting_for_ai`; dashboard `totals.photos_waiting_for_ai` and `projects[].photos_waiting_for_ai` (stored photos with no analysis job for the current model version).

**Platform admin and organization requests (CR-004):**
| Method | Path | Who | Answer |
|--------|------|-----|--------|
| GET | `/auth/me` | signed in | `user.is_platform_admin` (bool) added |
| POST | `/organization-requests` | anyone (no sign-in) | `202 {message}`. Body: `organization_name`, `contact_name`, `contact_email`, `phone?`, `city_or_agency`, `note?`, `website` (hidden robot trap: if filled, answers 202 and saves nothing). `409 conflict` if a request for that email is waiting; `429 too_many_requests` after 5 per hour from one address (`cf-connecting-ip` / `x-forwarded-for` first) |
| GET | `/platform/organization-requests?status=pending\|approved\|rejected` | platform admin | `{items: [...], pending_count}`; waiting oldest first, decided newest first |
| POST | `/platform/organization-requests/{id}/approve` | platform admin | Body `{note?}`. `{request, invitation_url, invitation_expires_at}`; creates the organization, its placeholder settings and an `org_admin` invitation. `409` if already decided |
| POST | `/platform/organization-requests/{id}/reject` | platform admin | Body `{reason}` (3–2000 characters). The updated request. `409` if already decided |
| POST | `/platform/organization-requests/{id}/invitation-link` | platform admin | New link for an approved request; older pending links for that email are revoked |

Not platform admin: `403 permission_denied`; not signed in: `401`.

**Survey area from a place (FR-58, FR-59):**
| Method | Path | Who | Answer |
|--------|------|-----|--------|
| POST | `/geo/area-from-place` | signed in | Body `{shape, road_width_m (10–200, default 30), add_to?}` where `shape` is GeoJSON Point / LineString / MultiLineString / Polygon / MultiPolygon (max 20,000 points) and `add_to` an existing area. Answer `{area (Polygon or MultiPolygon), area_square_meters}`. Lines become strips (`ST_Buffer` on geography, round ends), points a 150 m circle, areas keep their outline (`ST_MakeValid`); with `add_to` the result is joined (`ST_Union`). Saves nothing. `422` for bad input or an empty / over-detailed result |

Place search itself runs in the browser against OpenStreetMap Nominatim (`/search`, and `/reverse` for coordinates); it is not part of this API.

## Implementation notes (F4c road risk, 2026-10-30, additive)

Section 3.10 Road risk and alerts (`backend/app/api/road_risk.py`). Owner decision F4-D2: **levels only**. No answer contains a percentage or the raw model value; every risk answer carries `label: "TRIAL FORECAST"` and `notice: "Risk estimate, not a confirmed defect."`.

| Method | Path | Who | Answer |
|--------|------|-----|--------|
| GET | `/projects/{id}/forecast-settings` | `risk.view` | `{enabled, status (off/setting_up/ready/failed/too_large), level (1/2, when ready), level_label, message, area_km2, max_area_km2, last_weekly_run, last_daily_run, can_configure, label, notice}` |
| PUT | `/projects/{id}/forecast-settings` | `risk.configure` | Body `{enabled}`. On: area checked (max 500 km²) and set up in the background; already on and ready or setting up: nothing changes. Off: results kept. Audited (`forecast.enabled`, `forecast.disabled`). `409` on archived projects |
| POST | `/projects/{id}/risk-runs` | `risk.configure` | `202`. "Update now": marks the daily (and Chicago weekly) parts due and wakes the worker; the hourly check runs them anyway if the worker is busy. Daily part runs from 06:00 Chicago time. `409` if not on and ready. Audited (`forecast.update_requested`) |
| GET | `/projects/{id}/risk?level=high\|medium\|low&page&page_size (max 500)` | `risk.view` | `{items, page, page_size, total, status, levels_run, factors_run, counts {high, medium, low}, label, notice}`. Item: `section_id, name, road_type, length_m, position (1 = inspect first), level, rank_in_area (Level 2), reasons [{input, label, value}] (top 3, largest first), missing_inputs (plain labels), factors [{factor, label, value, level, kind}]`. Level 2: weekly B1 levels, rank order. Level 1: ordered by the number of high, then medium risk factors; level = the highest risk-factor level |
| GET | `/projects/{id}/risk/map` | `risk.view` | GeoJSON FeatureCollection of all sections; properties `section_id, name, level, position` |
| GET | `/projects/{id}/road-sections/{section_id}/risk` | `risk.view` | `{section, geometry, history [{as_of, level, rank_in_area}] (weekly, newest first, max 52), inspections [{id, status, planned_date}] (linked by risk_level_id), levels_run, factors_run, label, notice}`. `404` if the section is not in this project |
| GET | `/projects/{id}/weather` | `risk.view` | `{outlook {source, issued_at, fetched_at, days, freeze_thaw_days, frost_days, heavy_rain_days, snow_mm} \| null, recent {as_of, values [factor]} \| null}` (recent = middle value over the project's sections) |
| GET | `/projects/{id}/alerts?include_closed&page&page_size` | `alert.view` | Page of `{id, project_id, project_name, type, title, details, created_at, closed_at, read}`, newest first |
| GET | `/notifications` | signed in | `{items (max 50, open first, newest first), unread_count}` for projects the person manages (project manager role) |
| POST | `/notifications/{alert_id}/read` | `alert.view` on the alert's project | `204`; reading twice is fine. `404` outside the person's projects |

**Added in F4d part 1 (2026-10-30):**
| Method | Path | Who | Answer |
|--------|------|-----|--------|
| PUT | `/projects/{id}/forecast-settings` | `risk.configure` | Body now `{enabled?, visible_to_roles?}` (at least one; roles from `technical_reviewer`, `viewer`, `field_collector`). Visibility can be set before switching on. Audited `forecast.visibility_changed` (before/after) |
| GET | `/projects/{id}/forecast-settings` and all `risk.view` routes | `risk.view` + project setting | Answer has `visible_to_roles`. Reviewers, viewers and field collectors get `403` when the project hides road risk from their role |
| GET | `/projects/{id}` | as before | `my_permissions` leaves out `risk.view` where hidden; new `road_risk_enabled` (bool) |
| GET | `/projects/{id}/risk/export?format=csv\|geojson` | `risk.view` + setting | Labelled file (CSV: `#` lines with TRIAL FORECAST, notice, run dates; GeoJSON: `metadata`). Audited `forecast.exported` |
| POST | `/projects/{id}/road-sections/{section_id}/inspections` | `inspection.plan` | Body `{owner_user_id, planned_date}`. `201` InspectionOut. `404` if the road is not in the project, `409` if it has an open inspection |
| (changed) | InspectionOut | | Adds `project_id`, `section_id`; `finding_id` is `null` for road inspections |
| (changed) | `GET /projects/{id}/inspections` | | Items `{inspection, finding \| null, road \| null}`; `road` = `{section_id, name, road_type, length_m}` (no level) |
| (changed) | `/inspections/{id}`, `/evidence`, `/reopen` | | Work for road inspections too |

Differences from roadmap 7.3 (decided in F4c): risk history is per project (`/projects/{id}/road-sections/{id}/risk`) so permissions follow the project; `weather-summary?days=30` became `/weather` (7-day outlook plus the recent weather inputs); no `horizon` (30 days only).

