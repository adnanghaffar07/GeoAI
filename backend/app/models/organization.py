"""Organizations (customers) and who belongs to them."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, sql_in_list, updated_at_column, uuid_pk

# Allowed organization roles. What each role may do lives in app/core/permissions.py,
# never in the database (see permission-matrix.md section 6).
ORG_ROLES: tuple[str, ...] = ("org_admin", "org_manager", "org_member")


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_at_column()


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_membership_org_user"),
        CheckConstraint(f"org_role IN ({sql_in_list(ORG_ROLES)})", name="org_role_allowed"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    org_role: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
