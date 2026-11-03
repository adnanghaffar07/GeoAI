"""CR-006: "Ask about road risk" switch per project. Add-only: one new column, off by default.

Design: documentation/04-design/cr-006-ask-road-risk-proposal.md (approved 2026-11-02).

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-02 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0011'
down_revision: str | None = '0010'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('forecast_settings', sa.Column('assistant_enabled', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('forecast_settings', 'assistant_enabled')
