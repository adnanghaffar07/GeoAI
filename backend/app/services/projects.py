"""Business rules for projects and project teams.

Functions change the session but do not commit; routes commit once per action.
"""

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import ColumnElement, Integer, cast, delete, exists, func, select
from sqlalchemy.orm import Session

from app.core.auth import OrgContext, ProjectContext
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models import (
    AnalysisJob,
    Finding,
    FindingType,
    Image,
    Inspection,
    OrganizationMembership,
    Project,
    ProjectMember,
    User,
)
from app.models.base import utc_now
from app.models.priority import ACTIVE_INSPECTION_STATES
from app.schemas.projects import GeoJsonArea, ProjectCreate, ProjectUpdate
from app.services.audit import record_event


# ------------------------------------------------------------------- shared helpers
def _area_expression(area: GeoJsonArea) -> ColumnElement[Any]:
    """SQL that turns GeoJSON into a WGS 84 MultiPolygon."""
    return func.ST_Multi(func.ST_SetSRID(func.ST_GeomFromGeoJSON(area.model_dump_json()), 4326))


def validate_area(db: Session, area: GeoJsonArea) -> None:
    """Ask PostGIS whether the shape is valid (no crossing edges, has an area).

    Raises:
        ValidationFailedError: with a plain-language reason.
    """
    geometry = _area_expression(area)
    valid, reason, square_meters = db.execute(
        select(
            func.ST_IsValid(geometry),
            func.ST_IsValidReason(geometry),
            func.ST_Area(cast(geometry, Geography())),  # square meters
        )
    ).one()
    if not valid:
        raise ValidationFailedError(
            "The survey area shape is not valid. Check that its edges do not cross.",
            details={"fields": [{"field": "body.boundary", "message": reason}]},
        )
    if not square_meters or square_meters <= 0:
        raise ValidationFailedError(
            "The survey area has no size.",
            details={"fields": [{"field": "body.boundary", "message": "Area is zero."}]},
        )


def _check_finding_types(db: Session, organization_id: uuid.UUID, keys: list[str]) -> list[str]:
    unique_keys = list(dict.fromkeys(keys))
    active = set(
        db.scalars(
            select(FindingType.key).where(
                FindingType.organization_id == organization_id,
                FindingType.key.in_(unique_keys),
                FindingType.is_active.is_(True),
            )
        ).all()
    )
    unknown = [key for key in unique_keys if key not in active]
    if unknown:
        raise ValidationFailedError(
            "Some finding types are not available in this organization.",
            details={
                "fields": [{"field": "body.finding_type_keys", "message": ", ".join(unknown)}]
            },
        )
    return unique_keys


def _check_org_members(db: Session, organization_id: uuid.UUID, user_ids: list[uuid.UUID]) -> None:
    found = set(
        db.scalars(
            select(OrganizationMembership.user_id).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id.in_(user_ids),
            )
        ).all()
    )
    if missing := [str(user_id) for user_id in user_ids if user_id not in found]:
        raise ValidationFailedError(
            "Some people are not members of this organization.",
            details={"fields": [{"field": "body.user_ids", "message": ", ".join(missing)}]},
        )


def ensure_not_archived(ctx: ProjectContext) -> None:
    if ctx.project.archived_at is not None:
        raise ConflictError("This project is archived and can no longer be changed.")


# ------------------------------------------------------------------------- projects
def create_project(db: Session, ctx: OrgContext, body: ProjectCreate) -> Project:
    """Create a project. The creator becomes its project manager (decision Q1)."""
    org_id = ctx.organization.id
    keys = _check_finding_types(db, org_id, body.finding_type_keys)
    reviewers = list(dict.fromkeys(body.reviewer_user_ids))
    _check_org_members(db, org_id, reviewers)
    validate_area(db, body.boundary)

    project = Project(
        organization_id=org_id,
        name=body.name,
        boundary=_area_expression(body.boundary),
        finding_type_keys=keys,
        road_category=(body.road_category or "").strip() or None,
        survey_start=body.survey_start,
        survey_end=body.survey_end,
        partner_reference=(body.partner_reference or "").strip() or None,
        created_by=ctx.user.id,
    )
    db.add(project)
    db.flush()
    db.add(
        ProjectMember(
            project_id=project.id, user_id=ctx.user.id, role="project_manager", added_by=ctx.user.id
        )
    )
    for reviewer_id in reviewers:
        db.add(
            ProjectMember(
                project_id=project.id,
                user_id=reviewer_id,
                role="technical_reviewer",
                added_by=ctx.user.id,
            )
        )
    record_event(
        db,
        action="project.created",
        organization_id=org_id,
        project_id=project.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="project",
        target_id=project.id,
        details={
            "name": project.name,
            "finding_type_keys": keys,
            "reviewers": [str(r) for r in reviewers],
        },
    )
    return project


def update_project(db: Session, ctx: ProjectContext, body: ProjectUpdate) -> Project:
    ensure_not_archived(ctx)
    project = ctx.project
    changes: dict[str, Any] = {}
    fields = body.model_fields_set

    if "name" in fields and body.name is not None:
        name = body.name.strip()
        if not name:
            raise ValidationFailedError("Enter a project name.")
        if name != project.name:
            changes["name"] = {"old": project.name, "new": name}
            project.name = name
    if "finding_type_keys" in fields and body.finding_type_keys is not None:
        keys = _check_finding_types(db, project.organization_id, body.finding_type_keys)
        if keys != list(project.finding_type_keys):
            changes["finding_type_keys"] = {"old": project.finding_type_keys, "new": keys}
            project.finding_type_keys = keys
    if "boundary" in fields and body.boundary is not None:
        validate_area(db, body.boundary)
        project.boundary = _area_expression(body.boundary)
        changes["boundary"] = "changed"
    for name in ("road_category", "partner_reference"):
        if name in fields:
            value = (getattr(body, name) or "").strip() or None
            if value != getattr(project, name):
                changes[name] = {"old": getattr(project, name), "new": value}
                setattr(project, name, value)
    for name in ("survey_start", "survey_end"):
        if name in fields and getattr(body, name) != getattr(project, name):
            changes[name] = {"old": str(getattr(project, name)), "new": str(getattr(body, name))}
            setattr(project, name, getattr(body, name))
    if project.survey_start and project.survey_end and project.survey_end < project.survey_start:
        raise ValidationFailedError("Survey end date must be on or after the start date.")

    if changes:
        record_event(
            db,
            action="project.changed",
            organization_id=project.organization_id,
            project_id=project.id,
            actor_user_id=ctx.user.id,
            actor_roles=ctx.actor_roles,
            target_type="project",
            target_id=project.id,
            details=changes,
        )
    return project


def archive_project(db: Session, ctx: ProjectContext) -> Project:
    project = ctx.project
    if project.archived_at is None:
        project.archived_at = utc_now()
        record_event(
            db,
            action="project.archived",
            organization_id=project.organization_id,
            project_id=project.id,
            actor_user_id=ctx.user.id,
            actor_roles=ctx.actor_roles,
            target_type="project",
            target_id=project.id,
        )
    return project


@dataclass
class Counts:
    images: int
    images_missing_location: int
    images_with_quality_flags: int
    images_analysed: int = 0  # photos whose analysis finished (current model)
    # Photos the current AI model has not been asked to check yet ("Check new photos" sends these).
    images_waiting_for_ai: int = 0
    findings_to_review: int = 0  # AI suggestions and manual findings not yet reviewed
    findings_needs_field_check: int = 0
    findings_verified: int = 0
    # Verified findings whose position a reviewer has not confirmed (incl. no location).
    verified_location_unconfirmed: int = 0
    verified_by_type: dict[str, int] = field(default_factory=dict)
    inspections_open: int = 0  # planned or inspected, not yet resolved


def project_counts(db: Session, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, Counts]:
    if not project_ids:
        return {}
    rows = db.execute(
        select(
            Image.project_id,
            func.count(),
            func.sum(cast(Image.location_source == "none", Integer)),
            func.sum(cast(func.cardinality(Image.quality_flags) > 0, Integer)),
        )
        .where(Image.project_id.in_(project_ids), Image.status == "stored")
        .group_by(Image.project_id)
    ).all()
    counts = {
        pid: Counts(int(total), int(missing or 0), int(flagged or 0))
        for pid, total, missing, flagged in rows
    }
    analysed = dict(
        db.execute(
            select(Image.project_id, func.count())
            .join(AnalysisJob, AnalysisJob.image_id == Image.id)
            .where(
                Image.project_id.in_(project_ids),
                Image.status == "stored",
                AnalysisJob.status == "completed",
                AnalysisJob.model_version == get_settings().analysis_model_version,
            )
            .group_by(Image.project_id)
        ).all()
    )
    not_sent = dict(
        db.execute(
            select(Image.project_id, func.count())
            .where(
                Image.project_id.in_(project_ids),
                Image.status == "stored",
                ~exists().where(
                    AnalysisJob.image_id == Image.id,
                    AnalysisJob.model_version == get_settings().analysis_model_version,
                ),
            )
            .group_by(Image.project_id)
        ).all()
    )
    to_review = dict(
        db.execute(
            select(Finding.project_id, func.count())
            .where(
                Finding.project_id.in_(project_ids),
                Finding.review_status.in_(("ai_generated", "awaiting_review")),
            )
            .group_by(Finding.project_id)
        ).all()
    )
    by_status: dict[tuple[uuid.UUID, str], int] = {
        (pid, status): int(n)
        for pid, status, n in db.execute(
            select(Finding.project_id, Finding.review_status, func.count())
            .where(Finding.project_id.in_(project_ids))
            .group_by(Finding.project_id, Finding.review_status)
        ).all()
    }
    verified = Finding.review_status == "verified"
    unconfirmed = dict(
        db.execute(
            select(Finding.project_id, func.count())
            .where(
                Finding.project_id.in_(project_ids),
                verified,
                Finding.location_quality != "reviewer_confirmed",
            )
            .group_by(Finding.project_id)
        ).all()
    )
    by_type: dict[uuid.UUID, dict[str, int]] = {}
    for pid, type_key, n in db.execute(
        select(Finding.project_id, Finding.type_key, func.count())
        .where(Finding.project_id.in_(project_ids), verified)
        .group_by(Finding.project_id, Finding.type_key)
    ).all():
        by_type.setdefault(pid, {})[type_key or "unknown"] = int(n)
    open_inspections = dict(
        db.execute(
            select(Finding.project_id, func.count())
            .join(Inspection, Inspection.finding_id == Finding.id)
            .where(
                Finding.project_id.in_(project_ids),
                Inspection.status.in_(ACTIVE_INSPECTION_STATES),
            )
            .group_by(Finding.project_id)
        ).all()
    )
    result = {}
    for pid in project_ids:
        base = counts.get(pid, Counts(0, 0, 0))
        base.images_analysed = int(analysed.get(pid, 0))
        base.images_waiting_for_ai = int(not_sent.get(pid, 0))
        base.findings_to_review = int(to_review.get(pid, 0))
        base.findings_needs_field_check = by_status.get((pid, "needs_field_check"), 0)
        base.findings_verified = by_status.get((pid, "verified"), 0)
        base.verified_location_unconfirmed = int(unconfirmed.get(pid, 0))
        base.verified_by_type = by_type.get(pid, {})
        base.inspections_open = int(open_inspections.get(pid, 0))
        result[pid] = base
    return result


def visible_projects(
    db: Session, user: User, org_ctx: OrgContext, *, include_archived: bool
) -> list[tuple[Project, list[str]]]:
    """Projects the user can see in this organization, with the user's roles on each."""
    query = select(Project).where(Project.organization_id == org_ctx.organization.id)
    if org_ctx.membership.org_role != "org_admin":
        query = query.where(
            Project.id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id == user.id))
        )
    if not include_archived:
        query = query.where(Project.archived_at.is_(None))
    projects = list(
        db.scalars(query.order_by(Project.archived_at.is_not(None), Project.name)).all()
    )
    roles: dict[uuid.UUID, list[str]] = {}
    for project_id, role in db.execute(
        select(ProjectMember.project_id, ProjectMember.role).where(
            ProjectMember.user_id == user.id,
            ProjectMember.project_id.in_([p.id for p in projects]),
        )
    ).all():
        roles.setdefault(project_id, []).append(role)
    return [(project, sorted(roles.get(project.id, []))) for project in projects]


def boundary_geojson(db: Session, project_id: uuid.UUID) -> dict[str, Any]:
    raw = db.scalar(select(func.ST_AsGeoJSON(Project.boundary, 7)).where(Project.id == project_id))
    result: dict[str, Any] = json.loads(raw) if raw else {}
    return result


# --------------------------------------------------------------------- project team
def list_project_members(db: Session, project_id: uuid.UUID) -> list[tuple[ProjectMember, User]]:
    rows = db.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(User.full_name, ProjectMember.role)
    ).all()
    return [(member, user) for member, user in rows]


def eligible_members(db: Session, organization_id: uuid.UUID) -> list[tuple[User, str]]:
    rows = db.execute(
        select(User, OrganizationMembership.org_role)
        .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
        .where(OrganizationMembership.organization_id == organization_id, User.is_active.is_(True))
        .order_by(User.full_name)
    ).all()
    return [(user, role) for user, role in rows]


def add_project_member(
    db: Session, ctx: ProjectContext, user_id: uuid.UUID, role: str
) -> ProjectMember:
    """Give an organization member a role on this project. Adding an existing role
    returns it unchanged, so a repeated click is harmless."""
    ensure_not_archived(ctx)
    _check_org_members(db, ctx.project.organization_id, [user_id])
    existing = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == ctx.project.id,
            ProjectMember.user_id == user_id,
            ProjectMember.role == role,
        )
    )
    if existing:
        return existing
    member = ProjectMember(
        project_id=ctx.project.id, user_id=user_id, role=role, added_by=ctx.user.id
    )
    db.add(member)
    db.flush()
    record_event(
        db,
        action="project_member.added",
        organization_id=ctx.project.organization_id,
        project_id=ctx.project.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="user",
        target_id=user_id,
        details={"role": role},
    )
    return member


def remove_project_member(db: Session, ctx: ProjectContext, member_id: uuid.UUID) -> None:
    """Remove one role from a person. The last project manager cannot be removed."""
    ensure_not_archived(ctx)
    member = db.scalar(
        select(ProjectMember)
        .where(ProjectMember.id == member_id, ProjectMember.project_id == ctx.project.id)
        .with_for_update()
    )
    if member is None:
        raise NotFoundError("Team member not found.")
    if member.role == "project_manager":
        managers = db.scalars(
            select(ProjectMember.id)
            .where(
                ProjectMember.project_id == ctx.project.id, ProjectMember.role == "project_manager"
            )
            .with_for_update()
        ).all()
        if len(managers) <= 1:
            raise ConflictError(
                "A project must keep at least one project manager. Add another manager first."
            )
    db.delete(member)
    record_event(
        db,
        action="project_member.removed",
        organization_id=ctx.project.organization_id,
        project_id=ctx.project.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="user",
        target_id=member.user_id,
        details={"role": member.role},
    )


def remove_user_from_org_projects(
    db: Session, organization_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Used when someone leaves the organization: their project roles there end too."""
    db.execute(
        delete(ProjectMember).where(
            ProjectMember.user_id == user_id,
            ProjectMember.project_id.in_(
                select(Project.id).where(Project.organization_id == organization_id)
            ),
        )
    )
