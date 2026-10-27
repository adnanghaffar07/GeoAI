"""Inspections of verified findings (FR-43, FR-44).

- A manager plans an inspection: owner (a project member) and date.
- The owner or a manager marks it inspected, or resolved with a note or a photo.
- A resolved inspection can be reopened: the old one is kept (status "reopened", with the
  reason) and a new one is planned. Nothing is deleted.
- The finding's `inspection_status` always mirrors its newest inspection.
"""

import io
import logging
import uuid
from typing import BinaryIO

from PIL import Image as PillowImage
from PIL import UnidentifiedImageError
from sqlalchemy import select
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
from app.models import Finding, Inspection, ProjectMember, User
from app.models.base import utc_now
from app.models.priority import ACTIVE_INSPECTION_STATES
from app.schemas.priority import InspectionOut, InspectionPlan, InspectionReopen, InspectionUpdate
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
        details={"finding_id": str(inspection.finding_id), **details},
    )


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
    finding: Finding,
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
    finding.inspection_status = body.status
    _audit(db, ctx, f"inspection.{body.status}", inspection, note=note)
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
    finding: Finding,
    inspection_id: uuid.UUID,
    body: InspectionReopen,
) -> Inspection:
    """Reopen a resolved inspection: the old one is kept, a new one is planned."""
    if not ctx.has(Perm.INSPECTION_REOPEN):
        raise PermissionDeniedError()
    ensure_not_archived(ctx)
    finding = _lock_finding(db, finding)
    old = _locked(db, inspection_id)
    if old.status != "resolved":
        raise ConflictError("Only a resolved inspection can be reopened.")
    newest = history(db, finding.id)[-1]
    if newest.id != old.id or open_inspection(db, finding.id) is not None:
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
        finding_id=old.finding_id,
        owner_user_id=body.owner_user_id,
        planned_date=body.planned_date,
        status="planned",
        created_by=ctx.user.id,
    )
    db.add(new)
    finding.inspection_status = "planned"
    db.flush()
    _audit(db, ctx, "inspection.reopened", old, reason=body.reason, new_inspection_id=str(new.id))
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
            finding_id=item.finding_id,
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
