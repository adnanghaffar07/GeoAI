"""Who may do what: the permission policy, in one place.

This file is the code version of `documentation/03-requirements/permission-matrix.md`.

Design rule (permission-matrix.md section 6): the database stores only facts
(who holds which role). What each role may do is defined **only here**. Changing a
decision means editing this file and its tests; no stored data changes.

Some permissions carry a condition (e.g. a field collector may only view **their own**
uploads). Conditions are listed in `CONDITIONS` and enforced by the feature that
uses the permission, in the phase that builds it.
"""

from collections.abc import Iterable


class Perm:
    """Permission keys. Keys are stable: never rename one; add new keys instead."""

    # Organization level
    ORG_VIEW = "org.view"
    ORG_MEMBERS_VIEW = "org.members.view"
    ORG_MEMBERS_INVITE = "org.members.invite"
    ORG_MEMBERS_CHANGE_ROLE = "org.members.change_role"
    ORG_MEMBERS_REMOVE = "org.members.remove"
    ORG_MEMBERS_RESET_PASSWORD = "org.members.reset_password"  # noqa: S105 (a permission name, not a password)
    ORG_SETTINGS_EDIT = "org.settings.edit"
    ORG_RETENTION_EDIT = "org.retention.edit"
    ORG_AUDIT_VIEW = "org.audit.view"
    PROJECT_CREATE = "project.create"

    # Project level (used from P4 onward)
    PROJECT_VIEW = "project.view"
    PROJECT_EDIT = "project.edit"
    PROJECT_MEMBERS_MANAGE = "project.members.manage"
    PROJECT_ARCHIVE = "project.archive"
    PROJECT_AUDIT_VIEW = "project.audit.view"
    IMAGE_UPLOAD = "image.upload"
    IMAGE_STATUS_VIEW = "image.status.view"
    IMAGE_LOCATION_SET = "image.location.set"
    IMAGE_RETRY = "image.retry"
    IMAGE_VIEW = "image.view"
    IMAGE_WITHDRAW = "image.withdraw"
    ANALYSIS_RUN = "analysis.run"
    ANALYSIS_STATUS_VIEW = "analysis.status.view"
    FINDING_VIEW_VERIFIED = "finding.view_verified"
    FINDING_VIEW_CANDIDATES = "finding.view_candidates"
    FINDING_VIEW_REJECTED = "finding.view_rejected"
    FINDING_CREATE_MANUAL = "finding.create_manual"
    FINDING_REVIEW = "finding.review"
    FINDING_MERGE = "finding.merge"
    FINDING_HISTORY_VIEW = "finding.history.view"
    PRIORITY_VIEW = "priority.view"
    PRIORITY_CONFIGURE = "priority.configure"
    INSPECTION_PLAN = "inspection.plan"
    INSPECTION_RECORD = "inspection.record"
    INSPECTION_REOPEN = "inspection.reopen"
    REPORT_GENERATE = "report.generate"
    REPORT_INCLUDE_UNREVIEWED = "report.include_unreviewed"
    REPORT_SHARE = "report.share"
    REPORT_VIEW_SHARED = "report.view_shared"
    REPORT_VIEW_ALL = "report.view_all"


P = Perm

# ---------------------------------------------------------------- organization roles
ORG_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "org_admin": frozenset(
        {
            P.ORG_VIEW,
            P.ORG_MEMBERS_VIEW,
            P.ORG_MEMBERS_INVITE,
            P.ORG_MEMBERS_CHANGE_ROLE,
            P.ORG_MEMBERS_REMOVE,
            P.ORG_MEMBERS_RESET_PASSWORD,
            P.ORG_SETTINGS_EDIT,
            P.ORG_RETENTION_EDIT,
            P.ORG_AUDIT_VIEW,
            P.PROJECT_CREATE,
        }
    ),
    # Decision Q1: org managers may create projects.
    "org_manager": frozenset({P.ORG_VIEW, P.ORG_MEMBERS_VIEW, P.PROJECT_CREATE}),
    "org_member": frozenset({P.ORG_VIEW}),
}

# ---------------------------------------------------------------- project roles
_PROJECT_MANAGER = frozenset(
    {
        P.PROJECT_VIEW,
        P.PROJECT_EDIT,
        P.PROJECT_MEMBERS_MANAGE,
        P.PROJECT_ARCHIVE,  # Q9
        P.PROJECT_AUDIT_VIEW,
        P.IMAGE_UPLOAD,
        P.IMAGE_STATUS_VIEW,
        P.IMAGE_LOCATION_SET,
        P.IMAGE_RETRY,
        P.IMAGE_VIEW,
        P.IMAGE_WITHDRAW,
        P.ANALYSIS_RUN,
        P.ANALYSIS_STATUS_VIEW,
        P.FINDING_VIEW_VERIFIED,
        P.FINDING_VIEW_CANDIDATES,
        P.FINDING_VIEW_REJECTED,
        P.FINDING_CREATE_MANUAL,
        P.FINDING_HISTORY_VIEW,
        P.PRIORITY_VIEW,
        P.PRIORITY_CONFIGURE,
        P.INSPECTION_PLAN,
        P.INSPECTION_RECORD,
        P.INSPECTION_REOPEN,
        P.REPORT_GENERATE,
        P.REPORT_INCLUDE_UNREVIEWED,
        P.REPORT_SHARE,
        P.REPORT_VIEW_SHARED,
        P.REPORT_VIEW_ALL,
    }
)

PROJECT_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "project_manager": _PROJECT_MANAGER,
    "field_collector": frozenset(
        {
            P.PROJECT_VIEW,
            P.IMAGE_UPLOAD,
            P.IMAGE_STATUS_VIEW,
            P.IMAGE_LOCATION_SET,
            P.IMAGE_RETRY,
            P.IMAGE_VIEW,
            P.IMAGE_WITHDRAW,  # Q6
            P.ANALYSIS_RUN,
            P.ANALYSIS_STATUS_VIEW,
            P.FINDING_VIEW_VERIFIED,
            P.FINDING_CREATE_MANUAL,
            P.INSPECTION_RECORD,  # Q7
        }
    ),
    "technical_reviewer": frozenset(
        {
            P.PROJECT_VIEW,
            P.IMAGE_STATUS_VIEW,
            P.IMAGE_LOCATION_SET,
            P.IMAGE_VIEW,
            P.ANALYSIS_STATUS_VIEW,
            P.FINDING_VIEW_VERIFIED,
            P.FINDING_VIEW_CANDIDATES,
            P.FINDING_VIEW_REJECTED,
            P.FINDING_CREATE_MANUAL,
            P.FINDING_REVIEW,  # Q3: only reviewers review
            P.FINDING_MERGE,
            P.FINDING_HISTORY_VIEW,
            P.PRIORITY_VIEW,
            P.INSPECTION_RECORD,  # Q7
            P.REPORT_VIEW_SHARED,  # Q8: view, not generate
        }
    ),
    "viewer": frozenset(
        {
            P.PROJECT_VIEW,
            P.IMAGE_VIEW,  # Q4
            P.FINDING_VIEW_VERIFIED,
            P.PRIORITY_VIEW,
            P.REPORT_VIEW_SHARED,
        }
    ),
}

# Org admins manage every project in their organization without being added to it.
# They do NOT get finding.review / finding.merge (decision Q3).
ORG_ADMIN_PROJECT_PERMISSIONS: frozenset[str] = _PROJECT_MANAGER

# Conditions applied by the feature code (role, permission) -> condition.
CONDITIONS: dict[tuple[str, str], str] = {
    ("field_collector", P.IMAGE_STATUS_VIEW): "own_uploads",
    ("field_collector", P.IMAGE_LOCATION_SET): "own_uploads",
    ("field_collector", P.IMAGE_RETRY): "own_uploads",
    ("field_collector", P.IMAGE_VIEW): "own_uploads",
    ("field_collector", P.IMAGE_WITHDRAW): "own_uploads_before_analysis",
    ("field_collector", P.ANALYSIS_RUN): "own_uploads",
    ("field_collector", P.ANALYSIS_STATUS_VIEW): "own_uploads",
    ("field_collector", P.INSPECTION_RECORD): "assigned_owner",
    ("technical_reviewer", P.INSPECTION_RECORD): "assigned_owner",
    ("viewer", P.IMAGE_VIEW): "verified_findings_only",
}


def org_permissions(org_role: str) -> frozenset[str]:
    """Permissions granted by an organization role (empty for unknown roles)."""
    return ORG_ROLE_PERMISSIONS.get(org_role, frozenset())


def project_permissions(project_roles: Iterable[str], org_role: str | None) -> frozenset[str]:
    """Combined permissions for a person on one project (roles can be combined, Q2)."""
    granted: set[str] = set()
    for role in project_roles:
        granted |= PROJECT_ROLE_PERMISSIONS.get(role, frozenset())
    if org_role == "org_admin":
        granted |= ORG_ADMIN_PROJECT_PERMISSIONS
    return frozenset(granted)
