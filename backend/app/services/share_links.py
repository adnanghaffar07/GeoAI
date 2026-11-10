# ruff: noqa: E501
"""Shareable photo links (team lead plan, item 9).

A manager makes a secret link to one photo's preview (never the original, never the GPS). It ends after 1-30 days
(7 by default), can be cancelled at any time, and stops working when the photo is withdrawn.
"""

import hashlib
import secrets
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import ProjectContext
from app.core.errors import NotFoundError, ValidationFailedError
from app.models import Image
from app.models.base import utc_now
from app.models.share_link import ImageShareLink
from app.services.audit import record_event

DEFAULT_DAYS = 7
MAX_DAYS = 30


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def out(link: ImageShareLink, token: str | None = None) -> dict[str, Any]:
    now = utc_now()
    state = "cancelled" if link.revoked_at else ("ended" if link.expires_at <= now else "active")
    return {
        "id": str(link.id),
        "image_id": str(link.image_id),
        "created_at": link.created_at,
        "expires_at": link.expires_at,
        "revoked_at": link.revoked_at,
        "state": state,
        # The secret is shown once, when the link is made.
        "url": f"/api/v1/shared/{token}" if token else None,
    }


def _event(db: Session, ctx: ProjectContext, action: str, link: ImageShareLink) -> None:
    record_event(
        db,
        action=action,
        organization_id=ctx.project.organization_id,
        project_id=ctx.project.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="image",
        target_id=link.image_id,
        details={"link_id": str(link.id), "expires_at": link.expires_at.isoformat()},
    )


def create(
    db: Session, ctx: ProjectContext, image: Image, days: int = DEFAULT_DAYS
) -> dict[str, Any]:
    if not 1 <= days <= MAX_DAYS:
        raise ValidationFailedError(f"A link can last 1 to {MAX_DAYS} days.")
    if image.withdrawn_at or not image.preview_storage_key:
        raise ValidationFailedError("This photo cannot be shared (withdrawn or no preview yet).")
    token = secrets.token_urlsafe(24)
    link = ImageShareLink(
        image_id=image.id,
        token_hash=_hash(token),
        created_by=ctx.user.id,
        expires_at=utc_now() + timedelta(days=days),
    )
    db.add(link)
    db.flush()
    _event(db, ctx, "image.shared", link)
    db.commit()
    return out(link, token)


def list_for(db: Session, image_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(ImageShareLink)
        .where(ImageShareLink.image_id == image_id)
        .order_by(ImageShareLink.created_at.desc())
    )
    return [out(r) for r in rows]


def revoke(db: Session, ctx: ProjectContext, link_id: uuid.UUID) -> dict[str, Any]:
    link = db.scalar(
        select(ImageShareLink)
        .join(Image, Image.id == ImageShareLink.image_id)
        .where(ImageShareLink.id == link_id, Image.project_id == ctx.project.id)
    )
    if link is None:
        raise NotFoundError("Link not found.")
    if link.revoked_at is None:
        link.revoked_at = utc_now()
        _event(db, ctx, "image.share_revoked", link)
        db.commit()
    return out(link)


def resolve(db: Session, token: str) -> Image | None:
    """The photo behind a working link, or None (unknown, ended, cancelled or withdrawn: all look the same)."""
    if not token or len(token) > 100:
        return None
    link = db.scalar(select(ImageShareLink).where(ImageShareLink.token_hash == _hash(token)))
    if link is None or link.revoked_at or link.expires_at <= utc_now():
        return None
    image = db.get(Image, link.image_id)
    if image is None or image.withdrawn_at or not image.preview_storage_key:
        return None
    return image
