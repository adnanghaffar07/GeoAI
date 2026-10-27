"""Photos: upload, list, details, protected file download, pick location, withdraw.

Paths (api-spec.md section 3.5). Every route is permission-checked; photo files are only
ever sent through these routes, never served directly from storage (FR-18, AC-08).
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
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
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from app.core.permissions import Perm
from app.models import Image
from app.schemas.common import Page
from app.schemas.images import ImageOut, LatLon, SetLocationRequest, UploadResult
from app.services import images as service

project_router = APIRouter(prefix="/projects/{project_id}/images", tags=["images"])
router = APIRouter(prefix="/images/{image_id}", tags=["images"])


@project_router.post("", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
def upload_image(
    response: Response,
    file: UploadFile = File(description="One JPEG or PNG photo"),
    device_latitude: float | None = Form(default=None),
    device_longitude: float | None = Form(default=None),
    ctx: ProjectContext = Depends(require_project_permission(Perm.IMAGE_UPLOAD)),
    db: Session = Depends(get_db),
) -> UploadResult:
    """Upload one photo. `201` = new photo; `200` with `duplicate: true` = this exact file
    was already uploaded to the project (safe to retry)."""
    device_location = None
    if device_latitude is not None or device_longitude is not None:
        if device_latitude is None or device_longitude is None:
            raise ValidationFailedError(
                "Send both device_latitude and device_longitude, or neither."
            )
        device_location = LatLon(latitude=device_latitude, longitude=device_longitude)
    outcome = service.upload_image(
        db,
        ctx,
        upload=file.file,
        filename=file.filename or "photo",
        device_location=device_location,
    )
    if outcome.duplicate:
        response.status_code = status.HTTP_200_OK
    return UploadResult(duplicate=outcome.duplicate, image=service.to_out([outcome.image], db)[0])


@project_router.get("", response_model=Page[ImageOut])
def list_images(
    ctx: ProjectContext = Depends(require_project_permission(Perm.IMAGE_STATUS_VIEW)),
    db: Session = Depends(get_db),
    missing_location: bool = False,
    include_withdrawn: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[ImageOut]:
    """Photos in the project. Field collectors see only their own uploads."""
    images, total = service.list_images(
        db,
        ctx,
        missing_location_only=missing_location,
        include_withdrawn=include_withdrawn,
        page=page,
        page_size=page_size,
    )
    items = service.to_out(images, db, show_candidate_counts=ctx.has(Perm.FINDING_VIEW_CANDIDATES))
    return Page(items=items, page=page, page_size=page_size, total=total)


# ------------------------------------------------------------- single photo routes
def _load(db: Session, current: CurrentUser, image_id: uuid.UUID) -> tuple[ProjectContext, Image]:
    """Find the photo and the caller's access to its project. Photos in projects the
    caller cannot see are reported as not found."""
    project_id = db.scalar(select(Image.project_id).where(Image.id == image_id))
    if project_id is None:
        raise NotFoundError("Photo not found.")
    ctx = load_project_context(db, current.user, project_id)
    return ctx, service.get_image(db, ctx, image_id)


@router.get("", response_model=ImageOut)
def get_image(
    image_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageOut:
    ctx, image = _load(db, current, image_id)
    if not service.can_view_status(ctx, image):
        raise PermissionDeniedError()
    return service.to_out([image], db, show_candidate_counts=ctx.has(Perm.FINDING_VIEW_CANDIDATES))[
        0
    ]


def _send(image: Image, key: str | None, media_type: str, filename: str) -> FileResponse:
    if not key or not storage.exists(key):
        raise NotFoundError("The photo file is not available.")
    return FileResponse(
        storage.path_for(key),
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/file", response_class=FileResponse)
def download_original(
    image_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """The original photo, unchanged. Permission-checked on every request."""
    ctx, image = _load(db, current, image_id)
    if not service.can_view_file(ctx, image, db):
        raise PermissionDeniedError()
    return _send(image, image.storage_key, image.content_type, image.original_filename)


@router.get("/preview", response_class=FileResponse)
def download_preview(
    image_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """A smaller copy for screens. Same permission rules as the original."""
    ctx, image = _load(db, current, image_id)
    if not service.can_view_file(ctx, image, db):
        raise PermissionDeniedError()
    return _send(image, image.preview_storage_key, "image/jpeg", f"preview-{image.id}.jpg")


@router.patch("/location", response_model=ImageOut)
def set_location(
    image_id: uuid.UUID,
    body: SetLocationRequest,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageOut:
    ctx, image = _load(db, current, image_id)
    if not ctx.has(Perm.IMAGE_LOCATION_SET):
        raise PermissionDeniedError()
    service.set_location(db, ctx, image, body)
    db.commit()
    db.refresh(image)
    return service.to_out([image], db, show_candidate_counts=ctx.has(Perm.FINDING_VIEW_CANDIDATES))[
        0
    ]


@router.post("/withdraw", response_model=ImageOut)
def withdraw(
    image_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageOut:
    ctx, image = _load(db, current, image_id)
    if not ctx.has(Perm.IMAGE_WITHDRAW):
        raise PermissionDeniedError()
    service.withdraw(db, ctx, image)
    db.commit()
    db.refresh(image)
    return service.to_out([image], db, show_candidate_counts=ctx.has(Perm.FINDING_VIEW_CANDIDATES))[
        0
    ]
