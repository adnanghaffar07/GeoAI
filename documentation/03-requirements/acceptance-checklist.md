# Acceptance Checklist (P1)

**Status:** Draft, 2026-10-14.

## In plain words

This is the **exam the app must pass**. Each line is one test: "do this, and this must happen".
When every line passes, version 1 is finished. Each test points to the requirement it proves (from `03-requirements/requirements.md`).

- **How:** `Auto` = an automated test the computer runs every time. `Manual` = a person tries it on screen. `Partner` = needs the customer (real photos, real reviewer).
- **When:** the phase where the test is first written and must pass. Everything is run again in P9 (system testing).
- The ✅ column is ticked only after the test has **actually been run and passed**.

---

## 1. Security and organization isolation

| # | Test | Proves | How | When | ✅ |
|---|------|--------|-----|------|----|
| AC-01 | A user from Organization A changes the ID in a link to a project of Organization B. They get "not found" and see nothing. | FR-05, NFR-01 | Auto | P3 || ✅ org level, 2026-10-14 (projects in P4) |
| AC-02 | The same ID-swap test, for photos, photo downloads, findings, jobs, and reports. All blocked. | FR-05, FR-18, NFR-01 | Auto | P4–P7 || ✅ projects, photos, photo files, 2026-10-14 (findings, jobs, reports in P5–P7) |
| AC-03 | For every ❌ cell in the permission matrix, a user with that role tries the action and is blocked. | FR-04 | Auto | P3–P7 || ✅ org level and project/photo actions, 2026-10-14 (findings, reports in P5–P7) |
| AC-04 | An admin removes a user who is signed in. The user's very next action is refused. | FR-03 | Auto | P3 || ✅ 2026-10-14 |
| AC-05 | An invitation used after 7 days, or used twice, is refused. | FR-02 | Auto | P3 || ✅ 2026-10-14 |
| AC-06 | A role change is visible in the audit log with who, when, old role, and new role. | FR-06 | Auto | P3 || ✅ 2026-10-14 |
| AC-07 | Passwords are stored hashed; the database contains no readable passwords. | NFR-02 | Auto | P3 || ✅ 2026-10-14 |
| AC-51 | A password reset link works once, and not after 1 hour. Using it ends the person's other sign-ins. (CR-001) | FR-55 | Auto | P3 || ✅ 2026-10-14 |
| AC-52 | Creating an invitation shows a copyable link; the link is not shown again afterwards. (CR-001) | FR-54 | Auto + Manual | P3 || ✅ 2026-10-14 |
| AC-08 | Nobody can open a photo by guessing its file address; photos only come through the app after a permission check. | FR-18 | Auto | P4 || ✅ 2026-10-14 |

## 2. Projects

| # | Test | Proves | How | When | ✅ |
|---|------|--------|-----|------|----|
| AC-09 | Create a project with a drawn area, and another from an uploaded GeoJSON file. Both are saved and shown on the map. | FR-07 | Auto + Manual | P4 || ✅ 2026-10-14 (tests + browser) |
| AC-10 | Submit the project form with a missing name. The error shows next to the field, and the other entries are kept. | FR-08 | Manual | P4 || ✅ 2026-10-14 (test + browser) |
| AC-11 | An archived project can be viewed but not changed. Nothing is deleted. | FR-10 | Auto | P4 || ✅ 2026-10-14 |

## 3. Uploading photos

| # | Test | Proves | How | When | ✅ |
|---|------|--------|-----|------|----|
| AC-12 | Upload 20 photos: each one shows progress and "done". | FR-11, FR-12 | Manual | P4 || ◐ checked with 3 photos in a test browser; owner to try 20 real photos |
| AC-13 | Upload a broken file and a .txt file. Each shows a clear reason and a replace option; the others still upload. | FR-12, FR-16 | Auto + Manual | P4 || ✅ 2026-10-14 (tests + browser) |
| AC-14 | Upload the same photo twice, and retry after a network drop. Only one copy exists. | FR-13, NFR-04 | Auto | P4 || ✅ 2026-10-14 |
| AC-15 | A photo with GPS gets its location and capture time. A photo without GPS is flagged and gets **no** location until someone picks one. | FR-14, FR-15 | Auto | P4 || ✅ 2026-10-14 |
| AC-16 | A blurry photo and a very dark photo are flagged with the reason. | FR-16 | Auto | P4 || ✅ 2026-10-14 |
| AC-17 | Every location shows its source (photo GPS / phone GPS / picked on map). | FR-17 | Auto + Manual | P4 || ✅ 2026-10-14 (tests + browser) |
| AC-18 | The upload screen works on a phone browser. | NFR-07 | Manual | P4 || ◐ checked at phone size in a test browser; owner to confirm on a real phone |

## 4. AI analysis

| # | Test | Proves | How | When | ✅ |
|---|------|--------|-----|------|----|
| AC-19 | Start analysis. The screen shows waiting, then processing, then done. | FR-19 | Auto + Manual | P5 | Pass 2026-10-15 (tests + browser) |
| AC-20 | Each result shows type, confidence, box, source photo, and model version. | FR-20 | Auto | P5 | Pass 2026-10-15 (tests) |
| AC-21 | Make an analysis fail, then retry it. Results are not duplicated. | FR-21, NFR-04 | Auto | P5 | Pass 2026-10-15 (tests) |
| AC-22 | AI results start as "unreviewed" and never appear as verified or in the priority list without review. | FR-22, FR-39 | Auto | P5 | Pass 2026-10-15 for P5 (all AI results start `ai_generated`; priority list arrives in P7) |
| AC-23 | A photo with no AI results says "no candidates found", not "road is fine". | FR-24 | Manual | P5 | Pass 2026-10-15 (browser) |

## 5. Map and review

| # | Test | Proves | How | When | ✅ |
|---|------|--------|-----|------|----|
| AC-24 | Click a pin: the same finding is selected in the list. Click in the list: the map pin is selected. | FR-25 | Manual | P6 | Pass 2026-10-15 (test + browser) |
| AC-25 | Apply a filter: the map and list show the same findings and the same count. | FR-26 | Auto + Manual | P6 | Pass 2026-10-15 (test; the map shows the same findings minus those without a location, which the list flags) |
| AC-26 | A finding without a location is in the list, flagged. Rejected findings are hidden until the filter shows them. | FR-27, FR-28 | Auto | P6 | Pass 2026-10-15 (tests) |
| AC-27 | Trying to verify without choosing type and severity is refused. | FR-31 | Auto | P6 | Pass 2026-10-15 (tests) |
| AC-28 | A reviewer changes the type and moves the pin. The original AI result and original location are still stored, unchanged. | FR-32, FR-33 | Auto | P6 | Pass 2026-10-15 (tests) |
| AC-29 | Each review decision shows who, when, what changed, and the decision. | FR-34 | Auto | P6 | Pass 2026-10-15 (tests) |
| AC-30 | Two reviewers open the same finding. The first saves. The second's save is refused with a "reload" message. | FR-35 | Auto | P6 | Pass 2026-10-15 (tests + browser) |
| AC-31 | Leaving the review screen with unsaved changes shows a warning. | FR-36 | Manual | P6 | Pass 2026-10-15 (test + browser) |
| AC-32 | A manual sidewalk observation can be created and goes to review. | FR-37 | Auto + Manual | P6 | Pass 2026-10-15 (tests + browser) |
| AC-33 | The whole review flow can be done with the keyboard only. | NFR-08 | Manual | P6 | Partial 2026-10-15: decisions, type, severity, notes by keyboard; moving the pin needs a mouse or touch |

## 6. Priority, inspection, reports

| # | Test | Proves | How | When | ✅ |
|---|------|--------|-----|------|----|
| AC-34 | Rejected and unreviewed findings never get a priority score. | FR-39 | Auto | P7 | Pass 2026-10-15 (tests) |
| AC-35 | The score breakdown shows each input, its weight, and flags any missing input. | FR-40, FR-41 | Auto + Manual | P7 | Pass 2026-10-15 (tests + browser) |
| AC-36 | Changing priority weights is recorded in the history; old scores keep the weights version they used. | FR-51, NFR-09 | Auto | P7 | Pass 2026-10-15 (tests) |
| AC-37 | Plan an inspection, mark it resolved with a photo, reopen it. The full history is kept. | FR-43, FR-44 | Auto + Manual | P7 | Pass 2026-10-15 (tests + browser) |
| AC-38 | Export with a filter: the CSV, GeoJSON, and PDF each contain exactly the filtered number of findings. | FR-45, FR-47 | Auto | P7 | Pass 2026-10-15 (tests; GeoJSON contains the located ones and counts the rest in its metadata) |
| AC-39 | A default export contains only verified findings. Including unreviewed data adds a clear label. | FR-46 | Auto | P7 | Pass 2026-10-15 (tests) |
| AC-40 | Each export shows date, filters, review status, and limitations, and appears in the export log. | FR-48 | Auto | P7 | Pass 2026-10-15 (tests) |
| AC-41 | A finding with an unconfirmed location is left out of, or flagged in, the GeoJSON export. | FR-49 | Auto | P7 | Pass 2026-10-15 (tests) |
| AC-42 | Placeholder settings show the "placeholder" banner and are marked in exports. | FR-52 | Manual | P7 | Pass 2026-10-15 (browser + tests) |

## 7. Errors and quality

| # | Test | Proves | How | When | ✅ |
|---|------|--------|-----|------|----|
| AC-43 | Any error shows a clear message and a reference ID, never internal details. | NFR-05 | Auto | P3 onward | ✅ (foundation: verified 2026-10-14) |
| AC-44 | Stop the database: the app says a service is unavailable instead of crashing. | NFR-05 | Auto + Manual | P3 | ✅ (verified 2026-10-14) |
| AC-45 | Every screen has a loading, empty, error, and success state. | NFR-06 | Manual | P4–P7 | |

## 8. Pilot (needs the customer)

| # | Test | Proves | How | When | ✅ |
|---|------|--------|-----|------|----|
| AC-46 | The AI meets the per-class accuracy targets agreed with the customer, on photos it never trained on. | FR-23, PI-17 | Partner | P8 | |
| AC-47 | Real users complete upload, review, and export without help. | NFR-07, NFR-08 | Partner | P9 | |
| AC-48 | The app handles the expected number of photos; timings are measured and recorded. | NFR-11 | Auto + Manual | P9 | |
| AC-49 | A backup is restored successfully onto a fresh server. | NFR-12 | Manual | P10 | |
| AC-50 | Monitoring alerts on failed jobs and slow queues. | NFR-12 | Manual | P10 | |
