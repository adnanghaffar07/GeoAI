"""Review history (database-schema.md section 3.6, `review_events`).

One row per review action on a finding: who, when, their roles at that moment, what
changed (before and after) and the decision. Rows are only ever added; a database trigger
refuses updates and deletes (FR-34).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ARRAY, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, sql_in_list, uuid_pk

REVIEW_ACTIONS: tuple[str, ...] = (
    "create",
    "verify",
    "reject",
    "needs_field_check",
    "edit",
    "merge",
    "reopen_review",
)


class ReviewEvent(Base):
    __tablename__ = "review_events"
    __table_args__ = (
        CheckConstraint(f"action IN ({sql_in_list(REVIEW_ACTIONS)})", name="action_allowed"),
        CheckConstraint("finding_version >= 1", name="finding_version_positive"),
        Index("ix_review_events_finding_created", "finding_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id", ondelete="RESTRICT"))
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    # The person's roles at that moment, so history stays truthful if roles change later.
    actor_roles: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    action: Mapped[str] = mapped_column(String(30))
    # {"field": {"old": ..., "new": ...}} for every field that changed.
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    note: Mapped[str | None] = mapped_column(Text)
    finding_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at_column()
