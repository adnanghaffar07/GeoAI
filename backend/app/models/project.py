"""Survey projects and who works on them."""

import uuid
from datetime import date, datetime

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, sql_in_list, updated_at_column, uuid_pk

# Allowed project roles. What each role may do lives in app/core/permissions.py.
PROJECT_ROLES: tuple[str, ...] = (
    "project_manager",
    "field_collector",
    "technical_reviewer",
    "viewer",
)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("cardinality(finding_type_keys) >= 1", name="has_finding_types"),
        CheckConstraint(
            "survey_end IS NULL OR survey_start IS NULL OR survey_end >= survey_start",
            name="survey_dates_in_order",
        ),
        Index("ix_projects_boundary", "boundary", postgresql_using="gist"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    # Survey area in WGS 84 longitude/latitude.
    boundary: Mapped[WKBElement] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False)
    )
    finding_type_keys: Mapped[list[str]] = mapped_column(ARRAY(String(60)))
    road_category: Mapped[str | None] = mapped_column(String(60))
    survey_start: Mapped[date | None] = mapped_column(Date)
    survey_end: Mapped[date | None] = mapped_column(Date)
    partner_reference: Mapped[str | None] = mapped_column(String(120))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class ProjectMember(Base):
    """One row per role a person holds on a project, so roles can be combined (Q2)."""

    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", "role", name="uq_project_members_role"),
        CheckConstraint(f"role IN ({sql_in_list(PROJECT_ROLES)})", name="role_allowed"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    role: Mapped[str] = mapped_column(String(40))
    added_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = created_at_column()
