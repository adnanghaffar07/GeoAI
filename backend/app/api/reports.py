"""Reports and exports (api-spec.md section 3.9). Downloads are permission-checked and logged."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import storage
from app.core import queue
from app.core.auth import (
    CurrentUser,
    ProjectContext,
    get_current_user,
    load_project_context,
    require_project_permission,
)
from app.core.database import get_db
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.permissions import Perm
from app.models import Report
from app.schemas.common import Page
from app.schemas.reports import ReportOut, ReportRequest, ReportShare
from app.services import reports as service

project_router = APIRouter(prefix="/projects/{project_id}", tags=["reports"])
report_router = APIRouter(prefix="/reports/{report_id}", tags=["reports"])


def _send(report_id: uuid.UUID) -> None:
    queue.send_report_job(report_id)  # looked up at call time, so tests can replace it


@project_router.post("/reports", response_model=ReportOut, status_code=status.HTTP_202_ACCEPTED)
def request_report(
    body: ReportRequest,
    ctx: ProjectContext = Depends(require_project_permission(Perm.REPORT_GENERATE)),
    db: Session = Depends(get_db),
) -> ReportOut:
    """Ask for a CSV, GeoJSON or PDF report. It is built in the background."""
    report = service.request_report(db, ctx, body, _send)
    return service.to_out(db, [report], ctx.project.name)[0]


@project_router.get("/reports", response_model=Page[ReportOut])
def list_reports(
    ctx: ProjectContext = Depends(require_project_permission(Perm.PROJECT_VIEW)),
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[ReportOut]:
    """Reports this person may see: all for managers, shared ones for viewers (FR-50)."""
    if not (ctx.has(Perm.REPORT_VIEW_ALL) or ctx.has(Perm.REPORT_VIEW_SHARED)):
        raise PermissionDeniedError()
    query = select(Report).where(Report.project_id == ctx.project.id)
    if not ctx.has(Perm.REPORT_VIEW_ALL):
        query = query.where(Report.shared_with_viewers.is_(True), Report.status == "completed")
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    reports = list(
        db.scalars(
            query.order_by(Report.created_at.desc(), Report.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=service.to_out(db, reports, ctx.project.name),
        page=page,
        page_size=page_size,
        total=int(total),
    )


def _load(db: Session, current: CurrentUser, report_id: uuid.UUID) -> tuple[ProjectContext, Report]:
    project_id = db.scalar(select(Report.project_id).where(Report.id == report_id))
    if project_id is None:
        raise NotFoundError("Report not found.")
    ctx = load_project_context(db, current.user, project_id)
    return ctx, service.get_report(db, ctx, report_id)


@report_router.get("", response_model=ReportOut)
def get_report(
    report_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportOut:
    ctx, report = _load(db, current, report_id)
    return service.to_out(db, [report], ctx.project.name)[0]


@report_router.get("/file", response_class=FileResponse)
def download_report(
    report_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download the file. Every download is recorded in the history (FR-48)."""
    ctx, report = _load(db, current, report_id)
    if report.status != "completed" or not report.storage_key:
        raise ConflictError("This report is not ready yet.")
    if not storage.exists(report.storage_key):
        raise NotFoundError("The report file is not available.")
    service.log_download(db, ctx, report)
    return FileResponse(
        storage.path_for(report.storage_key),
        media_type=service.MEDIA_TYPES[report.format],
        filename=service.file_name(ctx.project.name, report),
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@report_router.post("/share", response_model=ReportOut)
def share_report(
    report_id: uuid.UUID,
    body: ReportShare,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportOut:
    """Share a finished report with viewers, or stop sharing it."""
    ctx, report = _load(db, current, report_id)
    report = service.share(db, ctx, report, body.shared)
    return service.to_out(db, [report], ctx.project.name)[0]
