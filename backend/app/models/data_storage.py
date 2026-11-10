# ruff: noqa: E501
"""Where an organization keeps its files (team lead plan, Phase 2: bring your own storage)."""

import uuid
from datetime import datetime

from app.models.base import Base, updated_at_column
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column


class OrganizationStorage(Base):
    """No row (or kind "app"): the app's own private storage. Kind "s3": the organization's own S3-type storage
    (cloud account, or MinIO on its own computer/server). The secret key is kept encrypted."""

    __tablename__ = "organization_storage"
    __table_args__ = (CheckConstraint("kind IN ('app', 's3')", name="kind_allowed"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(10), default="app")
    endpoint: Mapped[str | None] = mapped_column(String(300))
    bucket: Mapped[str | None] = mapped_column(String(200))
    region: Mapped[str | None] = mapped_column(String(60))
    prefix: Mapped[str | None] = mapped_column(String(200))
    access_key_id: Mapped[str | None] = mapped_column(String(200))
    secret_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    location_note: Mapped[str | None] = mapped_column(String(200))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = updated_at_column()
