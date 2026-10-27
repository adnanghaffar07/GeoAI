"""AI analysis: start jobs, run them in the worker, and turn results into findings.

Rules (FR-19 to FR-24, NFR-04, model-output-contract.md):
- PostgreSQL holds the job state; the queue only carries "please run job X".
- One job per photo and model version. Starting again reuses it, so nothing is duplicated.
- Each AI candidate becomes one finding with status `ai_generated`: a suggestion only.
- A result that breaks the contract fails the whole job; nothing from it is saved.
- An empty result means "no candidates found", never "the road is fine".
"""

import logging
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import storage
from app.ai.contract import InvalidModelOutputError, ModelOutput, validate_output
from app.ai.registry import UnknownModelError, get_model
from app.core.auth import ProjectContext
from app.core.config import get_settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ServiceUnavailableError,
)
from app.core.permissions import Perm
from app.models import AnalysisJob, Finding, FindingImage, Image
from app.models.base import utc_now
from app.services.audit import record_event
from app.services.projects import ensure_not_archived

log = logging.getLogger(__name__)

ACTIVE_STATUSES = ("queued", "processing")

# Plain reasons shown to people when a job fails.
REASON_QUEUE_DOWN = "The analysis service could not be reached. Try again in a moment."
REASON_FILE_MISSING = "The photo file is not available."
REASON_UNREADABLE = "The analysis could not read this photo."
REASON_UNKNOWN_MODEL = "This AI model version is not available."


# ----------------------------------------------------------------- permissions
def _own_only(ctx: ProjectContext, permission: str) -> bool:
    """Field collectors work with their own uploads only (permission matrix §3.4)."""
    return not ctx.is_unconditional(permission)


def can_see_job(ctx: ProjectContext, image: Image) -> bool:
    if not ctx.has(Perm.ANALYSIS_STATUS_VIEW):
        return False
    return not _own_only(ctx, Perm.ANALYSIS_STATUS_VIEW) or image.uploaded_by == ctx.user.id


# ----------------------------------------------------------------- starting jobs
@dataclass
class StartOutcome:
    jobs: list[AnalysisJob]
    created: int
    reused: int


def current_model_version() -> str:
    return get_settings().analysis_model_version


def start_analysis(
    db: Session,
    ctx: ProjectContext,
    *,
    image_ids: list[uuid.UUID] | None,
) -> StartOutcome:
    """Create (or reuse) one job per photo for the current model. Commits.

    `image_ids=None` means "every photo in the project not yet analysed".
    Queuing happens after the commit (see `queue_jobs`).
    """
    ensure_not_archived(ctx)
    model_version = current_model_version()
    model = get_model(model_version)  # fail early if the configured model is unknown
    found = model.problem() if model.problem else None
    if found:  # e.g. the model file is missing: say so now instead of failing every photo
        log.warning("Analysis not started: %s", found)
        raise ServiceUnavailableError(found)

    query = select(Image).where(Image.project_id == ctx.project.id, Image.status == "stored")
    if _own_only(ctx, Perm.ANALYSIS_RUN):
        query = query.where(Image.uploaded_by == ctx.user.id)
    if image_ids is not None:
        wanted = set(image_ids)
        query = query.where(Image.id.in_(wanted))
    images = list(db.scalars(query).all())
    if image_ids is not None and len(images) != len(set(image_ids)):
        raise NotFoundError("Some photos were not found, or you cannot analyse them.")

    existing = {
        job.image_id: job
        for job in db.scalars(
            select(AnalysisJob).where(
                AnalysisJob.image_id.in_([image.id for image in images]),
                AnalysisJob.model_version == model_version,
            )
        )
    }
    jobs: list[AnalysisJob] = []
    created = 0
    for image in images:
        job = existing.get(image.id)
        if job is None:
            job = AnalysisJob(
                image_id=image.id, model_version=model_version, requested_by=ctx.user.id
            )
            db.add(job)
            created += 1
        jobs.append(job)

    if created:
        record_event(
            db,
            action="analysis.started",
            organization_id=ctx.project.organization_id,
            project_id=ctx.project.id,
            actor_user_id=ctx.user.id,
            actor_roles=ctx.actor_roles,
            target_type="project",
            target_id=ctx.project.id,
            details={"photos": created, "model_version": model_version},
        )
    db.commit()
    return StartOutcome(jobs=jobs, created=created, reused=len(images) - created)


def retry_job(db: Session, ctx: ProjectContext, job: AnalysisJob, image: Image) -> AnalysisJob:
    """Put a failed job back in the queue. Its findings, if any, are never duplicated."""
    ensure_not_archived(ctx)
    if not ctx.has(Perm.ANALYSIS_RUN) or (
        _own_only(ctx, Perm.ANALYSIS_RUN) and image.uploaded_by != ctx.user.id
    ):
        raise PermissionDeniedError()
    if job.status != "failed":
        raise ConflictError("Only an analysis that failed can be retried.")
    job.status = "queued"
    job.failure_reason = None
    job.queued_at = utc_now()
    job.started_at = None
    job.finished_at = None
    record_event(
        db,
        action="analysis.started",
        organization_id=ctx.project.organization_id,
        project_id=ctx.project.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="analysis_job",
        target_id=job.id,
        details={"retry": True, "model_version": job.model_version},
    )
    db.commit()
    return job


def queue_jobs(db: Session, jobs: Iterable[AnalysisJob], send: Callable[[uuid.UUID], None]) -> None:
    """Hand queued jobs to the worker. If the queue is down, the job is marked failed with a
    plain reason, so the person can press Retry later (nothing gets stuck in "waiting")."""
    for job in jobs:
        if job.status != "queued":
            continue
        try:
            send(job.id)
        except Exception:  # any queue problem means the same thing to the user
            log.warning("Could not queue analysis job %s", job.id, exc_info=True)
            job.status = "failed"
            job.failure_reason = REASON_QUEUE_DOWN
            job.finished_at = utc_now()
            db.commit()


# ----------------------------------------------------------------- running a job (worker)
def _fail(db: Session, job: AnalysisJob, reason: str) -> None:
    job.status = "failed"
    job.failure_reason = reason
    job.finished_at = utc_now()
    db.commit()
    log.warning("Analysis failed: job=%s reason=%s", job.id, reason)


def run_job(db: Session, job_id: uuid.UUID) -> None:
    """Run one analysis job. Safe to run twice: a finished job is skipped, and findings that
    already exist (same job and detection index) are never created again."""
    job = db.scalar(select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update())
    if job is None:
        log.warning("Analysis job %s not found; nothing to do", job_id)
        return
    if job.status == "completed":
        log.info("Analysis job %s already completed; skipped", job_id)
        db.rollback()
        return
    image = db.get(Image, job.image_id)
    if image is None:  # cannot happen (foreign key), but never crash the worker
        _fail(db, job, REASON_FILE_MISSING)
        return

    job.status = "processing"
    job.attempts += 1
    job.started_at = utc_now()
    job.failure_reason = None
    db.commit()

    try:
        model = get_model(job.model_version)
    except UnknownModelError:
        _fail(db, job, REASON_UNKNOWN_MODEL)
        return
    if not storage.exists(image.storage_key):
        _fail(db, job, REASON_FILE_MISSING)
        return

    try:
        note = model.detect(storage.path_for(image.storage_key), image_id=str(image.id))
    except Exception:  # any detector crash fails this job only, never the worker
        log.exception("Detector crashed on job %s", job.id)
        _fail(db, job, REASON_UNREADABLE)
        return

    try:
        output = validate_output(
            note,
            expected_image_id=str(image.id),
            expected_model_version=job.model_version,
            allowed_classes=model.classes,
        )
    except InvalidModelOutputError as exc:
        _fail(db, job, f"Invalid model output: {exc}.")
        return
    if output.status == "failed":
        _fail(db, job, output.failure_reason or REASON_UNREADABLE)
        return

    _save_findings(db, job, image, output)


def _save_findings(db: Session, job: AnalysisJob, image: Image, output: ModelOutput) -> None:
    """Create one `ai_generated` finding per candidate, all in one transaction with the
    job's "completed" status: either everything is saved or nothing is."""
    job = db.scalar(select(AnalysisJob).where(AnalysisJob.id == job.id).with_for_update()) or job
    already = set(
        db.scalars(select(Finding.detection_index).where(Finding.analysis_job_id == job.id))
    )
    created = 0
    for candidate in output.candidates:
        if candidate.detection_index in already:
            continue
        finding = Finding(
            project_id=image.project_id,
            origin="ai",
            analysis_job_id=job.id,
            detection_index=candidate.detection_index,
            predicted_type_key=candidate.class_key,
            predicted_confidence=round(candidate.confidence, 4),
            predicted_bbox=list(candidate.bbox_px),
            model_version=job.model_version,
            # The photo's approximate camera position, copied now and never changed.
            original_location=image.original_location,
            location_source=image.location_source,
            location_quality="approximate" if image.original_location is not None else "missing",
            review_status="ai_generated",
        )
        db.add(finding)
        db.flush()
        db.add(FindingImage(finding_id=finding.id, image_id=image.id, is_primary=True))
        created += 1
    job.status = "completed"
    job.finished_at = utc_now()
    db.commit()
    log.info(
        "Analysis completed: job=%s image=%s model=%s candidates=%s (new %s)",
        job.id,
        image.id,
        job.model_version,
        len(output.candidates),
        created,
    )


# ----------------------------------------------------------------- reading
def candidate_counts(db: Session, job_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, int]:
    ids = list(job_ids)
    if not ids:
        return {}
    return {
        job_id: int(count)
        for job_id, count in db.execute(
            select(Finding.analysis_job_id, func.count())
            .where(Finding.analysis_job_id.in_(ids))
            .group_by(Finding.analysis_job_id)
        ).all()
        if job_id is not None
    }


def jobs_for_images(db: Session, image_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, AnalysisJob]:
    """The current-model job for each photo, if any."""
    ids = list(image_ids)
    if not ids:
        return {}
    return {
        job.image_id: job
        for job in db.scalars(
            select(AnalysisJob).where(
                AnalysisJob.image_id.in_(ids), AnalysisJob.model_version == current_model_version()
            )
        )
    }


def list_jobs(
    db: Session, ctx: ProjectContext, *, status: str | None, page: int, page_size: int
) -> tuple[list[tuple[AnalysisJob, Image]], int, dict[str, int]]:
    """Jobs in the project (collectors: own uploads only), newest first, plus status counts."""
    conditions = [Image.project_id == ctx.project.id]
    if _own_only(ctx, Perm.ANALYSIS_STATUS_VIEW):
        conditions.append(Image.uploaded_by == ctx.user.id)
    base = (
        select(AnalysisJob, Image).join(Image, Image.id == AnalysisJob.image_id).where(*conditions)
    )
    counts = {
        status_name: int(count)
        for status_name, count in db.execute(
            select(AnalysisJob.status, func.count())
            .join(Image, Image.id == AnalysisJob.image_id)
            .where(*conditions)
            .group_by(AnalysisJob.status)
        ).all()
    }
    if status:
        base = base.where(AnalysisJob.status == status)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        base.order_by(AnalysisJob.queued_at.desc(), AnalysisJob.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [(job, image) for job, image in rows], int(total), counts


def has_analysis(db: Session, image_id: uuid.UUID) -> bool:
    """True once analysis has been requested for the photo (any model)."""
    return db.scalar(select(func.count()).where(AnalysisJob.image_id == image_id)) != 0
