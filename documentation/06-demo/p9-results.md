# P9 Results

**Plan:** `04-design/p9-system-testing-plan.md` (approved 2026-11-03). **Tested version:** `development`, pushed 2026-11-03.
Status: ✅ passed · ⏳ to run / owner · ◐ partly · ❌ failed. Updated as each part finishes.

## P9.1 Acceptance criteria → tests

| AC | Criterion (short) | Test(s) | Status |
|---|---|---|---|
| AC-01, AC-02 | Another organization's IDs reveal nothing (projects, photos, findings, jobs, reports; **now also road risk, alerts, assistant, road inspections**) | `test_organization_access.py`, `test_images.py`, `test_findings*`, `test_reports.py`, **`test_p9_security.py::test_another_organization_sees_nothing`** | ✅ (292 passed 2026-11-03) |
| AC-03 | Every blocked permission is refused, per role | `test_projects.py::test_every_blocked_project_permission_is_refused` (generated from the policy, includes road risk), `test_permissions_policy.py`, **`test_p9_security.py::test_every_route_needs_sign_in`** | ✅ |
| AC-04 – AC-07, AC-51, AC-52 | Removed users, invitations, role-change audit, hashed passwords, password reset, one-time links | `test_auth.py`, `test_invitations.py`, `test_password_reset.py` | ✅ (288 passed 2026-11-03) |
| AC-08 | Photos only through the app after a permission check | `test_images.py` | ✅ |
| AC-09, AC-11 | Drawn/uploaded areas; archived = read-only | `test_projects.py`, `project-form-page.test.tsx` | ✅ |
| AC-10 | Missing name shown next to the field, entries kept | `project-form-page.test.tsx` | ✅ |
| AC-12 | 20 photos with progress | Manual | ⏳ owner (20 photos) |
| AC-13 – AC-17 | Bad files, duplicates/retry, GPS, quality flags, location source | `test_images.py`, `test_photo_metadata.py`, `project-upload-page.test.tsx` | ✅ |
| AC-18 | Upload works on a phone | Manual | ⏳ owner (real phone) |
| AC-19 – AC-23 | Analysis states, results, retry, unreviewed, "no candidates" | `test_analysis*.py`, `project-analysis.test.tsx` | ✅ |
| AC-24 – AC-32 | Map/list sync, filters, review rules, originals kept, history, conflicts, unsaved warning, manual observation | `test_review.py`, `project-findings.test.tsx`, `project-review.test.tsx` | ✅ |
| AC-33 | Review flow by keyboard only | P9.4 | ⏳ P9.4 |
| AC-34 – AC-42 | Priority, inspections, exports, placeholder banner | `test_priority.py`, `test_reports.py`, `project-priority.test.tsx`, `project-reports.test.tsx` | ✅ |
| AC-43, AC-44 | Clear errors with reference; database down = "unavailable" | `test_errors.py`, `test_health.py`, **`test_p9_failures.py`** | ✅ (299 passed 2026-11-03) |
| AC-45 | Loading, empty, error, success state on every screen | P9.4 walk-through | ⏳ P9.4 |
| AC-46 | AI accuracy on pilot photos | Needs partner photos (PI-04, PI-17) | ❌ blocked (partner) |
| AC-47 | Real users complete the main tasks | P9.6 | ⏳ P9.6 |
| AC-48 | Expected volume handled, timings recorded | P9.5 `tests/p9_load.py`, `p9-load-report.md` | ✅ (2026-11-03) |
| AC-49, AC-50 | Backup restore, monitoring | P10 | — (P10) |
| AC-53 – AC-59 | Request access, platform admin, place search, roads, AI-check banner, trial label | `test_organization_requests.py`, `test_cli.py`, `test_geo.py`, `test_trial_model.py`, frontend tests | ✅ |
| AC-60 | AC-53 – AC-59 on the live deployment | Manual on https://geo-ai-liart.vercel.app | ⏳ owner |
| **AC-61** | Road risk is off until a manager switches it on; set-up shows progress; too-large areas refused | `test_road_risk.py`, `test_forecasting_jobs.py`, `project-road-risk.test.tsx` | ✅ |
| **AC-62** | Road risk shows levels and plain reasons, never a percentage or the raw model value; TRIAL label everywhere | `test_road_risk.py`, `test_road_risk_f4d.py` (export), `project-road-risk.test.tsx` | ✅ |
| **AC-63** | The manager chooses who else sees road risk; hidden roles are refused | `test_road_risk_f4d.py` | ✅ |
| **AC-64** | Road inspections: plan, inspected, resolved, reopen; one open per road; owner sees it in My inspections | `test_road_risk_f4d.py`, `project-road-risk.test.tsx` | ✅ |
| **AC-65** | Daily/weekly/monthly jobs run when due and catch up after the laptop was off | `test_forecasting_jobs.py`, `test_forecast_live.py` | ✅ |
| **AC-66** | Alerts: one per event, no repeats, close by themselves, managers only | `test_alerts.py`, `notifications.test.tsx` | ✅ |
| **AC-67** | "Ask about road risk": off by default; answers only from the data, with links; "I don't know"; no percentage; 50 a day; kept in history | `test_assistant.py`, `project-road-risk.test.tsx` | ✅ |
| **AC-68** | The person asked to inspect gets a personal notification that closes when resolved; "Assigned to me" in Priority | `test_assigned_notifications.py`, `project-priority.test.tsx` | ✅ |
| **AC-69** | Every page except Home has Back (one level up) and a breadcrumb | `page-nav.test.tsx`; owner walk-through | ✅ / ⏳ owner |
| **AC-70** | Security headers on every answer; session cookie not readable by scripts; no secrets in the code | **`test_p9_security.py`** | ✅ |

## P9.2 – P9.7

| Part | Status |
|---|---|
| P9.2 Security | Built 2026-11-03: `test_p9_security.py` (route sign-in coverage, cross-organization swap for the new features, headers, cookie, secrets scan) and security headers added to every API answer. ✅ 292 passed 2026-11-03. `npm audit`: 1 high in `undici` (test-only, via jsdom) fixed with `npm audit fix` → 0 vulnerabilities (2026-11-03) |
| P9.3 Failure paths | ✅ 299 passed 2026-11-03. Already covered: DB/queue down, queue down for analysis/reports/set-up, broken detector, failed set-up, bad photos, laptop off (catch-up + data-problem alert). Added `test_p9_failures.py`: report that cannot be built, Update now with worker down, one failing job part, weather and outlook downloads failing, AI model missing or Ollama down. |
| P9.4 Accessibility | ◐ Automatic checks ✅ 113 frontend tests passed 2026-11-03 (`accessibility.test.tsx`, axe-core, WCAG 2.1 A/AA: sign-in, request access, projects, road risk, road-risk settings, My inspections, alerts). ⏳ owner keyboard walk-through below |
| P9.5 Performance | ✅ 2026-11-03: all 19 screens and downloads within target at 10,000 photos / 5,004 findings / 1,000 inspections / 6,003 roads (`p9-load-report.md`). First run found the priority list slow the first time (2.55 s: scores saved one by one); fixed by saving in batches (0.95 s). Slowest: road risk ~1.1-1.3 s, PDF report ~21 s. |
| P9.6 Usability | ⏳ owner / team lead |
| P9.7 Fixes and sign-off | ⏳ |

## P9.4 Keyboard walk-through (owner, about 15 minutes)

Use only the keyboard: **Tab** (next), **Shift+Tab** (back), **Enter** (open/press), **Space** (tick), **Esc** (close a dialog), arrow keys in lists. Tick each line; note any problem.

| # | Check | OK? |
|---|---|---|
| K1 | Sign in: reach email, password, eye button and Sign in; error messages are read next to the fields | |
| K2 | You can always see where the focus is (a visible outline) on every page | |
| K3 | Menu: reach every menu item and the Alerts bell; Back and the breadcrumb work with Enter | |
| K4 | Upload: choose photos, tick the permission box, start the upload, see the progress | |
| K5 | Review: open a finding, use the keyboard shortcuts, choose type and severity, Verify; the next finding opens (AC-33) | |
| K6 | Plan an inspection: the dialog opens, focus goes into it, Esc closes it, focus returns to the button | |
| K7 | Reports: choose filters and request a CSV; download it | |
| K8 | Road risk: move through the list, open a road, plan a road inspection, ask a question | |
| K9 | Every screen shows a loading state, an empty message, an error with Retry, and a success message (AC-45) | |
| K10 | Colour: text is easy to read on every page; levels are shown in words, not only by colour | |
| K11 | Phone: open the app on a phone (or narrow the browser); menus and buttons still work | |
