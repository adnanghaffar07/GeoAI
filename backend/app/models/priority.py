"""Inspection priority and inspections (database-schema.md section 3.7).

- `priority_configs`: numbered settings versions per project. A version is never edited;
  saving creates a new one, so earlier scores keep the settings they were calculated with.
- `priority_scores`: one score per verified finding and settings version, with the full
  breakdown (inputs, weights, contributions, missing inputs).
- `inspections`: a planned field check of a verified finding. Reopening creates a new
  inspection and keeps the old one as history.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, sql_in_list, updated_at_column, uuid_pk

INSPECTION_STATES: tuple[str, ...] = ("planned", "inspected", "resolved", "reopened")
ACTIVE_INSPECTION_STATES: tuple[str, ...] = ("planned", "inspected")


class PriorityConfig(Base):
    __tablename__ = "priority_configs"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_priority_configs_project_version"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("facility_radius_m > 0", name="radius_positive"),
        # At most one current version per project.
        Index(
            "uq_priority_configs_one_current",
            "project_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer)
    # {"severity": 0.5, "road_category": 0.3, "facility_proximity": 0.2}
    weights: Mapped[dict[str, float]] = mapped_column(JSONB)
    # Points (0-100) per severity level key and per road category.
    severity_points: Mapped[dict[str, float]] = mapped_column(JSONB)
    road_category_points: Mapped[dict[str, float]] = mapped_column(JSONB)
    facility_types: Mapped[list[str]] = mapped_column(ARRAY(String(60)), default=list)
    facility_radius_m: Mapped[int] = mapped_column(Integer)
    is_placeholder: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = created_at_column()


class PriorityScore(Base):
    __tablename__ = "priority_scores"
    __table_args__ = (
        UniqueConstraint(
            "finding_id", "priority_config_id", name="uq_priority_scores_finding_config"
        ),
        Index("ix_priority_scores_config_score", "priority_config_id", "score"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id", ondelete="RESTRICT"))
    priority_config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("priority_configs.id", ondelete="RESTRICT")
    )
    score: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB)
    computed_at: Mapped[datetime] = created_at_column()


class Inspection(Base):
    __tablename__ = "inspections"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in_list(INSPECTION_STATES)})", name="status_allowed"),
        # FR-44: resolved needs an outcome note or an evidence photo.
        CheckConstraint(
            "status <> 'resolved' OR outcome_note IS NOT NULL OR evidence_storage_key IS NOT NULL",
            name="resolved_needs_note_or_photo",
        ),
        # Only one open (planned or inspected) inspection per finding.
        Index(
            "uq_inspections_one_open_per_finding",
            "finding_id",
            unique=True,
            postgresql_where=text("status IN ('planned', 'inspected')"),
        ),
        Index("ix_inspections_finding_created", "finding_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id", ondelete="RESTRICT"))
    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    planned_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="planned", server_default="planned")
    outcome_note: Mapped[str | None] = mapped_column(Text)
    evidence_storage_key: Mapped[str | None] = mapped_column(Text)
    evidence_content_type: Mapped[str | None] = mapped_column(String(40))
    inspected_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    inspected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set on the old inspection when it is reopened: why, by whom, and the new inspection.
    reopen_reason: Mapped[str | None] = mapped_column(Text)
    reopened_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
