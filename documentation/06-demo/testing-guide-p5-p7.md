# Testing guide: Phases 5, 6 and 7 together

The owner tests these three phases together on their own computer, with the AI agent guiding step by step.
Everything here was already tested in the cloud workspace (backend 204 tests, frontend 57 tests, browser walk-throughs).
This guide confirms it works on the owner's computer.

## 0. Start everything
1. In the project folder: `docker compose up --build`
   - The first build takes a few minutes longer than before because it adds the PDF libraries.
   - The new tables are added automatically. Existing data is kept.
   - Never use `docker compose down -v`: it deletes the data.
2. In the `frontend` folder: `npm run dev`, then open http://localhost:5173
3. If something fails, copy the error message for the agent. Do not show the `.env` file.

## Optional: ready-made demo data (good for showing the team lead)
`docker compose exec api python -m app.demo_data`
- Type a password (10+ characters) twice; it is used for all demo users.
- Sign in as `admin@demo-city.test`, `manager@…`, `reviewer@…`, `collector@…` or `viewer@…` (all `@demo-city.test`).
- Creates the separate "DEMO City" organization with 3 projects full of example data. It runs only once.

## 1. AI analysis (Phase 5)
- [ ] Open a project and upload a few photos (at least one without GPS).
- [ ] On **Photos**, click **Analyse new photos**. The status goes from "Waiting" to "Analysing" to "Analysed".
- [ ] Click it again: the message says every photo was already sent, and nothing is duplicated.
- [ ] Each analysed photo shows "N AI suggestions" or "No candidates found", plus the TEST DETECTOR label.

## 2. Review (Phase 6)
- [ ] On **Findings**, click a pin on the map: the same finding is selected in the list, and the other way round.
- [ ] Change the filters (status, type, location): the list and the map change together.
- [ ] Open a finding, then click **Open review**.
- [ ] Click **Verify** without choosing anything: you see "Choose a type and a severity".
- [ ] Choose a type and a severity, move the pin, and verify. The next finding opens automatically.
- [ ] Reject one with a reason, and mark one "Needs field check".
- [ ] Type in Notes, then click "Back to findings": you are warned about unsaved changes.
- [ ] Open the same finding in two browser tabs and save in both. The second tab says "changed by someone else" and offers Reload.
- [ ] Click **Add observation**, describe it, pick a point and save. The observation appears as "Awaiting review".
- [ ] Open a finding's details: its history shows who, when, what changed and the reason.

## 3. Priority and inspections (Phase 7)
- [ ] On **Settings**, set the road category to `arterial` and save.
- [ ] On **Priority**, the verified findings are ranked. Open "How this score was calculated": the facility input shows as missing, with its reason.
- [ ] Open **Priority settings**, change the weights so they add up to 100, and save. The settings version goes up by 1.
- [ ] Click **Plan inspection**, choose a person and a date.
- [ ] Open **Inspection** and click **Mark resolved** without a note or photo: you are told to add one.
- [ ] Add a note or photo and mark it resolved, then **Reopen** it with a reason. The old inspection stays under "Earlier inspections".

## 4. Reports (Phase 7)
- [ ] On **Reports**, generate a CSV, a GeoJSON and a PDF. Each shows "Ready" with a record count.
- [ ] Download each one. The PDF and the CSV start with the date, filters, settings and limitations.
- [ ] Tick "include unreviewed AI suggestions": a large warning appears, and that report cannot be shared.
- [ ] Share a verified-only report with viewers.

## 5. Overview and history
- [ ] **Overview** shows the numbers (waiting for review, verified, open inspections, and so on).
- [ ] The project's **History** tab and **History** in the left menu list everything you did. Filter them by person and by action.
- [ ] **Data retention** says automatic deletion is off.

## 6. Other roles (optional)
- [ ] From **Team**, invite a second email and add that person to the project as a field collector, then as a viewer.
- [ ] Sign in as them in another browser and check what they see:
  - A field collector sees their own photos, "My inspections", and verified findings only.
  - A viewer sees verified findings and shared reports only.

## After testing
Tell the agent what passed and what didn't. Then sign off Phases 5, 6 and 7, or ask for fixes.
