"""Organization settings that the customer controls: finding types and severity rubrics.

Both follow the "versioned settings" rule: existing findings keep the key or rubric
version they were saved with, so changing settings never rewrites old records.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, sql_in_list, updated_at_column, uuid_pk

FINDING_SOURCES: tuple[str, ...] = ("ai", "manual")

# Placeholder catalogue (partner-inputs.md PI-05) until the customer confirms it.
PLACEHOLDER_FINDING_TYPES: tuple[tuple[str, str, str], ...] = (
    ("pothole", "Pothole", "ai"),
    ("surface_cracking", "Surface cracking", "ai"),
    ("pavement_deterioration", "Pavement deterioration", "ai"),
    ("sidewalk_observation", "Sidewalk observation", "manual"),
)

# Placeholder rubric (PI-06): level names only, no engineering definitions.
PLACEHOLDER_SEVERITY_LEVELS: list[dict[str, str]] = [
    {"key": "low", "label": "Low", "definition": ""},
    {"key": "medium", "label": "Medium", "definition": ""},
    {"key": "high", "label": "High", "definition": ""},
]


class FindingType(Base):
    __tablename__ = "finding_types"
    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="uq_finding_types_org_key"),
        CheckConstraint(f"source IN ({sql_in_list(FINDING_SOURCES)})", name="source_allowed"),
        CheckConstraint("key ~ '^[a-z][a-z0-9_]*$'", name="key_format"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    # Permanent code; never changes once used. The label can change safely.
    key: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(10))
    is_placeholder: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class SeverityRubric(Base):
    """A numbered version of the severity scale. Never edited; a change adds a version."""

    __tablename__ = "severity_rubrics"
    __table_args__ = (
        UniqueConstraint("organization_id", "version", name="uq_severity_rubrics_org_version"),
        # Exactly one current version per organization.
        Index(
            "uq_severity_rubrics_one_current",
            "organization_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    levels: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    is_placeholder: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = created_at_column()
