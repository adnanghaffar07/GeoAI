# Screens (P2)

**Status:** Approved by owner and **frozen**, 2026-10-14. **Amended 2026-10-20** (owner approved: simpler navigation for non-technical users). See section 4.
**Source:** spec section 4 "UI UX screens and behavior", "Visual design", "Accessibility", "Loading and failure states", the suggested dashboard, and the wireframes in section 5.

## In plain words

This is the list of **every page in the app**: what it is for, who can open it, its main button, and what it shows in four situations:
- **Loading**: while waiting for data,
- **Empty**: when there is nothing to show yet,
- **Error**: when something goes wrong,
- **Success**: the normal view.

It is a written plan, not the final look. Visual design is done while building each screen.

---

## 1. Rules for every screen

### Layout
- **Left-side menu** that is always visible on desktop (spec), with the page title at the top and **one main button** per page. The menu has the everyday pages (Home, Projects, My account) and, below them, an **"Organization settings"** group (Team, Finding types, Activity history, Data retention) shown only to people allowed to use it.
- Every page starts with its name and **one plain sentence saying what it is for**.
- Menu items appear only if the user's permissions allow them. The screens read the user's permission keys from `/auth/me`, so a policy change never needs screen changes.
- On phones the menu collapses into a button.
- Inside a project there are **at most six tabs**: Overview, Photos, Findings, Priority (or "My inspections" for field collectors), Reports, Settings.

### Look
- Calm, professional, generous spacing.
- Status and severity colours are always paired with a **word and an icon**, never colour alone.
- **AI suggestions look different from reviewed findings**: for example a dashed outline and the label "AI suggestion" versus a solid marker and "Verified".
- Findings from the test detector show a **"TEST DETECTOR"** badge.
- Settings that are still placeholders show a yellow banner saying they are a **sample, to be replaced by the city's own rules**.
- Everyday words for non-technical users: e.g. "AI certainty" (always with "not how serious the problem is"), "Approximate location (where the photo was taken)", "Needs field check". No internal terms such as version numbers, "candidate" or "weights" on everyday screens.

### The four states (every data screen)
| State | Rule |
|-------|------|
| Loading | Grey placeholder shapes in the layout, never a blank page. Background jobs show progress **without blocking** the rest of the app. |
| Empty | Explains what to do next, with the button to do it (e.g. "No photos yet. Upload photos"). Empty filter results say **"No findings match these filters"** with a **Reset filters** button. |
| Error | Plain-language message, a **Try again** button, and the **reference** ID ("If you contact support, quote this reference"). Retry or replace actions where they make sense. |
| Success | The normal view. Saves that are not obvious on screen show a short notice at the bottom (e.g. "Location saved", "Saved: verified"). |

### Problems and messages
- **No internet**: a strip at the top says changes cannot be saved until the connection is back; a notice says when it is back.
- **Session ended** (expired or signed out elsewhere): the app says so and opens the sign-in page, then returns to the same page.
- **Page crash or app updated**: a full page with a plain message and **Reload page** / **Go to Home** (after an update: "The app has been updated. Reload the page").
- **Browser console** (F12, for developers and support): every message starts with `[GeoInfraLens]`. In development every server call is listed; in the released app only failures, each with its reference ID. Never passwords, link codes or file contents.

### Accessibility
Everything works with a keyboard; focus is always visible; text has readable contrast; every control has a label; photos can be zoomed; **the findings list is always available as an alternative to the map**.

### Phones
Upload works on a phone browser: one column, large buttons, take a photo with the camera or pick files, and clear online/offline feedback.

### Safety
Leaving a page with unsaved changes asks for confirmation. Important changes (removing people, changing settings) ask "Are you sure?" and are recorded.

---

## 2. Screen list

Format for each screen: **Address** · **Who** (permission) · **Main button** · **Shows** · **Special behaviour** · **Requirements**.

### Sign-in pages (no menu)

**S01 Sign in**: `/sign-in`
- Who: anyone
- Main button: **Sign in**
- Shows: email and password
- Special: one message for any wrong email/password combination ("Email or password is incorrect"); "Too many attempts, try again in a few minutes" after repeated failures. Forgotten password: "Ask your administrator for a reset link."
- Requirements: FR-01

**S02 Accept invitation**: `/invite/{token}`
- Who: anyone with the link
- Main button: **Create account**
- Shows: organization name, email (fixed), name, password, confirm password
- Special: expired or used links show a clear message and "Ask your administrator for a new invitation."
- Requirements: FR-02, FR-54

**S03 Set new password**: `/reset-password/{token}`
- Who: anyone with the link
- Main button: **Set password**
- Special: expired or used links explained; after success, "You have been signed out on all other devices."
- Requirements: FR-55

### Main app

**S00 Home**: `/`
- Who: signed in
- Shows: **"What to do next"** first: the jobs this person can act on now, each with one button (e.g. "7 AI suggestions are waiting to be checked → Start reviewing", "3 photos have no location → Add locations", "You have 2 inspections to do → See my inspections", "Upload photos" for field collectors), or "You are all caught up". Below it, **"Numbers and charts"** (the dashboard of every project this person can see) and a one-line system status ("All systems are working", or a plain warning).

**S04 Projects overview**: `/projects`
- Who: signed in; shows only projects the user can see
- Main button: **Create project** (only with `project.create`)
- Shows: project cards with name, status, photos uploaded, waiting for review, verified
- Empty: "No projects yet. Create your first project" (or, without permission: "You haven't been added to a project yet. Ask your project manager.")
- Requirements: FR-07

**S05 New / edit project**: `/projects/new`, `/projects/{id}/settings` (project details; the old address `/projects/{id}/edit` still opens it)
- Who: `project.create` / `project.edit`
- Main button: **Save project**
- Shows: short form (name, finding types, manager, reviewers, optional dates, road category, partner reference) and a **map to draw the survey area**, or upload a GeoJSON file
- Special: errors shown next to each field; **entries are kept if saving fails**; archived projects open read-only
- Requirements: FR-07, FR-08, FR-10

**S06 Project dashboard**: `/projects/{id}`
- Who: `project.view`
- Main button: **Upload photos** (with `image.upload`)
- Shows: **"What to do next"** for this project (as on Home), then the spec's suggested dashboard: photos uploaded, analysis progress, findings waiting for review, verified findings, **records needing location confirmation**, verified findings by type, and a small coverage map
- Special: **no "% surveyed"** figure (spec: not meaningful without a planned route)
- Empty: "No photos in this project yet" with **Upload the first photos**

**S07 Upload photos**: `/projects/{id}/upload` (opened from the **Upload photos** button on Overview and Photos; the Photos tab stays highlighted)
- Who: `image.upload`
- Main button: **Upload**
- Shows: drop zone (desktop) or "Take photo / Choose photos" (phone); a privacy confirmation checkbox ("I am allowed to upload these photos"); a file queue with per-file progress and a **GPS indicator** (has location / no location)
- Special: each file shows done or a plain reason with **Retry** or **Replace**; **successful files are not uploaded again**; photos without GPS get a "Pick location on map" action; duplicates say "Already uploaded"
- Requirements: FR-11 to FR-17, FR-54

**S08 Photos and analysis**: `/projects/{id}/photos`
- Who: `image.status.view` (collectors see their own)
- Main button: **Upload photos**; **Start analysis** (with `analysis.run`)
- Shows: photo list with quality flags, location source, and analysis status (waiting / processing / done / failed, refreshed every few seconds)
- Special: failed jobs show the reason and **Retry**; "No candidates found" (never "road is fine")
- Requirements: FR-19 to FR-24

**S09 Map and findings**: `/projects/{id}/findings`
- Who: `finding.view_verified` (wider views for reviewers and managers)
- Main button: **Open review**
- Shows: filters above (type, status, severity, date, "has location"); **map** and **list** side by side; clicking either opens the **finding drawer** with photo, status, location quality, and source
- Special: map and list **always selected together**; rejected hidden by default; findings without location appear in the list with a "No location" flag; AI suggestions styled differently from verified findings
- Empty: "No findings match these filters" and **Reset filters**
- Requirements: FR-25 to FR-29

**S10 Review finding**: `/projects/{id}/review/{finding_id}`
- Who: `finding.review`
- Main buttons: **Verify**, **Reject**, **Needs field check** (one line explains when to use each)
- Shows: large zoomable photo with the AI box (can be turned off), AI suggestion and **"AI certainty"** (with "how sure the AI is about the type, not how serious the problem is"), type, severity ("how serious is it?", from the rubric, with the chosen level's meaning and a sample-list banner if needed), notes, small map with draggable pin, location source and quality, nearby context, history
- Special: Verify needs type **and** severity; warns if the location is unconfirmed; unsaved-changes warning; if someone else saved first: "This finding was changed by someone else. Reload"; the **next finding opens only after the current decision is saved** (spec), with a "Saved: verified. Here is the next one." notice; keyboard shortcuts for the three decisions
- Requirements: FR-30 to FR-38

**S11 Add manual observation**: dialog from S09
- Who: `finding.create_manual`
- Main button: **Add observation**
- Shows: type (including "Sidewalk observation"), required note, optional photo, location picked on the map
- Special: goes to the review queue as "Awaiting review"
- Requirements: FR-37

**S12 Priority and inspection**: `/projects/{id}/priority`
- Who: `priority.view` (field collectors see **"My inspections"** here instead: the inspections assigned to them)
- Main button: **Plan inspection** (with `inspection.plan`)
- Shows: verified findings ranked by **"Inspection priority"** (score out of 100), each with "How this score was calculated" (what counts, points, share of the score, what it adds) and unknown parts named in plain words ("not known yet, so it adds nothing; nothing is guessed"); owner and planned date; location in words with **Open in Google Maps** for people going on site. Priority settings (shares of the score, points, facilities) are kept as versions for the record.
- Special: never shows unverified or rejected findings; sample-settings banner
- Requirements: FR-39 to FR-43

**S13 Inspection record**: dialog from S12
- Who: `inspection.record` (manager or assigned owner)
- Main buttons: **Mark inspected**, **Mark resolved**, **Reopen**
- Special: resolved needs a note or photo; history listed below
- Requirements: FR-44

**S14 Reports**: `/projects/{id}/reports`
- Who: `report.generate` to create; viewers see shared reports only
- Main button: **Generate report**
- Shows: filters (date, status, type, area), format (CSV / GeoJSON / PDF), "Include unreviewed data" switch, list of past reports with status, count, date, and Share / Download
- Special: verified-only by default; turning on unreviewed data shows a **prominent warning label**; generation runs in the background with progress
- Requirements: FR-45 to FR-50

**S15 Project settings**: `/projects/{id}/settings`, with three sections: **Project details** (S05), **Team** (`/settings/team`), **History** (`/settings/history`, S19). The old addresses `/projects/{id}/team` and `/projects/{id}/history` still open them. Priority settings stay on the Priority tab (S12).
- Who: everyone on the project can see details and team; changes need `project.edit` / `project.members.manage`; History needs `project.audit.view`
- Main button: **Save changes**
- Shows: team list with roles (add or remove a role), archive project
- Special: "Are you sure?" for removals and archiving
- Requirements: FR-09, FR-10, FR-40, FR-51

**S16 Organization: team**: `/settings/team`
- Who: `org.members.view` (changes need admin permissions)
- Main button: **Invite person**
- Shows: members with organization role; pending invitations; "Create reset link" per person
- Special: invite and reset links shown **once** with **Copy**; cannot remove or demote the last admin; all changes recorded
- Requirements: FR-02, FR-03, FR-06, FR-54, FR-55

**S17 Organization: finding types and severity**: `/settings/catalog`
- Who: `org.settings.edit`
- Main button: **Save changes**
- Shows: finding types (label, AI or manual, active, placeholder flag); severity rubric versions
- Special: type codes can't be changed once used; a rubric change creates a new version; placeholder banner
- Requirements: FR-51, FR-52

**S18 Organization: retention**: `/settings/retention`
- Who: `org.retention.edit`
- Main button: **Save changes**
- Special: V1 shows "Automatic deletion is off until retention rules are confirmed (PI-13)"; any change needs confirmation and is recorded
- Requirements: FR-51

**S19 History (audit log)**: `/settings/history` (menu: "Activity history") and `/projects/{id}/settings/history`
- Who: `org.audit.view` / `project.audit.view`
- Shows: who did what and when, filterable by person, action, and date
- Requirements: FR-53

**S20 My account**: `/account`
- Who: signed in
- Shows: name, email, signed-in devices, **Sign out**
- Special: changing the sign-in method later (e.g. single sign-on) only changes this page and S01–S03

**S21 Page not found / Something went wrong**
- Plain message ("This is not your fault…"), **Reload page** and **Go to Home**; after an app update: "The app has been updated. Reload the page."

---

## 3. Build order

| Phase | Screens |
|-------|---------|
| P3 | S01, S02, S03, S16, S20, S21, and the app frame with the left menu |
| P4 | S04, S05, S06 (basic), S07, S17 (finding types) |
| P5 | S08 |
| P6 | S09, S10, S11, S17 (rubric) |
| P7 | S06 (full), S12, S13, S14, S15, S18, S19 |
| UI pass (2026-10-20) | S00 "What to do next", six project tabs, plain wording, notices, offline/session/crash handling |

---

## 4. Changes after the freeze (2026-10-20)

Approved by the owner to make the app easier for non-technical users. **No feature was removed**; pages were moved, not deleted.

| What | Before | After |
|------|--------|-------|
| Project tabs | 9: Overview, Photos, Upload photos, Findings, Priority, Reports, Team, History, Settings | 6: Overview, Photos, Findings, Priority, Reports, Settings |
| Upload photos | A tab | A button on Overview and Photos (same page, same address) |
| Project team, project history | Tabs | Sections of the project Settings tab; old addresses redirect |
| Left menu | One list of 7 items | Home, Projects, My account, then an "Organization settings" group |
| Home (was "Overview") | Charts only | "What to do next" first, then "Numbers and charts" |
| Wording | Technical terms (AI score, weights, scale v1, version N) | Everyday words; project rules kept (AI certainty is never severity; locations are approximate unless confirmed; placeholders marked as samples) |
| Feedback | Errors only | Short "saved" notices; offline strip; session-ended redirect; crash and app-updated pages; central console logging |
