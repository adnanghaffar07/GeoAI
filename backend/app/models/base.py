"""Declarative base and shared column helpers for all models.

The naming convention gives every index and constraint a predictable name, so
Alembic migrations can create and drop them reliably.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utc_now() -> datetime:
    """Current time in UTC (all stored times are UTC)."""
    return datetime.now(UTC)


def uuid_pk() -> Mapped[uuid.UUID]:
    """Random UUID primary key (IDs cannot be guessed)."""
    return mapped_column(primary_key=True, default=uuid.uuid4)


def created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utc_now, server_default=func.now())


def updated_at_column() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )


def sql_in_list(values: tuple[str, ...]) -> str:
    """Render a tuple of allowed text values for a CHECK constraint."""
    return ", ".join(f"'{value}'" for value in values)
