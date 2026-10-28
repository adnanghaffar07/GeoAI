"""Requests from new organizations to use the app (CR-004).

Anyone may send a request from the public "Request access" page. Nothing is created
until a platform admin approves it; then the organization and an invitation for its
first admin are created in the same transaction.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, sql_in_list, uuid_pk

REQUEST_STATUSES: tuple[str, ...] = ("pending", "approved", "rejected")


class OrganizationRequest(Base):
    __tablename__ = "organization_requests"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in_list(REQUEST_STATUSES)})", name="status_allowed"),
        Index("ix_organization_requests_status_created", "status", "created_at"),
        # One waiting request per email at a time.
        Index(
            "uq_organization_requests_pending_email",
            text("lower(contact_email)"),
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str] = mapped_column(String(200))
    contact_email: Mapped[str] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40))
    city_or_agency: Mapped[str] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    # Only for the spam limit (requests per address per hour).
    requester_ip: Mapped[str | None] = mapped_column(String(64))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = created_at_column()
