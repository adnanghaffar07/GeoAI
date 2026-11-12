"""Projects deleted by an organization admin (owner, 2026-11-12).

Add-only: projects.deleted_at. A deleted project is hidden everywhere; nothing is erased.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-12 06:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = '0017'
down_revision: str | None = '0016'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # IF NOT EXISTS: the column may already be there from an earlier start (owner run, 2026-11-12).
    op.execute('ALTER TABLE projects ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE')


def downgrade() -> None:
    op.execute('ALTER TABLE projects DROP COLUMN IF EXISTS deleted_at')
