"""AI analysis jobs and findings (database-schema.md sections 3.5 and 3.6).

A finding is a suspected problem. AI findings start as `ai_generated`: a suggestion only,
never a confirmed defect, until a technical reviewer checks it (P6). The AI's original
answer is kept in its own columns and can never be changed (a database trigger refuses).
"""

import uuid
from datetime import datetime
from decimal import Decimal

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, sql_in_list, updated_at_column, uuid_pk
from app.models.image import LOCATION_QUALITIES, LOCATION_SOURCES

JOB_STATUSES: tuple[str, ...] = ("queued", "processing", "completed", "failed")
FINDING_ORIGINS: tuple[str, ...] = ("ai", "manual")
REVIEW_STATUSES: tuple[str, ...] = (
    "ai_generated",
    "awaiting_review",
    "verified",
    "rejected",
    "needs_field_check",
    "merged",
)
INSPECTION_STATUSES: tuple[str, ...] = ("none", "planned", "inspected", "resolved")

# Columns the database refuses to change after a finding is created (FR-33).
PROTECTED_FINDING_COLUMNS: tuple[str, ...] = (
    "origin",
    "analysis_job_id",
    "detection_index",
    "predicted_type_key",
    "predicted_confidence",
    "predicted_bbox",
    "model_version",
    "original_location",
    "location_source",
)


class AnalysisJob(Base):
    """One request to analyse one photo with one AI model version."""

    __tablename__ = "analysis_jobs"
    __table_args__ = (
        # Re-running the same photo with the same model reuses this job (FR-21).
        UniqueConstraint("image_id", "model_version", name="uq_analysis_jobs_image_model"),
        CheckConstraint(f"status IN ({sql_in_list(JOB_STATUSES)})", name="status_allowed"),
        CheckConstraint("attempts >= 0", name="attempts_not_negative"),
        Index("ix_analysis_jobs_status", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # Indexed through the (image_id, model_version) unique constraint.
    image_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("images.id", ondelete="RESTRICT"))
    model_version: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="queued", server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failure_reason: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    queued_at: Mapped[datetime] = created_at_column()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Finding(Base):
    """One suspected or confirmed problem. AI original, location and review are kept apart."""

    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint(
            "analysis_job_id", "detection_index", name="uq_findings_job_detection_index"
        ),
        CheckConstraint(f"origin IN ({sql_in_list(FINDING_ORIGINS)})", name="origin_allowed"),
        CheckConstraint(
            f"review_status IN ({sql_in_list(REVIEW_STATUSES)})", name="review_status_allowed"
        ),
        CheckConstraint(
            f"inspection_status IN ({sql_in_list(INSPECTION_STATUSES)})",
            name="inspection_status_allowed",
        ),
        CheckConstraint(
            f"location_source IN ({sql_in_list(LOCATION_SOURCES)})", name="location_source_allowed"
        ),
        CheckConstraint(
            f"location_quality IN ({sql_in_list(LOCATION_QUALITIES)})",
            name="location_quality_allowed",
        ),
        # AI findings carry the full AI original; manual findings carry none of it.
        CheckConstraint(
            "(origin = 'ai') = (analysis_job_id IS NOT NULL AND detection_index IS NOT NULL"
            " AND predicted_type_key IS NOT NULL AND predicted_confidence IS NOT NULL"
            " AND predicted_bbox IS NOT NULL AND model_version IS NOT NULL)",
            name="ai_original_complete",
        ),
        CheckConstraint(
            "predicted_confidence IS NULL OR predicted_confidence BETWEEN 0 AND 1",
            name="confidence_range",
        ),
        CheckConstraint(
            "predicted_bbox IS NULL OR cardinality(predicted_bbox) = 4", name="bbox_four_values"
        ),
        # Verified needs a reviewed type, a severity, and the rubric version used (FR-31).
        CheckConstraint(
            "review_status <> 'verified' OR (type_key IS NOT NULL AND severity_key IS NOT NULL"
            " AND severity_rubric_id IS NOT NULL)",
            name="verified_needs_type_and_severity",
        ),
        CheckConstraint(
            "inspection_status = 'none' OR review_status = 'verified'",
            name="inspection_needs_verified",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_findings_project_review_status", "project_id", "review_status"),
        Index("ix_findings_original_location", "original_location", postgresql_using="gist"),
        Index("ix_findings_corrected_location", "corrected_location", postgresql_using="gist"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    origin: Mapped[str] = mapped_column(String(10))

    # AI original: written once, never changed.
    analysis_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_jobs.id", ondelete="RESTRICT"), index=True
    )
    detection_index: Mapped[int | None] = mapped_column(Integer)
    predicted_type_key: Mapped[str | None] = mapped_column(String(60))
    # An AI score from 0 to 1. NOT severity.
    predicted_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    predicted_bbox: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))
    model_version: Mapped[str | None] = mapped_column(String(60))

    # Location: the photo's approximate camera position, copied at creation and never changed.
    original_location: Mapped[WKBElement | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False)
    )
    location_source: Mapped[str] = mapped_column(String(20))
    corrected_location: Mapped[WKBElement | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False)
    )
    location_quality: Mapped[str] = mapped_column(String(30))

    # The reviewer's version (P6).
    type_key: Mapped[str | None] = mapped_column(String(60))
    severity_key: Mapped[str | None] = mapped_column(String(60))
    severity_rubric_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("severity_rubrics.id", ondelete="RESTRICT")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    review_status: Mapped[str] = mapped_column(String(30))
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT")
    )
    inspection_status: Mapped[str] = mapped_column(
        String(20), default="none", server_default="none"
    )

    # Goes up by 1 on every change; a save with an old number is refused (FR-35, P6).
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class FindingImage(Base):
    """Which photos show a finding. Normally one; several after a merge (P6)."""

    __tablename__ = "finding_images"

    # The pair is the key: a photo is linked to a finding at most once.
    finding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT"), primary_key=True
    )
    image_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("images.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    added_at: Mapped[datetime] = created_at_column()
