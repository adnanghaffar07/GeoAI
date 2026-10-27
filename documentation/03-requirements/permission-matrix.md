# Permission Matrix (P1)

**Status:** ACCEPTED by owner on 2026-10-14. All recommendations in section 5 were accepted for V1.
The design keeps these decisions changeable later without touching stored data (section 6).
**Source:** spec section 1 "Users and access", screen table (Settings), data integrity rules, and privacy section.

This table says **who may do what**. It is turned almost directly into code (the central permission check)
and into security tests (every ❌ becomes a "must be blocked" test).

Legend: ✅ allowed · ❌ blocked · 🔸 allowed with a condition (see note)

---

## 1. Rules that apply to every request

1. **Organization boundary.** Every record belongs to one organization and one project. Nobody can see or change anything in another organization. There are no exceptions.
2. **Server-side checks.** Every protected API request is checked on the server, including image downloads, job status, and exports. Hiding a button in the UI is not security.
3. **Hide what you can't access.**
   - **No access to the project** (another organization's, or one you are not a member of): return `404 not_found`, so the project's existence is not revealed.
   - **Can see the project but not do the action:** return `403 permission_denied`.
4. **Removed users lose access immediately.** Removing a member or deactivating a user deletes their sessions.
5. **Invitations expire** (proposed: 7 days) and can only be used once.
6. **Changes are recorded.** Role changes, member removals, settings changes, review decisions, and exports are written to the audit log with who, when, and what changed.
7. **Platform setup is not in the app.** Creating an organization and its first admin is done with a command-line script by the operator (us). There is no "super admin" screen in V1.

---

## 2. Two levels of roles

| Level | Roles | Stored in |
|-------|-------|-----------|
| Organization | `org_admin`, `org_manager`, `org_member` | `organization_memberships` |
| Project | `project_manager`, `field_collector`, `technical_reviewer`, `viewer` | `project_members` |

- **`org_admin`** manages the organization and can **manage** every project in it, without being added to each project.
- **`org_manager`** is an ordinary member who may also **create** projects (see Q1). The creator becomes that project's `project_manager`.
- **`org_member`** has no project access until they are added to a project.
- **Project roles can be combined** (see Q2). A user with two roles gets the permissions of both. Example: on a small pilot, the same person is `project_manager` and `technical_reviewer`.

---

## 3. The matrix

Columns show project roles. "Org admin" means an `org_admin` acting in any project of their organization.

### 3.1 Organization and team

| Action | Permission key | Org admin | Project manager | Field collector | Technical reviewer | Viewer |
|--------|---------------|:-:|:-:|:-:|:-:|:-:|
| View organization member list | `org.members.view` | ✅ | ✅ | ❌ | ❌ | ❌ |
| Invite a user to the organization | `org.members.invite` | ✅ | ❌ | ❌ | ❌ | ❌ |
| Change a user's organization role | `org.members.change_role` | ✅ ¹ | ❌ | ❌ | ❌ | ❌ |
| Remove a user from the organization | `org.members.remove` | ✅ ¹ | ❌ | ❌ | ❌ | ❌ |
| Create a password reset link for a member (CR-001) | `org.members.reset_password` | ✅ | ❌ | ❌ | ❌ | ❌ |
| Edit organization settings (name, finding categories) | `org.settings.edit` | ✅ | ❌ | ❌ | ❌ | ❌ |
| Edit retention settings | `org.retention.edit` | ✅ ² | ❌ | ❌ | ❌ | ❌ |
| View organization-wide audit log | `org.audit.view` | ✅ | ❌ | ❌ | ❌ | ❌ |

¹ An admin cannot remove or demote the **last** `org_admin`, so the organization is never locked out.
² Consequential change: needs a confirmation step and is audited (spec: Settings screen).

### 3.2 Projects

| Action | Permission key | Org admin | Project manager | Field collector | Technical reviewer | Viewer |
|--------|---------------|:-:|:-:|:-:|:-:|:-:|
| Create a project | `project.create` | ✅ | 🔸 ³ | ❌ | ❌ | ❌ |
| See the project in the list and open it | `project.view` | ✅ | ✅ | ✅ | ✅ | ✅ |
| Edit project details (name, boundary, finding types, dates) | `project.edit` | ✅ | ✅ | ❌ | ❌ | ❌ |
| Add or remove project members, assign roles | `project.members.manage` | ✅ | ✅ ⁴ | ❌ | ❌ | ❌ |
| Archive a project | `project.archive` | ✅ | ✅ | ❌ | ❌ | ❌ |
| View the project audit history | `project.audit.view` | ✅ | ✅ | ❌ | ❌ | ❌ |

³ Requires organization role `org_manager` or `org_admin` (Q1).
⁴ A project manager can only add people who are already in the organization; only an org admin invites new people.

### 3.3 Photos and uploads

| Action | Permission key | Org admin | Project manager | Field collector | Technical reviewer | Viewer |
|--------|---------------|:-:|:-:|:-:|:-:|:-:|
| Upload photos | `image.upload` | ✅ | ✅ | ✅ | ❌ | ❌ |
| See upload status | `image.status.view` | ✅ | ✅ | 🔸 own | ✅ | ❌ |
| Set or confirm a photo's location (missing GPS) | `image.location.set` | ✅ | ✅ | 🔸 own | ✅ | ❌ |
| Replace or retry a failed upload | `image.retry` | ✅ | ✅ | 🔸 own | ❌ | ❌ |
| View or download original photos | `image.view` | ✅ | ✅ | 🔸 own | ✅ | 🔸 ⁵ |
| Withdraw an upload | `image.withdraw` | ✅ | ✅ | 🔸 own, before analysis ⁶ | ❌ | ❌ |

"Own" = photos the user uploaded (`images.uploaded_by`).
⁵ Recommended: viewers may see only photos linked to **verified** findings, subject to the masking policy (Q4).
⁶ Nothing is hard-deleted. Withdrawing marks the photo as withdrawn and keeps an audit record. Real deletion only follows the retention policy.

### 3.4 Analysis jobs

| Action | Permission key | Org admin | Project manager | Field collector | Technical reviewer | Viewer |
|--------|---------------|:-:|:-:|:-:|:-:|:-:|
| Start or retry analysis | `analysis.run` | ✅ | ✅ | 🔸 own uploads | ❌ | ❌ |
| View job status | `analysis.status.view` | ✅ | ✅ | 🔸 own uploads | ✅ | ❌ |

### 3.5 Findings and review

| Action | Permission key | Org admin | Project manager | Field collector | Technical reviewer | Viewer |
|--------|---------------|:-:|:-:|:-:|:-:|:-:|
| View **verified** findings (map, list, drawer) | `finding.view_verified` | ✅ | ✅ | ✅ | ✅ | ✅ |
| View **unreviewed** AI candidates | `finding.view_candidates` | ✅ | ✅ | ❌ ⁷ | ✅ | ❌ |
| View **rejected** findings (hidden by default) | `finding.view_rejected` | ✅ | ✅ | ❌ | ✅ | ❌ |
| Create a manual observation (incl. sidewalk) | `finding.create_manual` | ✅ | ✅ | ✅ | ✅ | ❌ |
| Verify / reject / mark "needs field check" | `finding.review` | ❌ ⁸ | ❌ ⁸ | ❌ | ✅ | ❌ |
| Edit type, severity, corrected location, notes | `finding.review` | ❌ ⁸ | ❌ ⁸ | ❌ | ✅ | ❌ |
| Merge duplicate findings | `finding.merge` | ❌ ⁸ | ❌ ⁸ | ❌ | ✅ | ❌ |
| Confirm or change the suggested road association | `finding.review` | ❌ ⁸ | ❌ ⁸ | ❌ | ✅ | ❌ |
| View a finding's review history | `finding.history.view` | ✅ | ✅ | ❌ | ✅ | ❌ |

⁷ Recommended: collectors see **processing status** of their uploads, not the AI's guesses. That keeps them from treating unreviewed candidates as facts. They do see verified findings.
⁸ Recommended: **only `technical_reviewer` can review**, because severity must come from a qualified reviewer. A manager or admin who is qualified is simply also given the reviewer role on that project (Q2, Q3).

### 3.6 Inspection priority and inspections

| Action | Permission key | Org admin | Project manager | Field collector | Technical reviewer | Viewer |
|--------|---------------|:-:|:-:|:-:|:-:|:-:|
| View inspection priority and score breakdown | `priority.view` | ✅ | ✅ | ❌ | ✅ | ✅ |
| Configure priority weights and inputs | `priority.configure` | ✅ | ✅ ² | ❌ | ❌ | ❌ |
| Plan an inspection (owner, date) | `inspection.plan` | ✅ | ✅ | ❌ | ❌ | ❌ |
| Record outcome: inspected / resolved with evidence | `inspection.record` | ✅ | ✅ | 🔸 ⁹ | 🔸 ⁹ | ❌ |
| Reopen a resolved finding | `inspection.reopen` | ✅ | ✅ | ❌ | ❌ | ❌ |

⁹ Recommended: the person named as the inspection's owner can record its outcome, whatever their role. The owner must be a project member.

### 3.7 Reports and exports

| Action | Permission key | Org admin | Project manager | Field collector | Technical reviewer | Viewer |
|--------|---------------|:-:|:-:|:-:|:-:|:-:|
| Generate CSV / GeoJSON / PDF (verified only) | `report.generate` | ✅ | ✅ | ❌ | ❌ | ❌ |
| Include unreviewed data (prominently labelled) | `report.include_unreviewed` | ✅ | ✅ | ❌ | ❌ | ❌ |
| Share a report with viewers ("approve") | `report.share` | ✅ | ✅ | ❌ | ❌ | ❌ |
| View and download shared reports | `report.view_shared` | ✅ | ✅ | ❌ | ✅ | ✅ |
| View all reports and the export log | `report.view_all` | ✅ | ✅ | ❌ | ❌ | ❌ |

---

## 4. How this becomes code

1. Each **permission key** above becomes a constant (e.g. `project.edit`).
2. One table in code maps each role to its set of keys. Org admin gets the management keys for every project in its organization.
3. Every protected route declares the key it needs. The central dependency:
   1. loads the user's org membership and project roles,
   2. returns `404` if the user has no access to the project at all,
   3. returns `403` if they have access but lack the key,
   4. applies 🔸 conditions ("own", "assigned owner") inside the service, using the same helper everywhere.
4. Tests: one test per ❌ cell, plus the cross-organization ID-swap tests from the acceptance criteria.

---

## 5. Decisions (owner accepted all recommendations, 2026-10-14)

| # | Question | Decision | Why |
|---|----------|----------------|-----|
| Q1 | Who may create projects? Spec says the project manager creates projects, but a project role cannot exist before the project does. | Add org role `org_manager`: org admins and org managers can create projects, and the creator becomes project manager. | Keeps the spec's intent without admin bottlenecks |
| Q2 | Can one user hold several roles on the same project? | **Yes**: permissions are combined. | Small pilot teams: the manager is often also the qualified reviewer |
| Q3 | Can a project manager or org admin review findings without the reviewer role? | **No**: only `technical_reviewer` can review; give qualified managers that role too. | Severity must come from a qualified reviewer (spec); this makes it explicit and auditable |
| Q4 | Can viewers see original photos? | Only photos of **verified** findings, after any required face/plate masking. | Spec: "restrict media access"; viewers need evidence but not raw uploads |
| Q5 | Can collectors see unreviewed AI candidates? | **No**: status only, plus verified findings. | Avoids treating AI guesses as facts |
| Q6 | Can a collector withdraw their own upload? | Yes, only **before** analysis starts; soft withdraw with an audit record. | Fixes mistakes without losing history |
| Q7 | Who records inspection outcomes? | Project managers, plus whoever is the inspection's assigned owner. | Field staff often do the site visit |
| Q8 | Can technical reviewers generate exports? | **No** (they can view shared reports). | Spec gives exports to managers |
| Q9 | Can project managers archive their projects? | **Yes**: archive only, no hard delete. | Normal project lifecycle |
| Q10 | Invitation expiry period | 7 days | Common default; short enough to be safe |

---

## 6. Designed for change: policy in code, facts in the database

The owner may change any decision above later. The design makes that a **code change in one file, with no data migration and no change to existing records.**

### Rule 1: the database stores facts, never permissions
The database records only **who holds which role** and **what happened**:
- `organization_memberships`: user, organization, org role
- `project_members`: user, project, project role (one row per role, so combining roles needs no schema change)
- facts the conditions need, always recorded whatever the current policy: `images.uploaded_by`, `inspections.owner_user_id`, `findings.review_status`, `reports.shared_with_viewers`

There is **no** `permissions` column or per-user permission table. Nothing in the data says "this user may review".

### Rule 2: what each role may do lives in one code file
`backend/app/core/permissions.py` will hold the mapping *role → permission keys* from section 3, plus the condition helpers ("own upload", "assigned owner", "verified only").
Changing a decision means editing that mapping and its tests. For example:
- **Q3 reversed** (managers may review): add `finding.review` to `project_manager`. Existing findings and review events are untouched.
- **Q4 changed** (viewers see all photos): change the viewer condition from "verified only" to "all". No data changes.

### Rule 3: role names are plain text with a check list, not a database enum
Roles are stored as text, validated by a `CHECK` constraint and by the code. Adding a role later is a small migration that only widens the check. If a role is ever retired, existing rows are moved to another role in a reviewed migration, never deleted.

### Rule 4: history records what was true at the time
Audit and review events store the actor, the action key, and the **roles the actor held at that moment**. If policy changes later, old records still show truthfully who did what and with which role.

### Rule 5: permission tests follow the mapping
The "must be blocked" tests are generated from the same mapping, so a policy change updates the tests in the same place and nothing is missed.
