"""Findings: listing with filters, review decisions, manual observations, history (P5-P6).

Rules (FR-25 to FR-38):
- Who sees what is decided here: unreviewed AI suggestions only for roles allowed to see
  them; rejected ones only when asked for.
- The AI's original answer and the original location are never changed (a database
  trigger also refuses). Reviewer changes go into their own columns.
- Every review action is stored in `review_events` with before/after values.
- Each finding has a version number. A save based on an old version is refused with 409,
  so nobody's work is silently overwritten.
- Verify needs a type and a severity chosen by a person. AI confidence is never severity.
"""

import logging
import uuid
from datetime import datetime, time, timedelta
from typing import Any

from geoalchemy2 import WKBElement
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.ai.registry import is_stand_in, is_trial
from app.core.auth import ProjectContext
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from app.core.permissions import Perm
from app.models import Finding, FindingImage, FindingType, Image, ReviewEvent, SeverityRubric, User
from app.models.base import utc_now
from app.schemas.findings import (
    FindingFilters,
    FindingOut,
    FindingPhoto,
    FindingTypeOption,
    ManualFindingCreate,
    ReviewEventOut,
    ReviewOptions,
    ReviewRequest,
    SeverityLevel,
    SeverityRubricOut,
)
from app.schemas.images import LatLon
from app.services.projects import ensure_not_archived

log = logging.getLogger(__name__)

CANDIDATE_STATUSES = ("ai_generated", "awaiting_review", "needs_field_check")
DECISION_STATUS = {
    "verify": "verified",
    "reject": "rejected",
    "needs_field_check": "needs_field_check",
}
MAP_LIMIT = 5000

STALE_MESSAGE = "This finding was changed by someone else. Reload to see the latest version."


def _point(location: LatLon) -> Any:
    return func.ST_SetSRID(func.ST_MakePoint(location.longitude, location.latitude), 4326)


# The location to show: the reviewer's corrected point if any, otherwise the original.
EFFECTIVE_LOCATION = func.coalesce(Finding.corrected_location, Finding.original_location)
# The type to filter on: the reviewer's type if chosen, otherwise the AI's suggestion.
EFFECTIVE_TYPE = func.coalesce(Finding.type_key, Finding.predicted_type_key)


# ----------------------------------------------------------------- who may see what
def visible_statuses(ctx: ProjectContext, include_rejected: bool) -> list[str]:
    statuses: list[str] = []
    if ctx.has(Perm.FINDING_VIEW_VERIFIED):
        statuses.append("verified")
    if ctx.has(Perm.FINDING_VIEW_CANDIDATES):
        statuses.extend(CANDIDATE_STATUSES)
    if include_rejected and ctx.has(Perm.FINDING_VIEW_REJECTED):
        statuses.append("rejected")
    return statuses


def get_visible_finding(db: Session, ctx: ProjectContext, finding_id: uuid.UUID) -> Finding:
    finding = db.scalar(
        select(Finding).where(Finding.id == finding_id, Finding.project_id == ctx.project.id)
    )
    if finding is None:
        raise NotFoundError("Finding not found.")
    # Findings this person may not see are "not found", so their existence is not revealed.
    if finding.review_status not in visible_statuses(ctx, include_rejected=True):
        raise NotFoundError("Finding not found.")
    return finding


def _filtered(ctx: ProjectContext, filters: FindingFilters) -> Select[Finding] | None:
    """The query for findings this person may see that match the filters (None = nothing)."""
    include_rejected = filters.include_rejected or "rejected" in filters.review_status
    statuses = visible_statuses(ctx, include_rejected)
    if filters.review_status:
        statuses = [s for s in statuses if s in filters.review_status]
    if not statuses:
        return None
    return filtered_query(ctx.project.id, statuses, filters)


def filtered_query(
    project_id: uuid.UUID, statuses: list[str], filters: FindingFilters
) -> Select[Finding]:
    """Findings of a project with these statuses that match the filters. Used by the list,
    the map and the exports, so they always agree (FR-26, FR-47)."""
    query = select(Finding).where(
        Finding.project_id == project_id, Finding.review_status.in_(statuses)
    )
    if filters.type_key:
        query = query.where(EFFECTIVE_TYPE.in_(filters.type_key))
    if filters.severity_key:
        query = query.where(Finding.severity_key.in_(filters.severity_key))
    if filters.created_from:
        query = query.where(Finding.created_at >= datetime.combine(filters.created_from, time.min))
    if filters.created_to:
        end = datetime.combine(filters.created_to + timedelta(days=1), time.min)
        query = query.where(Finding.created_at < end)
    if filters.has_location is True:
        query = query.where(EFFECTIVE_LOCATION.is_not(None))
    elif filters.has_location is False:
        query = query.where(EFFECTIVE_LOCATION.is_(None))
    if filters.image_id is not None:
        query = query.where(
            Finding.id.in_(
                select(FindingImage.finding_id).where(FindingImage.image_id == filters.image_id)
            )
        )
    return query


def list_findings(
    db: Session, ctx: ProjectContext, filters: FindingFilters, *, page: int, page_size: int
) -> tuple[list[Finding], int]:
    query = _filtered(ctx, filters)
    if query is None:
        return [], 0
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    findings = db.scalars(
        query.order_by(Finding.created_at.desc(), Finding.detection_index, Finding.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(findings), int(total)


def findings_geojson(db: Session, ctx: ProjectContext, filters: FindingFilters) -> dict[str, Any]:
    """The same findings as the list, as map points (only those with a location)."""
    query = _filtered(ctx, filters)
    features: list[dict[str, Any]] = []
    total_located = 0
    if query is not None:
        located = query.where(EFFECTIVE_LOCATION.is_not(None)).subquery()
        total_located = int(db.scalar(select(func.count()).select_from(located)) or 0)
        rows = db.execute(
            select(
                located.c.id,
                located.c.review_status,
                func.coalesce(located.c.type_key, located.c.predicted_type_key),
                located.c.severity_key,
                located.c.origin,
                func.ST_X(func.coalesce(located.c.corrected_location, located.c.original_location)),
                func.ST_Y(func.coalesce(located.c.corrected_location, located.c.original_location)),
            )
            .order_by(located.c.created_at.desc(), located.c.id)
            .limit(MAP_LIMIT)
        ).all()
        features = [
            {
                "type": "Feature",
                "id": str(row[0]),
                "geometry": {"type": "Point", "coordinates": [row[5], row[6]]},
                "properties": {
                    "id": str(row[0]),
                    "review_status": row[1],
                    "type_key": row[2],
                    "severity_key": row[3],
                    "origin": row[4],
                },
            }
            for row in rows
        ]
    return {
        "type": "FeatureCollection",
        "features": features,
        # More than MAP_LIMIT located findings: the map shows the newest ones only.
        "truncated": total_located > len(features),
    }


# ----------------------------------------------------------------- output
def _names(db: Session, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not user_ids:
        return {}
    return {
        user_id: name
        for user_id, name in db.execute(
            select(User.id, User.full_name).where(User.id.in_(user_ids))
        ).all()
    }


def _coordinates(db: Session, column: Any, ids: list[uuid.UUID]) -> dict[uuid.UUID, LatLon]:
    return {
        finding_id: LatLon(latitude=lat, longitude=lon)
        for finding_id, lat, lon in db.execute(
            select(Finding.id, func.ST_Y(column), func.ST_X(column)).where(
                Finding.id.in_(ids), column.is_not(None)
            )
        ).all()
    }


def to_out(db: Session, findings: list[Finding]) -> list[FindingOut]:
    if not findings:
        return []
    ids = [f.id for f in findings]
    originals = _coordinates(db, Finding.original_location, ids)
    corrected = _coordinates(db, Finding.corrected_location, ids)
    photos = {
        finding_id: FindingPhoto(
            id=image.id,
            original_filename=image.original_filename,
            width_px=image.width_px,
            height_px=image.height_px,
        )
        for finding_id, image in db.execute(
            select(FindingImage.finding_id, Image)
            .join(Image, Image.id == FindingImage.image_id)
            .where(FindingImage.finding_id.in_(ids), FindingImage.is_primary.is_(True))
        ).all()
    }
    rubric_ids = {f.severity_rubric_id for f in findings if f.severity_rubric_id}
    rubric_versions = (
        dict(
            db.execute(
                select(SeverityRubric.id, SeverityRubric.version).where(
                    SeverityRubric.id.in_(rubric_ids)
                )
            ).all()
        )
        if rubric_ids
        else {}
    )
    names = _names(db, {u for f in findings for u in (f.reviewed_by, f.created_by) if u})
    return [
        FindingOut(
            id=f.id,
            project_id=f.project_id,
            origin=f.origin,
            review_status=f.review_status,
            inspection_status=f.inspection_status,
            predicted_type_key=f.predicted_type_key,
            predicted_confidence=(
                float(f.predicted_confidence) if f.predicted_confidence is not None else None
            ),
            predicted_bbox=f.predicted_bbox,
            model_version=f.model_version,
            is_test_detector=bool(f.model_version and is_stand_in(f.model_version)),
            is_trial_model=bool(f.model_version and is_trial(f.model_version)),
            analysis_job_id=f.analysis_job_id,
            type_key=f.type_key,
            severity_key=f.severity_key,
            severity_rubric_id=f.severity_rubric_id,
            severity_rubric_version=rubric_versions.get(f.severity_rubric_id)
            if f.severity_rubric_id
            else None,
            notes=f.notes,
            reviewed_by_name=names.get(f.reviewed_by) if f.reviewed_by else None,
            reviewed_at=f.reviewed_at,
            created_by_name=names.get(f.created_by) if f.created_by else None,
            location=corrected.get(f.id) or originals.get(f.id),
            original_location=originals.get(f.id),
            corrected_location=corrected.get(f.id),
            location_source=f.location_source,
            location_quality=f.location_quality,
            photo=photos.get(f.id),
            version=f.version,
            created_at=f.created_at,
            updated_at=f.updated_at,
        )
        for f in findings
    ]


# ----------------------------------------------------------------- settings used by review
def _active_type(db: Session, ctx: ProjectContext, key: str) -> FindingType:
    finding_type = db.scalar(
        select(FindingType).where(
            FindingType.organization_id == ctx.project.organization_id, FindingType.key == key
        )
    )
    if finding_type is None or not finding_type.is_active:
        raise ValidationFailedError(
            "Choose one of the organization's finding types.", details={"type_key": key}
        )
    return finding_type


def current_rubric(db: Session, organization_id: uuid.UUID) -> SeverityRubric:
    rubric = db.scalar(
        select(SeverityRubric).where(
            SeverityRubric.organization_id == organization_id,
            SeverityRubric.is_current.is_(True),
        )
    )
    if rubric is None:  # every organization gets rubric v1 when it is created
        raise ConflictError("This organization has no severity scale yet.")
    return rubric


def rubric_out(rubric: SeverityRubric) -> SeverityRubricOut:
    return SeverityRubricOut(
        id=rubric.id,
        version=rubric.version,
        levels=[SeverityLevel(**level) for level in rubric.levels],
        is_placeholder=rubric.is_placeholder,
        is_current=rubric.is_current,
        created_at=rubric.created_at,
    )


def review_options(db: Session, ctx: ProjectContext) -> ReviewOptions:
    types = db.scalars(
        select(FindingType)
        .where(
            FindingType.organization_id == ctx.project.organization_id,
            FindingType.is_active.is_(True),
        )
        .order_by(FindingType.source, FindingType.label)
    ).all()
    chosen = set(ctx.project.finding_type_keys or [])
    return ReviewOptions(
        finding_types=[
            FindingTypeOption(
                key=t.key,
                label=t.label,
                source=t.source,
                is_placeholder=t.is_placeholder,
                in_project=t.key in chosen,
            )
            for t in types
        ],
        severity_rubric=rubric_out(current_rubric(db, ctx.project.organization_id)),
    )


# ----------------------------------------------------------------- review
def _location_text(db: Session, value: Any) -> list[float] | None:
    """A point as [longitude, latitude] for the history (None when empty)."""
    if value is None:
        return None
    if isinstance(value, WKBElement):
        row = db.execute(select(func.ST_X(value), func.ST_Y(value))).one()
        return [round(float(row[0]), 7), round(float(row[1]), 7)]
    return None


def _snapshot(db: Session, finding: Finding) -> dict[str, Any]:
    return {
        "review_status": finding.review_status,
        "type_key": finding.type_key,
        "severity_key": finding.severity_key,
        "severity_rubric_id": str(finding.severity_rubric_id)
        if finding.severity_rubric_id
        else None,
        "notes": finding.notes,
        "corrected_location": _location_text(db, finding.corrected_location),
        "location_quality": finding.location_quality,
    }


def _record(
    db: Session,
    ctx: ProjectContext,
    finding: Finding,
    *,
    action: str,
    changes: dict[str, Any],
    note: str | None,
) -> None:
    db.add(
        ReviewEvent(
            finding_id=finding.id,
            actor_user_id=ctx.user.id,
            actor_roles=ctx.actor_roles,
            action=action,
            changes=changes,
            note=note,
            finding_version=finding.version,
        )
    )


def review(db: Session, ctx: ProjectContext, finding_id: uuid.UUID, body: ReviewRequest) -> Finding:
    """Apply one review action. Commits. Raises 409 if the finding changed meanwhile."""
    if not ctx.has(Perm.FINDING_REVIEW):
        raise PermissionDeniedError()
    ensure_not_archived(ctx)
    # Lock the row so two saves at the same moment are handled one after the other.
    finding = db.scalar(
        select(Finding)
        .where(Finding.id == finding_id, Finding.project_id == ctx.project.id)
        .with_for_update()
        # Read the locked row fresh: the request may already hold an older copy of this
        # finding, and the version check must use what is in the database right now.
        .execution_options(populate_existing=True)
    )
    if finding is None or finding.review_status not in visible_statuses(ctx, True):
        raise NotFoundError("Finding not found.")
    if finding.version != body.version:
        raise ConflictError(STALE_MESSAGE, details={"current_version": finding.version})
    if finding.review_status == "merged":
        raise ConflictError("This finding was merged into another one and cannot be reviewed.")

    before = _snapshot(db, finding)
    sent = body.model_fields_set

    if "type_key" in sent:
        if body.type_key is None:
            raise ValidationFailedError("Choose a finding type.")
        finding.type_key = _active_type(db, ctx, body.type_key).key
    if "severity_key" in sent:
        if body.severity_key is None:
            raise ValidationFailedError("Choose a severity.")
        rubric = current_rubric(db, ctx.project.organization_id)
        if body.severity_key not in {level["key"] for level in rubric.levels}:
            raise ValidationFailedError(
                "Choose a severity from the current scale.",
                details={"severity_key": body.severity_key},
            )
        if body.severity_key != finding.severity_key or finding.severity_rubric_id != rubric.id:
            finding.severity_key = body.severity_key
            finding.severity_rubric_id = rubric.id
    if "notes" in sent:
        finding.notes = (body.notes or "").strip() or None
    if "corrected_location" in sent:
        if body.corrected_location is None:
            finding.corrected_location = None
            finding.location_quality = (
                "approximate" if finding.original_location is not None else "missing"
            )
        else:
            finding.corrected_location = _point(body.corrected_location)
            finding.location_quality = "reviewer_confirmed"

    if body.action in DECISION_STATUS:
        new_status = DECISION_STATUS[body.action]
        if new_status == "verified" and not (finding.type_key and finding.severity_key):
            raise ValidationFailedError(
                "Choose a type and a severity before verifying.",
                details={
                    "missing": [k for k in ("type_key", "severity_key") if not getattr(finding, k)]
                },
            )
        if new_status != "verified" and finding.inspection_status != "none":
            raise ConflictError("This finding already has an inspection, so it must stay verified.")
        finding.review_status = new_status

    db.flush()
    after = _snapshot(db, finding)
    changes = {k: {"old": before[k], "new": after[k]} for k in before if before[k] != after[k]}
    if body.action == "edit" and not changes:
        raise ValidationFailedError("Nothing was changed.")

    finding.version += 1
    finding.reviewed_by = ctx.user.id
    finding.reviewed_at = utc_now()
    _record(
        db,
        ctx,
        finding,
        action=body.action,
        changes=changes,
        note=(body.reason or "").strip() or None,
    )
    db.commit()
    db.refresh(finding)
    log.info(
        "Finding reviewed: finding=%s action=%s status=%s version=%s",
        finding.id,
        body.action,
        finding.review_status,
        finding.version,
    )
    return finding


# ----------------------------------------------------------------- manual observations
def create_manual(db: Session, ctx: ProjectContext, body: ManualFindingCreate) -> Finding:
    """Add a problem seen by a person (e.g. on a sidewalk). It waits for review like AI ones."""
    ensure_not_archived(ctx)
    finding_type = _active_type(db, ctx, body.type_key)

    image: Image | None = None
    if body.image_id is not None:
        image = db.scalar(
            select(Image).where(
                Image.id == body.image_id,
                Image.project_id == ctx.project.id,
                Image.status == "stored",
            )
        )
        # People with limited photo access (collectors) may attach only their own photos.
        allowed = image is not None and (
            ctx.is_unconditional(Perm.IMAGE_VIEW) or image.uploaded_by == ctx.user.id
        )
        if image is None or not allowed:
            raise NotFoundError("Photo not found.")

    finding = Finding(
        project_id=ctx.project.id,
        origin="manual",
        type_key=finding_type.key,
        notes=body.notes,
        review_status="awaiting_review",
        created_by=ctx.user.id,
        location_source="none",
        location_quality="missing",
    )
    if body.location is not None:
        finding.original_location = _point(body.location)
        finding.location_source = "manual"
        finding.location_quality = "approximate"
    elif image is not None and image.original_location is not None:
        finding.original_location = image.original_location
        finding.location_source = image.location_source
        finding.location_quality = "approximate"
    db.add(finding)
    db.flush()
    if image is not None:
        db.add(FindingImage(finding_id=finding.id, image_id=image.id, is_primary=True))
    _record(
        db,
        ctx,
        finding,
        action="create",
        changes={
            "type_key": {"old": None, "new": finding.type_key},
            "notes": {"old": None, "new": finding.notes},
            "location_source": {"old": None, "new": finding.location_source},
        },
        note=None,
    )
    db.commit()
    db.refresh(finding)
    log.info("Manual finding added: finding=%s type=%s", finding.id, finding.type_key)
    return finding


# ----------------------------------------------------------------- history
def history(db: Session, ctx: ProjectContext, finding: Finding) -> list[ReviewEventOut]:
    if not ctx.has(Perm.FINDING_HISTORY_VIEW):
        raise PermissionDeniedError()
    events = db.scalars(
        select(ReviewEvent)
        .where(ReviewEvent.finding_id == finding.id)
        .order_by(ReviewEvent.created_at, ReviewEvent.finding_version)
    ).all()
    names = _names(db, {event.actor_user_id for event in events})
    return [
        ReviewEventOut(
            id=event.id,
            action=event.action,
            actor_name=names.get(event.actor_user_id),
            actor_roles=list(event.actor_roles),
            changes=event.changes,
            note=event.note,
            finding_version=event.finding_version,
            created_at=event.created_at,
        )
        for event in events
    ]
