# Forecasting F4d: Road Risk Screens (Design)

**Status:** **Approved 2026-10-30** (owner: "ok go ahead", D-F4d-1 to D-F4d-4 as suggested). **Part 1 (backend) complete 2026-10-30**: backend tests 277 passed (section 8). **Part 2 (screens) built and tested 2026-11-02** (frontend 99 passed); owner trial on the laptop next.
**Builds on:** `forecasting-f4-plan.md` (approved; F4-D1 to F4-D5), `forecasting-f4b-design.md` (complete), the F4c API
(`api-spec.md`, F4c notes) and `ui-screens.md`. Levels only (F4-D2): no percentage anywhere.
**Owner requests included (2026-10-30):** the project manager chooses who else can see road risk; a manager can plan an
inspection straight from a risky road.

## In plain words

F4d is the first part of forecasting that people see:

1. A **"Road risk" tab** in each project where forecasting is on: a map of the roads marked high / medium / low, an
   **"Inspect first"** list with the reasons in plain words, the 7-day weather outlook, and a download of the list.
2. **One road's page**: its level, reasons, risk factors, week-by-week history and its inspections.
3. In **Settings → Road risk** (project managers): switch forecasting on or off, see how set-up is going,
   **"Update now"**, and **tick who else can see road risk**.
4. **Plan an inspection from a road**, even when nobody has photographed it yet, using the same inspection steps as today.

Every road-risk screen shows the **TRIAL FORECAST** label and the sentence **"Risk estimate, not a confirmed defect."**
Alerts and the bell come next, in F4e.

## 1. Who can see road risk (owner request)

| Who | Sees road risk | Can change it |
|---|---|---|
| Project manager (and org admin) | Always | Yes: switch on/off, update now, who can see |
| Technical reviewer | Yes by default; the manager can untick | No |
| Viewer | Yes by default; the manager can untick | No |
| Field collector | No by default; the manager can tick | No |

- The defaults are exactly the F4 plan you approved, so nothing changes until a manager changes it.
- Each change is recorded in the project history (`forecast.visibility_changed`).
- **How it works in the code:** `risk.view` is given to every project role in `permissions.py`, with a condition for
  reviewers, viewers and field collectors ("only if the project's setting allows it"), the same way other conditions
  work today (e.g. "own uploads"). The setting is stored per project (`forecast_settings.visible_to_roles`).
- Alerts and the switch stay with project managers (`alert.view`, `risk.configure` unchanged).
- A field collector who is **given an inspection of a road** sees that road (name, map, date) in "My inspections" even
  when road risk is hidden from them. They do not see its level or reasons unless the manager ticks field collectors.

## 2. Inspection of a road section (owner request)

- On a road's page and in the "Inspect first" list, managers get **Plan inspection** (owner and date), as for findings.
- The inspection then works exactly like today: **inspected**, **resolved** with a note or photo, **reopened**; it
  appears in the Priority tab's inspections and in the owner's "My inspections".
- It is linked to the road and to the level that suggested it (`risk_level_id`), so later we can compare what the
  inspectors found with what the forecast said (roadmap §8).
- One open inspection per road at a time (as for findings).

**Database (migration 0010):** nothing is deleted and existing inspections are untouched.

| Change | Why |
|---|---|
| `forecast_settings.visible_to_roles` (list, default `["technical_reviewer", "viewer"]`) | Who else can see road risk |
| `inspections.section_id` (optional, → `forecast_sections`) and `inspections.project_id` (filled for all, existing rows copied from their finding) | A road inspection has no finding |
| `inspections.finding_id` may be empty, with a rule: **exactly one** of finding or road section | The only rule that is relaxed; every existing row still has its finding |

The migration can be undone while no road inspections exist (tested, like 0009).

## 3. Screens

### 3.1 "Road risk" tab

- **Shown** only when forecasting is on for the project **and** the person can see road risk. Projects without
  forecasting keep their six tabs. (This is the one change to the "at most six tabs" rule in `ui-screens.md`: seven
  tabs only where forecasting is on; decision D-F4d-1.)
- **Top bar:** TRIAL FORECAST label, the notice, "Updated Monday 26 October (weather up to 29 October)", the kind:
  - Chicago: "Tested Chicago risk levels: high = the riskiest 1% of Chicago roads this week, medium = the next 9%."
  - Other areas: "Risk factors only: there is no pothole history here, so roads are compared by their weather and
    road facts, not by a tested forecast."
  - Counts: "High 7 · Medium 41 · Low 1,203".
- **Weather strip:** the next 7 days (max/min °C, rain, snow), freeze-thaw days marked with a ❄/☀ icon, the source
  ("National Weather Service, issued 30 Oct 05:00"), and the last 14/30 days (freeze-thaw days, frost days, snow, rain).
- **Map:** the project area with its roads. Levels are shown by **line style and a word, never colour alone**:
  high = thick solid line with a ▲ marker, medium = medium dashed line, low = thin grey line; a legend with the words;
  clicking a road opens its page. Large projects show high and medium first; low appears when zoomed in.
- **"Inspect first" list:** high, then medium (filter: High / Medium / Low / All). Each row: road name and length, level
  badge (word + icon), the top 3 reasons in plain words (e.g. "Pothole reports here, last 12 months: 4"), a
  "some inputs missing" note when needed, and buttons **Open** and (managers) **Plan inspection**. Level 1 rows show
  the risk factors that are high or medium instead of reasons.
- **Download:** CSV and GeoJSON of the list, with the TRIAL label, the notice, run dates and model version in the file;
  downloads are recorded in the history (`forecast.exported`).
- **States:** setting up ("Setting up road risk for this area… this can take up to an hour"), failed (the plain reason
  and, for managers, "Try again"), too large (the size and the 500 km² limit), not ready yet (no Monday run yet).

### 3.2 One road's page

Level and position in the list, the top reasons, all risk factors in two groups ("Risk factors" and "Background
facts"), missing inputs, a small week-by-week history (last 26 weeks, words and markers, no numbers), the inspections
of this road with their outcome, map of the road, and **Plan inspection** (managers).

### 3.3 Settings → Road risk (project managers)

- **Switch:** "Road-risk forecast for this project: On / Off", with what it means, the project size and the 500 km²
  limit; status (setting up / ready / failed / too large / off) and the last updates (daily, weekly).
- **Update now** (when ready): "Weather, risk factors and outlook will be updated in the background (after 06:00
  Chicago time)."
- **Who can see road risk:** project managers (always, greyed out), technical reviewers ☑, viewers ☑,
  field collectors ☐.
- People without `risk.configure` do not see this section.

### 3.4 Small additions

- **Overview tab:** a "Road risk" card (counts and last update, link to the tab) for people who can see it.
- **Priority tab inspections and "My inspections":** road inspections are listed with the road name and a "Road" tag.

## 4. API additions (backend)

| Method | Path | Who | What |
|---|---|---|---|
| PUT | `/projects/{id}/forecast-settings` | `risk.configure` | Also accepts `visible_to_roles` (any of `technical_reviewer`, `viewer`, `field_collector`) |
| GET | `/projects/{id}/forecast-settings` | `risk.view` (as in §1) | Also returns `visible_to_roles` |
| GET | `/projects/{id}/risk/export?format=csv\|geojson` | `risk.view` | The list as a file, labelled; recorded in the history |
| POST | `/projects/{id}/road-sections/{section_id}/inspections` | `inspection.plan` | Plan an inspection of the road (owner, date); links the current level |
| (existing) | `/inspections/{id}`, `/inspections/{id}/evidence`, `/inspections/{id}/reopen`, `/projects/{id}/inspections` | as today | Also work for road inspections |

## 5. Tests

- **Backend:** visibility per role and per project setting (including a field collector ticked in, a viewer ticked
  out, and the generated per-role refusal test); road inspections plan → inspected → resolved → reopened; one open
  per road; a field collector owner sees the road but not its level; migration 0010 up / down / up; export labels.
  All 270 existing backend tests must still pass.
- **Frontend (Vitest, as for the other screens):** the tab appears only when on and allowed; labels and notice on every
  road-risk view; no "%" anywhere in road-risk screens; settings switch and ticks; plan-inspection dialog from a road.
- **Laptop:** `scripts\backend-tests.bat` and a new `scripts\frontend-tests.bat` (runs the frontend tests, type check
  and lint).

## 6. Decisions for the owner

| # | Question | Suggestion |
|---|---|---|
| D-F4d-1 | Road risk as its own tab (7 tabs only where forecasting is on), or inside the Priority tab | **Own tab**, shown only where forecasting is on |
| D-F4d-2 | Who sees road risk by default | **Managers always; reviewers and viewers ticked; field collectors not ticked** (the approved plan); managers can change it per project |
| D-F4d-3 | Inspections of a road without a photo finding | **Yes** (migration 0010 as in §2) |
| D-F4d-4 | When the screens go to the live demo (Vercel) | **After your check on the laptop**, then you push as usual; the TRIAL label stays until F4f sign-off |

## 7. Time

About one week, in two parts, each tested on the laptop before the next:
- **Part 1, backend:** migration 0010, visibility, road inspections, export (`backend-tests.bat`).
- **Part 2, screens:** tab, road page, settings, overview card, inspection lists (`frontend-tests.bat`), then you try it
  on the laptop with a Chicago test project.

## 8. Results

- **Part 1, backend (2026-10-30):** migration 0010 applied on the owner's laptop (app database backed up first to `_backups/app-db-before-0010-road-risk-screens.dump`); `risk.view` for reviewers, viewers and field collectors now depends on the project setting (`CONDITIONS` "project_setting"); `my_permissions` on the project page leaves out `risk.view` where it is hidden, and the page has `road_risk_enabled`; road inspections (plan from a road, inspected, resolved, reopened; one open per road; linked to that week's level); field collector owners see the road (no level) in "My inspections"; CSV / GeoJSON export labelled and audited; dashboard inspection counts include road inspections. New tests `tests/test_road_risk_f4d.py`; the per-role refusal test covers export and road inspections. **Backend 277 passed.**
- **Part 2, screens (2026-11-02):** Road risk tab (`project-road-risk-page.tsx`: trial label and notice, level meaning, counts, weather strip, map with a worded key and line styles, Inspect-first list with plain reasons / Level 1 factors, missing inputs, Plan inspection, CSV/GeoJSON download); road page (`project-road-section-page.tsx`); Settings -> Road risk (`project-road-risk-settings-page.tsx`: on/off, try again, update now, who can see it); Overview card; tab shown only with `risk.view` and `road_risk_enabled`; inspection dialogs and My inspections handle road inspections. Backend additions: `GET /projects/{id}/road-sections/{id}/inspections` (all for managers and people who can see road risk; own only for owners) and open-inspection counts include road inspections. New `scripts/frontend-tests.bat` (type check, lint, tests). **Backend 277 passed; frontend 99 passed (7 new).**

