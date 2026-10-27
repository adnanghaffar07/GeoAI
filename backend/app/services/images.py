"""Business rules for photos: upload, list, view, locate, withdraw.

Upload steps: receive the file (size limit) while fingerprinting it (SHA-256) -> if the
project already has this exact file, return it (no duplicate) -> read format, GPS,
capture time, quality -> store original and preview privately -> save the record.
"""

import hashlib
import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import storage
from app.ai.registry import is_stand_in, is_trial
from app.core.auth import ProjectContext
from app.core.config import get_settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    PermissionDeniedError,
    UnsupportedMediaTypeError,
)
from app.core.permissions import Perm
from app.models import AnalysisJob, Finding, FindingImage, Image, Project, User
from app.models.base import utc_now
from app.models.image import FLAG_MISSING_GPS, FLAG_OUTSIDE_PROJECT_AREA
from app.schemas.images import ImageAnalysis, ImageOut, LatLon
from app.services import analysis as analysis_service
from app.services.audit import record_event
from app.services.photo_metadata import NotAPhotoError, make_preview, read_photo
from app.services.projects import ensure_not_archived

log = logging.getLogger(__name__)

_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class UploadOutcome:
    image: Image
    duplicate: bool


def _point(latitude: float, longitude: float) -> object:
    return func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)


def _inside_project(db: Session, project_id: uuid.UUID, latitude: float, longitude: float) -> bool:
    return bool(
        db.scalar(
            select(func.ST_Intersects(Project.boundary, _point(latitude, longitude))).where(
                Project.id == project_id
            )
        )
    )


def _receive(upload: BinaryIO, limit_bytes: int) -> tuple[Path, str, int]:
    """Copy the upload to a temporary file, enforcing the size limit and fingerprinting it."""
    digest = hashlib.sha256()
    size = 0
    temp_path = storage.temp_dir() / f"{uuid.uuid4().hex}.upload"
    try:
        with temp_path.open("wb") as out:
            while chunk := upload.read(_CHUNK):
                size += len(chunk)
                if size > limit_bytes:
                    raise PayloadTooLargeError(
                        f"The file is larger than {limit_bytes // (1024 * 1024)} MB."
                    )
                digest.update(chunk)
                out.write(chunk)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    if size == 0:
        temp_path.unlink(missing_ok=True)
        raise UnsupportedMediaTypeError("The file is empty.")
    return temp_path, digest.hexdigest(), size


def _existing(db: Session, project_id: uuid.UUID, sha256: str) -> Image | None:
    return db.scalar(select(Image).where(Image.project_id == project_id, Image.sha256 == sha256))


def upload_image(
    db: Session,
    ctx: ProjectContext,
    *,
    upload: BinaryIO,
    filename: str,
    device_location: LatLon | None,
) -> UploadOutcome:
    """Store one photo. Commits. Uploading the same file again returns the existing photo."""
    ensure_not_archived(ctx)
    settings = get_settings()
    temp_path, sha256, size = _receive(upload, settings.max_upload_mb * 1024 * 1024)
    stored_keys: list[str] = []
    try:
        if existing := _existing(db, ctx.project.id, sha256):
            log.info("Photo already in project (same file), kept image=%s", existing.id)
            return UploadOutcome(existing, duplicate=True)

        try:
            info = read_photo(
                temp_path,
                blur_threshold=settings.blur_threshold,
                darkness_threshold=settings.darkness_threshold,
            )
        except NotAPhotoError as exc:
            raise UnsupportedMediaTypeError(str(exc)) from exc

        flags = list(info.quality_flags)
        latitude, longitude, source = info.latitude, info.longitude, "photo_gps"
        if latitude is None and device_location is not None:
            latitude, longitude, source = (
                device_location.latitude,
                device_location.longitude,
                "device_gps",
            )
        if latitude is None or longitude is None:
            source = "none"
            flags.append(FLAG_MISSING_GPS)
        elif not _inside_project(db, ctx.project.id, latitude, longitude):
            flags.append(FLAG_OUTSIDE_PROJECT_AREA)

        image_id = uuid.uuid4()
        base = f"org/{ctx.project.organization_id}/project/{ctx.project.id}/image/{image_id}"
        original_key = f"{base}/original.{info.extension}"
        preview_key = f"{base}/preview.jpg"
        storage.save_bytes(preview_key, make_preview(temp_path, settings.preview_max_px))
        stored_keys.append(preview_key)
        storage.save_file(original_key, temp_path)
        stored_keys.append(original_key)

        image = Image(
            id=image_id,
            project_id=ctx.project.id,
            uploaded_by=ctx.user.id,
            original_filename=(Path(filename or "photo").name or "photo")[:255],
            storage_key=original_key,
            preview_storage_key=preview_key,
            content_type=info.content_type,
            size_bytes=size,
            sha256=sha256,
            width_px=info.width_px,
            height_px=info.height_px,
            captured_at=info.captured_at,
            original_location=_point(latitude, longitude) if source != "none" else None,  # type: ignore[arg-type]
            location_source=source,
            location_quality="approximate" if source != "none" else "missing",
            quality_flags=sorted(set(flags)),
        )
        db.add(image)
        try:
            db.commit()
        except IntegrityError:
            # Someone uploaded the same file at the same moment: keep theirs.
            db.rollback()
            for key in stored_keys:
                storage.delete(key)
            stored_keys.clear()
            existing = _existing(db, ctx.project.id, sha256)
            if existing is None:
                raise
            return UploadOutcome(existing, duplicate=True)
        db.refresh(image)
        stored_keys.clear()
        log.info(
            "Photo stored: image=%s project=%s size=%s KB location=%s flags=%s",
            image.id,
            ctx.project.id,
            size // 1024,
            source,
            ",".join(image.quality_flags) or "none",
        )
        return UploadOutcome(image, duplicate=False)
    except BaseException:
        for key in stored_keys:
            storage.delete(key)
        raise
    finally:
        temp_path.unlink(missing_ok=True)


# ------------------------------------------------------------------- viewing rules
def can_view_status(ctx: ProjectContext, image: Image) -> bool:
    if not ctx.has(Perm.IMAGE_STATUS_VIEW):
        return False
    return ctx.is_unconditional(Perm.IMAGE_STATUS_VIEW) or image.uploaded_by == ctx.user.id


def can_view_file(ctx: ProjectContext, image: Image, db: Session) -> bool:
    """Original/preview access. Collectors see their own uploads; viewers only photos of
    verified findings (decision Q4)."""
    if not ctx.has(Perm.IMAGE_VIEW):
        return False
    if ctx.is_unconditional(Perm.IMAGE_VIEW):
        return True
    if "field_collector" in ctx.project_roles and image.uploaded_by == ctx.user.id:
        return True
    if "viewer" in ctx.project_roles:
        return _shows_verified_finding(db, image.id)
    return False


def _shows_verified_finding(db: Session, image_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(func.count())
            .select_from(FindingImage)
            .join(Finding, Finding.id == FindingImage.finding_id)
            .where(FindingImage.image_id == image_id, Finding.review_status == "verified")
        )
        != 0
    )


def get_image(db: Session, ctx: ProjectContext, image_id: uuid.UUID) -> Image:
    image = db.scalar(select(Image).where(Image.id == image_id, Image.project_id == ctx.project.id))
    if image is None:
        raise NotFoundError("Photo not found.")
    return image


def list_images(
    db: Session,
    ctx: ProjectContext,
    *,
    missing_location_only: bool,
    include_withdrawn: bool,
    page: int,
    page_size: int,
) -> tuple[list[Image], int]:
    conditions = [Image.project_id == ctx.project.id]
    if not ctx.is_unconditional(Perm.IMAGE_STATUS_VIEW):
        conditions.append(Image.uploaded_by == ctx.user.id)  # collectors: own uploads
    if not include_withdrawn:
        conditions.append(Image.status == "stored")
    if missing_location_only:
        conditions.append(Image.location_source == "none")
    total = db.scalar(select(func.count()).select_from(Image).where(*conditions)) or 0
    images = db.scalars(
        select(Image)
        .where(*conditions)
        .order_by(Image.created_at.desc(), Image.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(images), total


def set_location(db: Session, ctx: ProjectContext, image: Image, location: LatLon) -> Image:
    """Pick a location for a photo WITHOUT one (FR-15). A photo that has a location keeps
    its original; corrections are made on findings, never by overwriting the original."""
    ensure_not_archived(ctx)
    if not (ctx.is_unconditional(Perm.IMAGE_LOCATION_SET) or image.uploaded_by == ctx.user.id):
        raise PermissionDeniedError()
    if image.location_source != "none":
        raise ConflictError("This photo already has a location. Corrections are made on findings.")
    image.original_location = _point(location.latitude, location.longitude)  # type: ignore[assignment]
    image.location_source = "manual"
    image.location_quality = "approximate"
    flags = [
        f for f in image.quality_flags if f not in (FLAG_MISSING_GPS, FLAG_OUTSIDE_PROJECT_AREA)
    ]
    if not _inside_project(db, ctx.project.id, location.latitude, location.longitude):
        flags.append(FLAG_OUTSIDE_PROJECT_AREA)
    image.quality_flags = sorted(flags)
    record_event(
        db,
        action="image.location_set",
        organization_id=ctx.project.organization_id,
        project_id=ctx.project.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="image",
        target_id=image.id,
        details={"latitude": location.latitude, "longitude": location.longitude},
    )
    return image


def withdraw(db: Session, ctx: ProjectContext, image: Image) -> Image:
    """Mark a photo withdrawn (nothing is deleted). Collectors: own photos only, and only
    before analysis has started (analysis arrives in P5)."""
    ensure_not_archived(ctx)
    if not ctx.is_unconditional(Perm.IMAGE_WITHDRAW):
        # Field collectors: own photos only, and only before analysis has started (Q6).
        if image.uploaded_by != ctx.user.id:
            raise PermissionDeniedError()
        if analysis_service.has_analysis(db, image.id):
            raise ConflictError(
                "This photo has already been sent for analysis, so it can no longer be "
                "withdrawn. Ask your project manager."
            )
    if image.status != "withdrawn":
        image.status = "withdrawn"
        image.withdrawn_at = utc_now()
        record_event(
            db,
            action="image.withdrawn",
            organization_id=ctx.project.organization_id,
            project_id=ctx.project.id,
            actor_user_id=ctx.user.id,
            actor_roles=ctx.actor_roles,
            target_type="image",
            target_id=image.id,
        )
    return image


# ------------------------------------------------------------------------ output
def to_out(
    images: Iterable[Image], db: Session, *, show_candidate_counts: bool = False
) -> list[ImageOut]:
    images = list(images)
    jobs = analysis_service.jobs_for_images(db, [i.id for i in images])
    counts = (
        analysis_service.candidate_counts(db, [job.id for job in jobs.values()])
        if show_candidate_counts
        else {}
    )
    names = dict(
        db.execute(
            select(User.id, User.full_name).where(User.id.in_({i.uploaded_by for i in images}))
        ).all()
    )
    coordinates = {
        image_id: LatLon(latitude=lat, longitude=lon)
        for image_id, lat, lon in db.execute(
            select(
                Image.id, func.ST_Y(Image.original_location), func.ST_X(Image.original_location)
            ).where(Image.id.in_([i.id for i in images]), Image.original_location.is_not(None))
        ).all()
    }
    result = []
    for image in images:
        location = coordinates.get(image.id)
        result.append(
            ImageOut(
                id=image.id,
                project_id=image.project_id,
                original_filename=image.original_filename,
                content_type=image.content_type,
                size_bytes=image.size_bytes,
                width_px=image.width_px,
                height_px=image.height_px,
                captured_at=image.captured_at,
                location=location,
                location_source=image.location_source,
                location_quality=image.location_quality,
                quality_flags=image.quality_flags,
                status=image.status,
                uploaded_by=image.uploaded_by,
                uploaded_by_name=names.get(image.uploaded_by),
                created_at=image.created_at,
                analysis=_analysis_out(jobs.get(image.id), counts, show_candidate_counts),
            )
        )
    return result


def _analysis_out(
    job: AnalysisJob | None, counts: dict[uuid.UUID, int], show_counts: bool
) -> ImageAnalysis | None:
    if job is None:
        return None
    return ImageAnalysis(
        job_id=job.id,
        status=job.status,
        failure_reason=job.failure_reason,
        model_version=job.model_version,
        is_test_detector=is_stand_in(job.model_version),
        is_trial_model=is_trial(job.model_version),
        candidate_count=counts.get(job.id, 0)
        if show_counts and job.status == "completed"
        else None,
    )
