"""Audit history: one row per important action. Rows are only ever added."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ARRAY, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, uuid_pk


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_org_created", "organization_id", "created_at"),
        Index("ix_audit_events_action_created", "action", "created_at"),
        Index("ix_audit_events_project_created", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # Empty for events that happen before an organization is known (e.g. a failed sign-in).
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    # The actor's roles at the moment of the action, so history stays truthful
    # even if permissions change later.
    actor_roles: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    action: Mapped[str] = mapped_column(String(80))
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[uuid.UUID | None] = mapped_column()
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    request_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
