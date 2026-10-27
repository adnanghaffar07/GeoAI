# Requirements: Version 1 (P1)

**Status:** Accepted by owner, 2026-10-14.
**Source:** the requirements and UI/UX specification (see `source-documents/`), plus decisions in `03-requirements/permission-matrix.md` and `03-requirements/partner-inputs.md`.

## In plain words

This is the list of **everything version 1 must do**, and **everything it will not do yet**.
Each line has a number (like `FR-12`) so we can point to it later: "FR-12 is built and tested".

- **FR** = functional requirement: something the app does.
- **NFR** = non-functional requirement: how well it must do it (security, speed, reliability).
- "Must" = required for version 1.

---

## 1. Accounts and access

| ID | Requirement |
|----|-------------|
| FR-01 | Users sign in with email and password. There is no public sign-up; people join by invitation only. |
| FR-02 | An organization admin can invite people by email. Invitations expire after 7 days and work only once. |
| FR-03 | An organization admin can change a person's role or remove them. Removed people lose access immediately. |
| FR-04 | The roles and what each may do follow `03-requirements/permission-matrix.md`. |
| FR-05 | People never see anything from another organization, even by changing a link or ID. |
| FR-06 | Role changes, removals, and settings changes are recorded with who did it and when. |
| FR-54 | *(Added 2026-10-14, change CR-001)* After creating an invitation, the app shows the invite link once with a **Copy** button, so the admin can send it themselves. Automatic invite emails come later. |
| FR-55 | *(Added 2026-10-14, change CR-001)* An org admin can create a **password reset link** for a member. It works once, for 1 hour. Setting a new password ends all of that person's existing sign-ins. |

## 2. Projects

| ID | Requirement |
|----|-------------|
| FR-07 | An org admin or org manager can create a project with: name, survey area (drawn on the map or uploaded as a GeoJSON file), finding types, project manager, and assigned reviewers. Optional: survey dates, road category, partner reference number. |
| FR-08 | If the project form has errors, the user's entries are kept and the errors are shown next to the fields. |
| FR-09 | A project manager can add or remove project members and give them roles. |
| FR-10 | A project manager can archive a project. Archived projects are read-only and nothing is deleted. |

## 3. Uploading photos

| ID | Requirement |
|----|-------------|
| FR-11 | Collectors upload JPEG or PNG photos in batches, from a desktop or a phone browser. |
| FR-12 | Each file shows its own progress and either "done" or a clear reason it failed, with a retry or replace option. |
| FR-13 | Uploading the same file twice does not create a duplicate. |
| FR-14 | The app reads the photo's capture time and GPS location when present. |
| FR-15 | Photos without GPS are flagged. The user can pick the location on the map. The app never makes up a location. |
| FR-16 | The app flags photos that are blurry, too dark, or unreadable, with the reason. |
| FR-17 | Every location shows where it came from: photo GPS, phone GPS, or picked on the map. |
| FR-18 | Photos are stored privately and can only be opened by people allowed to see them. |

## 4. AI analysis

| ID | Requirement |
|----|-------------|
| FR-19 | A manager or collector starts analysis. It runs in the background, and the screen shows: waiting, processing, done, or failed. |
| FR-20 | Each AI result records: the suspected problem type, the AI's confidence score, the box around it in the photo, the photo it came from, and the AI model version. |
| FR-21 | Retrying a failed analysis never creates duplicate results. |
| FR-22 | AI results are only **suggestions**. They are never treated as confirmed. |
| FR-23 | V1 AI looks for road problems only: pothole, surface cracking, pavement deterioration (placeholder list, PI-05). Until a trained model passes its accuracy check, a clearly labelled test detector is used. |
| FR-24 | "No problems found" means the AI found nothing. The app must not say the road is fine. |

## 5. Map and findings list

| ID | Requirement |
|----|-------------|
| FR-25 | A map shows findings as pins, next to a list of the same findings. Selecting one in the map selects it in the list, and the other way round. |
| FR-26 | Filters (type, status, severity, date) apply to both the map and the list. |
| FR-27 | Findings without a location still appear in the list, clearly flagged. |
| FR-28 | Rejected findings are hidden by default and can be shown with a filter. |
| FR-29 | Clicking a finding opens a side panel with its photo, details, and history. |

## 6. Reviewing findings

| ID | Requirement |
|----|-------------|
| FR-30 | A reviewer sees the photo (with zoom), the AI box (can be turned off), the map pin, and nearby context. |
| FR-31 | The reviewer chooses **Verify**, **Reject**, or **Needs field check**. Verify requires choosing a type and a severity. |
| FR-32 | The reviewer can change the type, severity, notes, and move the pin. |
| FR-33 | The original AI result and the original location are **never overwritten**. Changes are stored separately. |
| FR-34 | Every review decision is saved with who, when, what changed, and the decision. |
| FR-35 | If two people edit the same finding at once, the second save is refused with a "reload" message. Nobody's work is silently overwritten. |
| FR-36 | The app warns before leaving the review screen with unsaved changes. |
| FR-37 | Sidewalk problems are added **manually** in V1 (no sidewalk AI). Manual findings go to review like AI ones. |
| FR-38 | Severity uses the rubric from PI-06 (placeholder until the customer confirms). AI confidence is never used as severity. |

## 7. Inspection priority and follow-up

| ID | Requirement |
|----|-------------|
| FR-39 | Only verified findings get an inspection priority score. |
| FR-40 | The score combines severity, road category, and nearness to selected facilities, using configurable weights (placeholder, PI-08). |
| FR-41 | The app shows how the score was calculated, including any missing inputs. Missing inputs are flagged, never guessed. |
| FR-42 | The score is always called "inspection priority". It does not decide repairs or compliance. |
| FR-43 | A manager can plan an inspection: owner and date. |
| FR-44 | The owner or manager can mark it inspected, or resolved with a note or photo. A resolved item can be reopened; history is kept. |

## 8. Reports and exports

| ID | Requirement |
|----|-------------|
| FR-45 | Managers can export CSV, GeoJSON, and a PDF summary. |
| FR-46 | Exports include verified findings by default. Unreviewed data can be included only with a clear label. |
| FR-47 | The number of records in an export matches the chosen filters. |
| FR-48 | Every export states its date, filters, review status, and location limitations. Every export is logged. |
| FR-49 | Findings with an unconfirmed location are left out of map exports, or clearly flagged. |
| FR-50 | A manager can share a report with viewers. |

## 9. Settings and history

| ID | Requirement |
|----|-------------|
| FR-51 | Admins manage team roles, finding categories, priority settings, and retention. Important changes ask for confirmation and are recorded. |
| FR-52 | Placeholder settings show a "placeholder" banner until the customer confirms them. |
| FR-53 | Admins and project managers can view the history (audit log) of their organization or project. |

---

## 10. Quality requirements (NFR)

| ID | Requirement |
|----|-------------|
| NFR-01 | **Security:** every request is permission-checked on the server, including photo downloads, job status, and exports. |
| NFR-02 | **Security:** passwords are stored hashed (Argon2); secrets are never in the code. |
| NFR-03 | **Data safety:** nothing is deleted or overwritten without permission; original photos and history are protected. |
| NFR-04 | **Reliability:** retries never create duplicate photos, jobs, or findings. |
| NFR-05 | **Errors:** every error shows a clear message and a reference ID. Internal details are never shown to users. |
| NFR-06 | **Screens:** every screen handles loading, empty, error, and success states. |
| NFR-07 | **Devices:** manager and reviewer screens work on desktop; the upload screen works on a phone browser. |
| NFR-08 | **Accessibility:** the review flow works with a keyboard, and a list is always available as an alternative to the map. |
| NFR-09 | **Changeability:** settings and permission decisions can change later without changing stored records (see `03-requirements/permission-matrix.md` §6, `03-requirements/partner-inputs.md` §3). |
| NFR-10 | **Testing:** each feature has automated tests that are actually run before it counts as done. |
| NFR-11 | **Performance:** handles the placeholder pilot volume (5,000 photos, PI-15). Measured in P9. |
| NFR-12 | **Operations (pilot):** HTTPS, backups with a tested restore, and monitoring of job errors and queue delays. |

---

## 11. Not in version 1 (later)

- Native phone app or offline capture (V1 uses the phone's web browser)
- Video upload
- Automatic sidewalk AI
- Comparing the same road over time
- Route planning for inspectors
- Repair cost or budget estimates
- Work orders, or connecting to other city systems
- Exact defect size or depth measurement
- Certifying accessibility compliance or structural safety
- Login with Google or Microsoft (V1 uses email and password)
- Automatic emails (invites, "forgot password"). V1 shows links on screen for the admin to share (FR-54, FR-55)
- Automatic face and licence-plate masking (until the customer's policy is known, PI-14)

## 12. Built if time allows (still V1, lower priority)

- Suggesting which road a finding belongs to (the reviewer confirms)
- Suggesting possible duplicate findings, and letting a reviewer merge them
