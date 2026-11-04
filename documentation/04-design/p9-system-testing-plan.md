# P9: System Testing and Hardening (Plan)

**Status:** **Draft 2026-11-03, waiting for the owner's approval.**
**Exit criteria** (`02-process/checkpoints-and-goals.md` P9): every acceptance criterion checked and passed; security,
failure-path and accessibility tests run; performance measured at expected volume; usability sessions done and
blocking issues fixed; owner sign-off. **Tested version:** the commit pushed on 2026-11-03 (`development`).

## Parts (each built, then run on the laptop, like F4)

| Part | What | How | Who |
|---|---|---|---|
| **P9.1** Acceptance checklist | Every criterion in `03-requirements/acceptance-checklist.md` plus the F4/CR-006 additions mapped to a test (existing or new); a table "criterion → test → result" in `06-demo/p9-results.md` | Backend + frontend tests; a few manual checks listed for the owner | Claude, owner |
| **P9.2** Security | Another organization's IDs in every URL (photos, findings, inspections, reports, road risk, alerts, assistant) → 404; each role refused what it may not do (generated from the permission policy, now for every route); sign-in limits, session expiry, sign-out; upload checks (size, type, bad files); no internal details in errors; security headers; no secrets in the repository | New `tests/test_p9_security.py`; a route-coverage test that fails if a new route has no permission test | Claude |
| **P9.3** Failure paths | Database, queue or worker down; NOAA/NWS/Chicago downloads failing or slow; assistant model missing; laptop off for days (catch-up); a report that fails; a photo the AI cannot read | Tests that simulate each failure; each must give a clear message and recover by itself | Claude |
| **P9.4** Accessibility | Automated checks of the main screens (labels, roles, contrast, headings); keyboard-only path through sign-in → upload → review → export and road risk; phone layout | `vitest-axe` checks in the frontend tests (one new dev package); a 15-minute keyboard walk-through by the owner | Claude, owner |
| **P9.5** Performance | Load the app with expected volume (section "Decisions"), measure list, map, review, report and road-risk speed; fix anything slower than the targets | `scripts\p9-load-test.bat` (fills a separate test organization, measures, writes a report) | Claude builds, owner runs |
| **P9.6** Usability | 2-3 people do: upload photos → review → plan an inspection → export; and road risk → plan a road inspection → ask a question. Note where they get stuck | A one-page task sheet and a notes form | Owner / team lead |
| **P9.7** Fixes and sign-off | Fix every blocking issue from P9.1-P9.6; final full test run; sign-off table | | Claude, owner |

Targets: pages and lists answer within **2 seconds** at the expected volume; reports within **1 minute**;
nothing slower than **5 seconds** without a progress message.

## Decisions for the owner

| # | Question | Suggestion |
|---|---|---|
| P9-D1 | Expected volume for the performance test (partner input not confirmed) | **Per organization: 20 projects, 10,000 photos, 5,000 findings, 1,000 inspections, 3 road-risk projects** (a busy year for one city); recorded as a PLACEHOLDER |
| P9-D2 | Add one test-only package for accessibility checks (`vitest-axe`, free, installed by `npm install` on the laptop) | **Yes** |
| P9-D3 | Who joins the usability sessions | **The team lead plus 1-2 colleagues** who have not used the app |

## Time and effort

About 1-1.5 weeks of building and fixing, 1-2 days of owner time, 2-3 weeks on the calendar (mostly the
usability sessions). Kept efficient: one plan approval, part-by-part builds, owner sends only test summaries.
