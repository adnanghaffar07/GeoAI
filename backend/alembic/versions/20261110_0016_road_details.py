"""Road details on forecast sections (team lead plan, item 12, 2026-11-10).

Add-only: speed limit, lanes, surface, one-way and route number from OpenStreetMap. Filled by the hourly check.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-10 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0016'
down_revision: str | None = '0015'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ('speed_limit_mph', 'lanes', 'surface', 'oneway', 'road_ref', 'details_filled')


def upgrade() -> None:
    op.add_column('forecast_sections', sa.Column('speed_limit_mph', sa.Integer(), nullable=True))
    op.add_column('forecast_sections', sa.Column('lanes', sa.Integer(), nullable=True))
    op.add_column('forecast_sections', sa.Column('surface', sa.String(length=40), nullable=True))
    op.add_column('forecast_sections', sa.Column('oneway', sa.Boolean(), nullable=True))
    op.add_column('forecast_sections', sa.Column('road_ref', sa.String(length=60), nullable=True))
    op.add_column('forecast_sections', sa.Column('details_filled', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    for name in reversed(COLUMNS):
        op.drop_column('forecast_sections', name)
