"""Uploaded photos. The photo file itself is in private storage; this row describes it."""

import uuid
from datetime import datetime

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    ARRAY,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, sql_in_list, updated_at_column, uuid_pk

LOCATION_SOURCES: tuple[str, ...] = ("photo_gps", "device_gps", "manual", "none")
LOCATION_QUALITIES: tuple[str, ...] = ("approximate", "missing", "reviewer_confirmed")
IMAGE_STATUSES: tuple[str, ...] = ("stored", "withdrawn")

# Quality flags (text list, so new flags can be added without a schema change).
FLAG_MISSING_GPS = "missing_gps"
FLAG_INVALID_GPS = "invalid_gps"
FLAG_BLURRY = "blurry"
FLAG_TOO_DARK = "too_dark"
FLAG_OUTSIDE_PROJECT_AREA = "outside_project_area"
FLAG_CAPTURE_TIME_NO_TIMEZONE = "capture_time_no_timezone"
FLAG_NO_CAPTURE_TIME = "no_capture_time"


class Image(Base):
    __tablename__ = "images"
    __table_args__ = (
        # The same file cannot be added twice to a project (FR-13): retries return it.
        UniqueConstraint("project_id", "sha256", name="uq_images_project_sha256"),
        CheckConstraint(
            f"location_source IN ({sql_in_list(LOCATION_SOURCES)})", name="location_source_allowed"
        ),
        CheckConstraint(
            f"location_quality IN ({sql_in_list(LOCATION_QUALITIES)})",
            name="location_quality_allowed",
        ),
        CheckConstraint(f"status IN ({sql_in_list(IMAGE_STATUSES)})", name="status_allowed"),
        # A location source other than "none" always comes with a location, and the reverse.
        CheckConstraint(
            "(location_source = 'none') = (original_location IS NULL)",
            name="location_matches_source",
        ),
        Index("ix_images_original_location", "original_location", postgresql_using="gist"),
        Index("ix_images_project_created", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(300))
    preview_storage_key: Mapped[str | None] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(40))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    width_px: Mapped[int] = mapped_column(Integer)
    height_px: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Written once, never changed. Empty until GPS is known or a point is picked.
    original_location: Mapped[WKBElement | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False)
    )
    location_source: Mapped[str] = mapped_column(String(20))
    location_quality: Mapped[str] = mapped_column(String(30))
    quality_flags: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    status: Mapped[str] = mapped_column(String(20), default="stored", server_default="stored")
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
