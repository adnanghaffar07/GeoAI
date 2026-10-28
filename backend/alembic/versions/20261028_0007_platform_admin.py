"""Platform admin flag on users (CR-004).

Add-only: every existing account gets False, so nothing changes until an operator runs
`python -m app.cli make-platform-admin --email ...`.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_platform_admin", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "is_platform_admin")
