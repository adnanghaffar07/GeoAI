"""Reports and exports (database-schema.md section 3.8).

Every export is a row here, so it is logged: who asked, exactly which filters, whether
unreviewed data was included, which settings versions were used, and how many records.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, sql_in_list, uuid_pk

REPORT_FORMATS: tuple[str, ...] = ("csv", "geojson", "pdf")
REPORT_STATUSES: tuple[str, ...] = ("queued", "processing", "completed", "failed")


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(f"format IN ({sql_in_list(REPORT_FORMATS)})", name="format_allowed"),
        CheckConstraint(f"status IN ({sql_in_list(REPORT_STATUSES)})", name="status_allowed"),
        CheckConstraint("record_count IS NULL OR record_count >= 0", name="count_not_negative"),
        # Reports with unreviewed AI suggestions are never shared with viewers.
        CheckConstraint(
            "NOT (shared_with_viewers AND include_unreviewed)", name="unreviewed_never_shared"
        ),
        Index("ix_reports_project_created", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"))
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    format: Mapped[str] = mapped_column(String(10))
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    include_unreviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    settings_used: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued", server_default="queued")
    record_count: Mapped[int | None] = mapped_column(Integer)
    storage_key: Mapped[str | None] = mapped_column(Text)
    shared_with_viewers: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
