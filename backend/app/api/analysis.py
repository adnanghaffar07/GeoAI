"""AI analysis jobs (api-spec.md section 3.6). Findings are in `app/api/findings.py`.

Every route goes through the project gatekeeper. Field collectors see and start analysis
for their own uploads only, and never see the AI's unreviewed guesses (decision Q5).
"""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.registry import is_stand_in, is_trial
from app.core import queue
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
from app.models import AnalysisJob, Image
from app.schemas.analysis import (
    AnalysisJobList,
    AnalysisJobOut,
    StartAnalysisRequest,
    StartAnalysisResult,
)
from app.services import analysis as service

project_router = APIRouter(prefix="/projects/{project_id}", tags=["analysis"])
job_router = APIRouter(prefix="/analysis-jobs/{job_id}", tags=["analysis"])

JOB_STATUS_PATTERN = "^(queued|processing|completed|failed)$"


def _send(job_id: uuid.UUID) -> None:
    queue.send_analysis_job(job_id)  # looked up at call time, so tests can replace it


def _jobs_out(
    db: Session, ctx: ProjectContext, pairs: list[tuple[AnalysisJob, Image]]
) -> list[AnalysisJobOut]:
    show_counts = ctx.has(Perm.FINDING_VIEW_CANDIDATES)
    counts = service.candidate_counts(db, [job.id for job, _ in pairs]) if show_counts else {}
    return [
        AnalysisJobOut(
            id=job.id,
            image_id=image.id,
            image_filename=image.original_filename,
            model_version=job.model_version,
            is_test_detector=is_stand_in(job.model_version),
            is_trial_model=is_trial(job.model_version),
            status=job.status,
            attempts=job.attempts,
            failure_reason=job.failure_reason,
            candidate_count=(
                counts.get(job.id, 0) if show_counts and job.status == "completed" else None
            ),
            queued_at=job.queued_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
        for job, image in pairs
    ]


# ------------------------------------------------------------------ jobs
@project_router.post(
    "/analysis-jobs", response_model=StartAnalysisResult, status_code=status.HTTP_202_ACCEPTED
)
def start_analysis(
    body: StartAnalysisRequest,
    ctx: ProjectContext = Depends(require_project_permission(Perm.ANALYSIS_RUN)),
    db: Session = Depends(get_db),
) -> StartAnalysisResult:
    """Start analysis for chosen photos, or for every photo not yet analysed.
    Photos that already have a job for this AI version reuse it (never duplicated)."""
    outcome = service.start_analysis(db, ctx, image_ids=body.image_ids or None)
    service.queue_jobs(db, outcome.jobs, _send)
    images = {
        image.id: image
        for image in db.scalars(
            select(Image).where(Image.id.in_([j.image_id for j in outcome.jobs]))
        )
    }
    pairs = [(job, images[job.image_id]) for job in outcome.jobs]
    return StartAnalysisResult(
        created=outcome.created, reused=outcome.reused, jobs=_jobs_out(db, ctx, pairs)
    )


@project_router.get("/analysis-jobs", response_model=AnalysisJobList)
def list_jobs(
    ctx: ProjectContext = Depends(require_project_permission(Perm.ANALYSIS_STATUS_VIEW)),
    db: Session = Depends(get_db),
    job_status: str | None = Query(default=None, alias="status", pattern=JOB_STATUS_PATTERN),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> AnalysisJobList:
    """Jobs with status counts (the screen checks this every few seconds)."""
    pairs, total, counts = service.list_jobs(
        db, ctx, status=job_status, page=page, page_size=page_size
    )
    return AnalysisJobList(
        items=_jobs_out(db, ctx, pairs),
        page=page,
        page_size=page_size,
        total=total,
        status_counts=counts,
    )


def _load_job(
    db: Session, current: CurrentUser, job_id: uuid.UUID
) -> tuple[ProjectContext, AnalysisJob, Image]:
    """Find the job and the caller's access to its project. Jobs in projects the caller
    cannot see are reported as not found."""
    row = db.execute(
        select(AnalysisJob, Image)
        .join(Image, Image.id == AnalysisJob.image_id)
        .where(AnalysisJob.id == job_id)
    ).first()
    if row is None:
        raise NotFoundError("Analysis not found.")
    job, image = row
    ctx = load_project_context(db, current.user, image.project_id)
    return ctx, job, image


@job_router.get("", response_model=AnalysisJobOut)
def get_job(
    job_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisJobOut:
    ctx, job, image = _load_job(db, current, job_id)
    if not service.can_see_job(ctx, image):
        raise PermissionDeniedError()
    return _jobs_out(db, ctx, [(job, image)])[0]


@job_router.post("/retry", response_model=AnalysisJobOut, status_code=status.HTTP_202_ACCEPTED)
def retry_job(
    job_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisJobOut:
    """Retry a failed analysis. Results are never duplicated (FR-21)."""
    ctx, job, image = _load_job(db, current, job_id)
    service.retry_job(db, ctx, job, image)
    service.queue_jobs(db, [job], _send)
    return _jobs_out(db, ctx, [(job, image)])[0]
