"""Findings, review, manual observations and history (api-spec.md section 3.7).

Every route goes through the project gatekeeper. What a person sees depends on their role:
unreviewed AI suggestions only for managers and reviewers; collectors and viewers see
verified findings only (decision Q5).
"""

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import (
    CurrentUser,
    ProjectContext,
    get_current_user,
    load_project_context,
    require_project_permission,
)
from app.core.database import get_db
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from app.core.permissions import Perm
from app.models import Finding
from app.models.analysis import REVIEW_STATUSES
from app.schemas.common import Page
from app.schemas.findings import (
    FindingFilters,
    FindingOut,
    ManualFindingCreate,
    ReviewEventOut,
    ReviewOptions,
    ReviewRequest,
)
from app.services import findings as service

project_router = APIRouter(prefix="/projects/{project_id}", tags=["findings"])
finding_router = APIRouter(prefix="/findings/{finding_id}", tags=["findings"])


def finding_filters(
    review_status: list[str] = Query(default=[], max_length=6),
    type_key: list[str] = Query(default=[], max_length=50),
    severity_key: list[str] = Query(default=[], max_length=20),
    created_from: date | None = None,
    created_to: date | None = None,
    has_location: bool | None = None,
    include_rejected: bool = False,
    image_id: uuid.UUID | None = None,
) -> FindingFilters:
    """Filters shared by the list and the map (FR-26), read from the address."""
    unknown = [value for value in review_status if value not in REVIEW_STATUSES]
    if unknown:
        raise ValidationFailedError("Unknown review status.", details={"review_status": unknown})
    return FindingFilters(
        review_status=review_status,
        type_key=type_key,
        severity_key=severity_key,
        created_from=created_from,
        created_to=created_to,
        has_location=has_location,
        include_rejected=include_rejected,
        image_id=image_id,
    )


@project_router.get("/findings", response_model=Page[FindingOut])
def list_findings(
    ctx: ProjectContext = Depends(require_project_permission(Perm.FINDING_VIEW_VERIFIED)),
    db: Session = Depends(get_db),
    filters: FindingFilters = Depends(finding_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[FindingOut]:
    """Findings this person may see, newest first. Rejected ones only when asked for."""
    findings, total = service.list_findings(db, ctx, filters, page=page, page_size=page_size)
    return Page(items=service.to_out(db, findings), page=page, page_size=page_size, total=total)


@project_router.get("/findings.geojson")
def findings_map(
    ctx: ProjectContext = Depends(require_project_permission(Perm.FINDING_VIEW_VERIFIED)),
    db: Session = Depends(get_db),
    filters: FindingFilters = Depends(finding_filters),
) -> dict[str, Any]:
    """The same findings as the list, as map points (findings without a location are left
    out here and flagged in the list)."""
    return service.findings_geojson(db, ctx, filters)


@project_router.post("/findings", response_model=FindingOut, status_code=status.HTTP_201_CREATED)
def add_manual_finding(
    body: ManualFindingCreate,
    ctx: ProjectContext = Depends(require_project_permission(Perm.FINDING_CREATE_MANUAL)),
    db: Session = Depends(get_db),
) -> FindingOut:
    """Add a problem seen by a person (e.g. a sidewalk observation). Starts "awaiting review"."""
    finding = service.create_manual(db, ctx, body)
    return service.to_out(db, [finding])[0]


@project_router.get("/review-options", response_model=ReviewOptions)
def review_options(
    ctx: ProjectContext = Depends(require_project_permission(Perm.FINDING_VIEW_VERIFIED)),
    db: Session = Depends(get_db),
) -> ReviewOptions:
    """Finding types and the current severity scale, for the review and add screens."""
    return service.review_options(db, ctx)


# ------------------------------------------------------------------ one finding
def _load(
    db: Session, current: CurrentUser, finding_id: uuid.UUID
) -> tuple[ProjectContext, Finding]:
    """Findings in projects the caller cannot see are reported as not found."""
    project_id = db.scalar(select(Finding.project_id).where(Finding.id == finding_id))
    if project_id is None:
        raise NotFoundError("Finding not found.")
    ctx = load_project_context(db, current.user, project_id)
    return ctx, service.get_visible_finding(db, ctx, finding_id)


@finding_router.get("", response_model=FindingOut)
def get_finding(
    finding_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FindingOut:
    _, finding = _load(db, current, finding_id)
    return service.to_out(db, [finding])[0]


@finding_router.post("/review", response_model=FindingOut)
def review_finding(
    finding_id: uuid.UUID,
    body: ReviewRequest,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FindingOut:
    """Verify, reject, mark "needs field check", or edit. Send the `version` you loaded;
    if someone else saved first the answer is 409 and nothing is changed."""
    ctx, _ = _load(db, current, finding_id)
    if not ctx.has(Perm.FINDING_REVIEW):
        raise PermissionDeniedError()
    finding = service.review(db, ctx, finding_id, body)
    return service.to_out(db, [finding])[0]


@finding_router.get("/history", response_model=list[ReviewEventOut])
def finding_history(
    finding_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ReviewEventOut]:
    """Every review action on this finding, oldest first."""
    ctx, finding = _load(db, current, finding_id)
    return service.history(db, ctx, finding)
