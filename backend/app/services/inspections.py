"""Inspections of verified findings (FR-43, FR-44) and of road sections (F4d).

- A manager plans an inspection: owner (a project member) and date.
- The owner or a manager marks it inspected, or resolved with a note or a photo.
- A resolved inspection can be reopened: the old one is kept (status "reopened", with the
  reason) and a new one is planned. Nothing is deleted.
- The finding's `inspection_status` always mirrors its newest inspection.
- F4d (owner request 2026-10-30): a manager can also plan an inspection of a road section from
  the road-risk screens, with no finding. It follows the same steps; it is linked to the risk
  level that suggested it, so inspection outcomes can later check the forecast.
"""

import io
import logging
import uuid
from typing import BinaryIO

from PIL import Image as PillowImage
from PIL import UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import storage
from app.core.auth import ProjectContext
from app.core.config import get_settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    PermissionDeniedError,
    UnsupportedMediaTypeError,
    ValidationFailedError,
)
from app.core.permissions import Perm, project_permissions
from app.models import Alert, Finding, ForecastSection, Inspection, ProjectMember, User
from app.models.base import utc_now
from app.models.priority import ACTIVE_INSPECTION_STATES
from app.schemas.priority import (
    InspectionOut,
    InspectionPlan,
    InspectionReopen,
    InspectionUpdate,
    RoadOut,
)
from app.services.audit import record_event
from app.services.projects import ensure_not_archived

log = logging.getLogger(__name__)

EVIDENCE_TYPES = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png")}


def _audit(
    db: Session, ctx: ProjectContext, action: str, inspection: Inspection, **details: object
) -> None:
    record_event(
        db,
        action=action,
        organization_id=ctx.project.organization_id,
        project_id=ctx.project.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="inspection",
        target_id=inspection.id,
        details={**_subject(inspection), **details},
    )


def _notify_owner(db: Session, ctx: ProjectContext, inspection: Inspection) -> None:
    """Personal bell notification for the person asked to inspect (owner request 2026-11-03).
    Not sent when people plan an inspection for themselves."""
    if inspection.owner_user_id == ctx.user.id:
        return
    if inspection.section_id is not None:
        road = db.get(ForecastSection, inspection.section_id)
        what = f"the road {road.name or 'Unnamed road'}" if road else "a road"
    else:
        finding = db.get(Finding, inspection.finding_id)
        what = f"a {finding.type_key or 'finding'}".replace("_", " ") if finding else "a finding"
    day = inspection.planned_date.strftime("%A %d %B").replace(" 0", " ")
    db.add(
        Alert(
            project_id=ctx.project.id,
            user_id=inspection.owner_user_id,
            type="inspection_assigned",
            event_key=f"inspection_assigned:{inspection.id}",
            title=f"You have been asked to inspect {what} by {day}",
            details={
                "when": f"Planned for {day}",
                "suggested_action": "Open My inspections (or Priority) to record what you find.",
                "path": f"/projects/{ctx.project.id}/priority",
                "inspection_id": str(inspection.id),
                "planned_by": ctx.user.full_name,
                "project_name": ctx.project.name,
            },
        )
    )


def _close_notice(db: Session, inspection: Inspection) -> None:
    for alert in db.scalars(
        select(Alert).where(
            Alert.event_key == f"inspection_assigned:{inspection.id}", Alert.closed_at.is_(None)
        )
    ):
        alert.closed_at = utc_now()


def _subject(inspection: Inspection) -> dict[str, str]:
    if inspection.section_id is not None:
        return {"section_id": str(inspection.section_id)}
    return {"finding_id": str(inspection.finding_id)}


def _check_owner(db: Session, ctx: ProjectContext, owner_id: uuid.UUID) -> None:
    """The owner must be on the project with a role that can record inspections
    (manager, technical reviewer or field collector; not a viewer)."""
    roles = db.scalars(
        select(ProjectMember.role).where(
            ProjectMember.project_id == ctx.project.id, ProjectMember.user_id == owner_id
        )
    ).all()
    if Perm.INSPECTION_RECORD not in project_permissions(roles, None):
        raise ValidationFailedError(
            "The inspection owner must be a project member who can record inspections "
            "(project manager, technical reviewer or field collector).",
            details={"owner_user_id": str(owner_id)},
        )


def open_inspection(db: Session, finding_id: uuid.UUID) -> Inspection | None:
    return db.scalar(
        select(Inspection).where(
            Inspection.finding_id == finding_id, Inspection.status.in_(ACTIVE_INSPECTION_STATES)
        )
    )


def open_road_inspection(
    db: Session, project_id: uuid.UUID, section_id: uuid.UUID
) -> Inspection | None:
    return db.scalar(
        select(Inspection).where(
            Inspection.project_id == project_id,
            Inspection.section_id == section_id,
            Inspection.status.in_(ACTIVE_INSPECTION_STATES),
        )
    )


def latest_inspections(db: Session, finding_ids: list[uuid.UUID]) -> dict[uuid.UUID, Inspection]:
    """The newest inspection of each finding."""
    latest: dict[uuid.UUID, Inspection] = {}
    if not finding_ids:
        return latest
    for inspection in db.scalars(
        select(Inspection)
        .where(Inspection.finding_id.in_(finding_ids))
        .order_by(Inspection.created_at, Inspection.id)
    ):
        latest[inspection.finding_id] = inspection
    return latest


def _lock_finding(db: Session, finding: Finding) -> Finding:
    """Lock the finding so two people planning at the same moment are handled in turn."""
    locked = db.scalar(
        select(Finding)
        .where(Finding.id == finding.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None:
        raise NotFoundError("Finding not found.")
    return locked


def plan(db: Session, ctx: ProjectContext, finding: Finding, body: InspectionPlan) -> Inspection:
    if not ctx.has(Perm.INSPECTION_PLAN):
        raise PermissionDeniedError()
    ensure_not_archived(ctx)
    finding = _lock_finding(db, finding)
    if finding.review_status != "verified":
        raise ConflictError("Only verified findings can be inspected.")
    if open_inspection(db, finding.id) is not None:
        raise ConflictError("This finding already has an open inspection.")
    _check_owner(db, ctx, body.owner_user_id)
    inspection = Inspection(
        project_id=ctx.project.id,
        finding_id=finding.id,
        owner_user_id=body.owner_user_id,
        planned_date=body.planned_date,
        status="planned",
        created_by=ctx.user.id,
    )
    db.add(inspection)
    finding.inspection_status = "planned"
    db.flush()
    _audit(
        db,
        ctx,
        "inspection.planned",
        inspection,
        owner_user_id=str(body.owner_user_id),
        planned_date=body.planned_date.isoformat(),
    )
    _notify_owner(db, ctx, inspection)
    db.commit()
    db.refresh(inspection)
    return inspection


def plan_road(
    db: Session,
    ctx: ProjectContext,
    section_id: uuid.UUID,
    risk_level_id: uuid.UUID | None,
    body: InspectionPlan,
) -> Inspection:
    """Plan an inspection of a road section (F4d). The caller checks the section is in it."""
    if not ctx.has(Perm.INSPECTION_PLAN):
        raise PermissionDeniedError()
    ensure_not_archived(ctx)
    if open_road_inspection(db, ctx.project.id, section_id) is not None:
        raise ConflictError("This road already has an open inspection.")
    _check_owner(db, ctx, body.owner_user_id)
    inspection = Inspection(
        project_id=ctx.project.id,
        section_id=section_id,
        risk_level_id=risk_level_id,
        owner_user_id=body.owner_user_id,
        planned_date=body.planned_date,
        status="planned",
        created_by=ctx.user.id,
    )
    db.add(inspection)
    try:
        db.flush()
    except IntegrityError as exc:  # someone planned the same road at the same moment
        db.rollback()
        raise ConflictError("This road already has an open inspection.") from exc
    _audit(
        db,
        ctx,
        "inspection.planned",
        inspection,
        owner_user_id=str(body.owner_user_id),
        planned_date=body.planned_date.isoformat(),
    )
    _notify_owner(db, ctx, inspection)
    db.commit()
    db.refresh(inspection)
    return inspection


def can_record(ctx: ProjectContext, inspection: Inspection) -> bool:
    """Managers record any inspection; others only the ones assigned to them (Q7)."""
    if not ctx.has(Perm.INSPECTION_RECORD):
        return False
    return ctx.is_unconditional(Perm.INSPECTION_RECORD) or inspection.owner_user_id == ctx.user.id


def _locked(db: Session, inspection_id: uuid.UUID) -> Inspection:
    inspection = db.scalar(
        select(Inspection)
        .where(Inspection.id == inspection_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if inspection is None:
        raise NotFoundError("Inspection not found.")
    return inspection


def record(
    db: Session,
    ctx: ProjectContext,
    finding: Finding | None,
    inspection_id: uuid.UUID,
    body: InspectionUpdate,
) -> Inspection:
    ensure_not_archived(ctx)
    inspection = _locked(db, inspection_id)
    if not can_record(ctx, inspection):
        raise PermissionDeniedError()
    if inspection.status not in ACTIVE_INSPECTION_STATES:
        raise ConflictError("This inspection is already closed. Reopen it to record again.")
    if body.status == "inspected" and inspection.status != "planned":
        raise ConflictError("This inspection is already marked inspected.")
    note = (body.outcome_note or "").strip() or None
    if note is not None:
        inspection.outcome_note = note
    now = utc_now()
    if body.status == "resolved":
        if inspection.outcome_note is None and inspection.evidence_storage_key is None:
            raise ValidationFailedError("To mark it resolved, add a note or a photo of the result.")
        inspection.resolved_by = ctx.user.id
        inspection.resolved_at = now
    else:
        inspection.inspected_by = ctx.user.id
        inspection.inspected_at = now
    inspection.status = body.status
    if finding is not None:
        finding.inspection_status = body.status
    _audit(db, ctx, f"inspection.{body.status}", inspection, note=note)
    if body.status == "resolved":
        _close_notice(db, inspection)
    db.commit()
    db.refresh(inspection)
    return inspection


def add_evidence(
    db: Session, ctx: ProjectContext, inspection_id: uuid.UUID, upload: BinaryIO
) -> Inspection:
    """Store a photo of the result (JPEG or PNG) in private storage."""
    ensure_not_archived(ctx)
    inspection = _locked(db, inspection_id)
    if not can_record(ctx, inspection):
        raise PermissionDeniedError()
    if inspection.status not in ACTIVE_INSPECTION_STATES:
        raise ConflictError("This inspection is already closed.")
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = upload.read(limit + 1)
    if len(data) > limit:
        raise PayloadTooLargeError(f"The file is larger than {get_settings().max_upload_mb} MB.")
    try:
        with PillowImage.open(io.BytesIO(data)) as photo:
            photo_format = photo.format or ""
            photo.verify()
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        PillowImage.DecompressionBombError,
    ) as exc:
        raise UnsupportedMediaTypeError("Only JPEG and PNG photos can be attached.") from exc
    if photo_format not in EVIDENCE_TYPES:
        raise UnsupportedMediaTypeError("Only JPEG and PNG photos can be attached.")
    content_type, extension = EVIDENCE_TYPES[photo_format]
    key = (
        f"org/{ctx.project.organization_id}/project/{ctx.project.id}/inspection/"
        f"{inspection.id}/evidence-{uuid.uuid4().hex[:8]}.{extension}"
    )
    storage.save_bytes(key, data)
    inspection.evidence_storage_key = key
    inspection.evidence_content_type = content_type
    _audit(db, ctx, "inspection.evidence_added", inspection, size_bytes=len(data))
    db.commit()
    db.refresh(inspection)
    return inspection


def reopen(
    db: Session,
    ctx: ProjectContext,
    finding: Finding | None,
    inspection_id: uuid.UUID,
    body: InspectionReopen,
) -> Inspection:
    """Reopen a resolved inspection: the old one is kept, a new one is planned."""
    if not ctx.has(Perm.INSPECTION_REOPEN):
        raise PermissionDeniedError()
    ensure_not_archived(ctx)
    if finding is not None:
        finding = _lock_finding(db, finding)
    old = _locked(db, inspection_id)
    if old.status != "resolved":
        raise ConflictError("Only a resolved inspection can be reopened.")
    newest = history_of(db, old)[-1]
    still_open = (
        open_inspection(db, finding.id)
        if finding is not None
        else open_road_inspection(db, old.project_id, old.section_id)  # type: ignore[arg-type]
    )
    if newest.id != old.id or still_open is not None:
        raise ConflictError(
            "Only the newest inspection can be reopened, and only when none is open."
        )
    _check_owner(db, ctx, body.owner_user_id)
    old.status = "reopened"
    old.reopen_reason = body.reason
    old.reopened_by = ctx.user.id
    old.reopened_at = utc_now()
    db.flush()
    new = Inspection(
        project_id=old.project_id,
        finding_id=old.finding_id,
        section_id=old.section_id,
        risk_level_id=old.risk_level_id,
        owner_user_id=body.owner_user_id,
        planned_date=body.planned_date,
        status="planned",
        created_by=ctx.user.id,
    )
    db.add(new)
    if finding is not None:
        finding.inspection_status = "planned"
    db.flush()
    _audit(db, ctx, "inspection.reopened", old, reason=body.reason, new_inspection_id=str(new.id))
    _close_notice(db, old)
    _notify_owner(db, ctx, new)
    db.commit()
    db.refresh(new)
    return new


def history(db: Session, finding_id: uuid.UUID) -> list[Inspection]:
    return list(
        db.scalars(
            select(Inspection)
            .where(Inspection.finding_id == finding_id)
            .order_by(Inspection.created_at, Inspection.id)
        )
    )


def road_history(db: Session, project_id: uuid.UUID, section_id: uuid.UUID) -> list[Inspection]:
    """All inspections of a road section in a project, oldest first (F4d)."""
    return list(
        db.scalars(
            select(Inspection)
            .where(Inspection.project_id == project_id, Inspection.section_id == section_id)
            .order_by(Inspection.created_at, Inspection.id)
        )
    )


def history_of(db: Session, inspection: Inspection) -> list[Inspection]:
    """All inspections of the same finding or road section, oldest first."""
    if inspection.finding_id is not None:
        return history(db, inspection.finding_id)
    return road_history(db, inspection.project_id, inspection.section_id)  # type: ignore[arg-type]


def roads_of(db: Session, inspections: list[Inspection]) -> dict[uuid.UUID, RoadOut]:
    """The road of each road inspection (name, type, length; never its risk level)."""
    ids = {i.section_id for i in inspections if i.section_id is not None}
    if not ids:
        return {}
    return {
        s.id: RoadOut(
            section_id=s.id, name=s.name, road_type=s.road_type, length_m=round(s.length_m, 1)
        )
        for s in db.scalars(select(ForecastSection).where(ForecastSection.id.in_(ids)))
    }


def to_out(db: Session, inspections: list[Inspection]) -> list[InspectionOut]:
    user_ids = {
        user_id
        for item in inspections
        for user_id in (
            item.owner_user_id,
            item.inspected_by,
            item.resolved_by,
            item.reopened_by,
            item.created_by,
        )
        if user_id
    }
    names = (
        dict(db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids))).all())
        if user_ids
        else {}
    )

    def name(user_id: uuid.UUID | None) -> str | None:
        return names.get(user_id) if user_id else None

    return [
        InspectionOut(
            id=item.id,
            project_id=item.project_id,
            finding_id=item.finding_id,
            section_id=item.section_id,
            owner_user_id=item.owner_user_id,
            owner_name=name(item.owner_user_id),
            planned_date=item.planned_date,
            status=item.status,
            outcome_note=item.outcome_note,
            has_evidence=item.evidence_storage_key is not None,
            inspected_by_name=name(item.inspected_by),
            inspected_at=item.inspected_at,
            resolved_by_name=name(item.resolved_by),
            resolved_at=item.resolved_at,
            reopen_reason=item.reopen_reason,
            reopened_by_name=name(item.reopened_by),
            reopened_at=item.reopened_at,
            created_by_name=name(item.created_by),
            created_at=item.created_at,
        )
        for item in inspections
    ]
