"""Enable the PostGIS extension.

Revision ID: 0001
Revises:
Create Date: 2026-10-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")


def downgrade() -> None:
    # Safe only while no table uses PostGIS types; later migrations depend on this one,
    # so Alembic always downgrades them first.
    op.execute("DROP EXTENSION IF EXISTS postgis")
