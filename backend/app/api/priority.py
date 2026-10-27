"""Inspection priority and inspections (api-spec.md section 3.8).

The score is always called "inspection priority": it helps decide what to inspect first
and does not decide repairs or compliance (FR-42).
"""

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.core.auth import (
    CurrentUser,
    ProjectContext,
    get_current_user,
    load_project_context,
    require_project_permission,
)
from app.core.database import get_db
from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.permissions import Perm
from app.models import Finding, Inspection
from app.models.priority import ACTIVE_INSPECTION_STATES
from app.schemas.common import Page
from app.schemas.priority import (
    AssignedInspection,
    InspectionOut,
    InspectionPlan,
    InspectionReopen,
    InspectionUpdate,
    PriorityConfigIn,
    PriorityConfigOut,
    PriorityItem,
    PriorityList,
)
from app.services import findings as findings_service
from app.services import inspections as service
from app.services import priority as priority_service

project_router = APIRouter(prefix="/projects/{project_id}", tags=["priority"])
finding_router = APIRouter(prefix="/findings/{finding_id}", tags=["priority"])
inspection_router = APIRouter(prefix="/inspections/{inspection_id}", tags=["priority"])

INSPECTION_FILTER = "^(none|planned|inspected|resolved)$"


# ------------------------------------------------------------------ settings
@project_router.get("/priority-configs", response_model=Page[PriorityConfigOut])
def list_priority_configs(
    ctx: ProjectContext = Depends(require_project_permission(Perm.PRIORITY_VIEW)),
    db: Session = Depends(get_db),
) -> Page[PriorityConfigOut]:
    """Settings versions, newest first. The current one is marked; placeholders flagged."""
    configs = priority_service.list_configs(db, ctx.project)
    items = [priority_service.config_out(db, config) for config in configs]
    return Page(items=items, page=1, page_size=len(items), total=len(items))


@project_router.post(
    "/priority-configs", response_model=PriorityConfigOut, status_code=status.HTTP_201_CREATED
)
def save_priority_config(
    body: PriorityConfigIn,
    ctx: ProjectContext = Depends(require_project_permission(Perm.PRIORITY_CONFIGURE)),
    db: Session = Depends(get_db),
) -> PriorityConfigOut:
    """Save a new settings version (recorded in the history). Old scores are kept."""
    return priority_service.config_out(db, priority_service.save_config(db, ctx, body))


# ------------------------------------------------------------------ ranked list
@project_router.get("/priority-list", response_model=PriorityList)
def priority_list(
    ctx: ProjectContext = Depends(require_project_permission(Perm.PRIORITY_VIEW)),
    db: Session = Depends(get_db),
    inspection_status: str | None = Query(default=None, pattern=INSPECTION_FILTER),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> PriorityList:
    """Verified findings only (FR-39), highest inspection priority first, each with its
    breakdown and missing inputs (FR-41)."""
    query = select(Finding).where(
        Finding.project_id == ctx.project.id, Finding.review_status == "verified"
    )
    if inspection_status:
        query = query.where(Finding.inspection_status == inspection_status)
    findings = list(db.scalars(query))
    config, results = priority_service.scores_for(db, ctx.project, findings)
    findings.sort(key=lambda f: (-results[f.id][0], f.created_at, str(f.id)))
    page_items = findings[(page - 1) * page_size : page * page_size]
    outs = {out.id: out for out in findings_service.to_out(db, page_items)}
    latest = service.latest_inspections(db, [f.id for f in page_items])
    inspections = {item.finding_id: item for item in service.to_out(db, list(latest.values()))}
    return PriorityList(
        items=[
            PriorityItem(
                finding=outs[f.id],
                score=results[f.id][0],
                breakdown=results[f.id][1],
                inspection=inspections.get(f.id),
            )
            for f in page_items
        ],
        page=page,
        page_size=page_size,
        total=len(findings),
        config=priority_service.config_out(db, config),
    )


@project_router.get("/inspections", response_model=Page[AssignedInspection])
def list_inspections(
    ctx: ProjectContext = Depends(require_project_permission(Perm.PROJECT_VIEW)),
    db: Session = Depends(get_db),
    mine: bool = False,
    include_closed: bool = False,
) -> Page[AssignedInspection]:
    """Inspections in the project, earliest planned date first. People who cannot see the
    priority list (e.g. field collectors) see only the inspections assigned to them."""
    if not ctx.has(Perm.PRIORITY_VIEW):
        if not ctx.has(Perm.INSPECTION_RECORD):
            raise PermissionDeniedError()
        mine = True
    query = (
        select(Inspection)
        .join(Finding, Finding.id == Inspection.finding_id)
        .where(Finding.project_id == ctx.project.id)
    )
    if not include_closed:
        query = query.where(Inspection.status.in_(ACTIVE_INSPECTION_STATES))
    if mine:
        query = query.where(Inspection.owner_user_id == ctx.user.id)
    inspections = list(
        db.scalars(query.order_by(Inspection.planned_date, Inspection.id).limit(500))
    )
    findings = {
        f.id: f
        for f in db.scalars(
            select(Finding).where(Finding.id.in_([i.finding_id for i in inspections]))
        )
    }
    finding_outs = {out.id: out for out in findings_service.to_out(db, list(findings.values()))}
    items = [
        AssignedInspection(inspection=out, finding=finding_outs[out.finding_id])
        for out in service.to_out(db, inspections)
    ]
    return Page(items=items, page=1, page_size=len(items), total=len(items))


# ------------------------------------------------------------------ one finding
def _finding(
    db: Session, current: CurrentUser, finding_id: uuid.UUID
) -> tuple[ProjectContext, Finding]:
    project_id = db.scalar(select(Finding.project_id).where(Finding.id == finding_id))
    if project_id is None:
        raise NotFoundError("Finding not found.")
    ctx = load_project_context(db, current.user, project_id)
    return ctx, findings_service.get_visible_finding(db, ctx, finding_id)


@finding_router.post(
    "/inspections", response_model=InspectionOut, status_code=status.HTTP_201_CREATED
)
def plan_inspection(
    finding_id: uuid.UUID,
    body: InspectionPlan,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InspectionOut:
    """Plan a field inspection of a verified finding (owner and date)."""
    ctx, finding = _finding(db, current, finding_id)
    return service.to_out(db, [service.plan(db, ctx, finding, body)])[0]


@finding_router.get("/inspections", response_model=list[InspectionOut])
def finding_inspections(
    finding_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[InspectionOut]:
    """All inspections of the finding, oldest first (reopened ones stay as history)."""
    ctx, finding = _finding(db, current, finding_id)
    items = service.history(db, finding.id)
    if not ctx.has(Perm.PRIORITY_VIEW):
        # e.g. a field collector: only the inspections assigned to them.
        items = [item for item in items if service.can_record(ctx, item)]
        if not items:
            raise PermissionDeniedError()
    return service.to_out(db, items)


# ------------------------------------------------------------------ one inspection
def _inspection(
    db: Session, current: CurrentUser, inspection_id: uuid.UUID
) -> tuple[ProjectContext, Finding, Inspection]:
    finding_id = db.scalar(select(Inspection.finding_id).where(Inspection.id == inspection_id))
    if finding_id is None:
        raise NotFoundError("Inspection not found.")
    ctx, finding = _finding(db, current, finding_id)
    inspection = db.get(Inspection, inspection_id)
    if inspection is None:
        raise NotFoundError("Inspection not found.")
    if not ctx.has(Perm.PRIORITY_VIEW) and not service.can_record(ctx, inspection):
        raise NotFoundError("Inspection not found.")
    return ctx, finding, inspection


@inspection_router.patch("", response_model=InspectionOut)
def record_inspection(
    inspection_id: uuid.UUID,
    body: InspectionUpdate,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InspectionOut:
    """Mark inspected, or resolved (needs a note or a photo)."""
    ctx, finding, _ = _inspection(db, current, inspection_id)
    return service.to_out(db, [service.record(db, ctx, finding, inspection_id, body)])[0]


@inspection_router.post("/evidence", response_model=InspectionOut)
def add_evidence(
    inspection_id: uuid.UUID,
    file: UploadFile = File(description="A JPEG or PNG photo of the result"),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InspectionOut:
    ctx, _, _ = _inspection(db, current, inspection_id)
    return service.to_out(db, [service.add_evidence(db, ctx, inspection_id, file.file)])[0]


@inspection_router.get("/evidence", response_class=FileResponse)
def get_evidence(
    inspection_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """The result photo. Permission-checked on every request; never served directly."""
    _, _, inspection = _inspection(db, current, inspection_id)
    key = inspection.evidence_storage_key
    if not key or not storage.exists(key):
        raise NotFoundError("No photo is attached to this inspection.")
    return FileResponse(
        storage.path_for(key),
        media_type=inspection.evidence_content_type or "application/octet-stream",
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )


@inspection_router.post(
    "/reopen", response_model=InspectionOut, status_code=status.HTTP_201_CREATED
)
def reopen_inspection(
    inspection_id: uuid.UUID,
    body: InspectionReopen,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InspectionOut:
    """Reopen a resolved inspection. The old one is kept; a new one is planned."""
    ctx, finding, _ = _inspection(db, current, inspection_id)
    return service.to_out(db, [service.reopen(db, ctx, finding, inspection_id, body)])[0]
