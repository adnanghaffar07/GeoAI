# ruff: noqa: E501
"""Shareable photo links (team lead plan, item 9). Managers make and cancel them; anyone with a working link sees the preview."""

import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.core.auth import CurrentUser, get_current_user, load_project_context
from app.core.database import get_db
from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.permissions import Perm
from app.models import Image
from app.services import images as image_service
from app.services import share_links as service

router = APIRouter(tags=["share links"])


def _manager(db: Session, current: CurrentUser, image_id: uuid.UUID):
    project_id = db.scalar(select(Image.project_id).where(Image.id == image_id))
    if project_id is None:
        raise NotFoundError("Photo not found.")
    ctx = load_project_context(db, current.user, project_id)
    if not ctx.has(Perm.IMAGE_SHARE):
        raise PermissionDeniedError()
    return ctx, image_service.get_image(db, ctx, image_id)


@router.post("/images/{image_id}/share-links", status_code=status.HTTP_201_CREATED)
def create_link(
    image_id: uuid.UUID,
    days: int = Body(service.DEFAULT_DAYS, embed=True),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ctx, image = _manager(db, current, image_id)
    return service.create(db, ctx, image, days)


@router.get("/images/{image_id}/share-links")
def list_links(
    image_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    _manager(db, current, image_id)
    return service.list_for(db, image_id)


@router.post("/images/{image_id}/share-links/{link_id}/revoke")
def revoke_link(
    image_id: uuid.UUID,
    link_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ctx, _image = _manager(db, current, image_id)
    return service.revoke(db, ctx, link_id)


@router.get("/shared/{token}", response_class=Response)
def open_link(token: str, db: Session = Depends(get_db)) -> Response:
    """No sign-in. Only the preview (no GPS in it); not cached by shared caches; not indexed."""
    image = service.resolve(db, token)
    answer = image and storage.file_response(
        image.preview_storage_key or "",
        "image/jpeg",
        {
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Robots-Tag": "noindex",
            "Referrer-Policy": "no-referrer",
        },
    )
    if not answer:
        raise NotFoundError("This link does not work. It may have ended or been cancelled.")
    return answer
