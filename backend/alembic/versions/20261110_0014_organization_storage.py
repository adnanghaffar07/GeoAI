"""Bring your own storage (team lead plan, Phase 2, 2026-11-10).

Add-only: the new table organization_storage. No row means the app's own storage, as before.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-10 06:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0014'
down_revision: str | None = '0013'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'organization_storage',
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('endpoint', sa.String(length=300), nullable=True),
        sa.Column('bucket', sa.String(length=200), nullable=True),
        sa.Column('region', sa.String(length=60), nullable=True),
        sa.Column('prefix', sa.String(length=200), nullable=True),
        sa.Column('access_key_id', sa.String(length=200), nullable=True),
        sa.Column('secret_encrypted', sa.LargeBinary(), nullable=True),
        sa.Column('location_note', sa.String(length=200), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("kind IN ('app', 's3')", name=op.f('ck_organization_storage_kind_allowed')),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_organization_storage_organization_id_organizations'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_organization_storage_updated_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('organization_id', name=op.f('pk_organization_storage')),
    )


def downgrade() -> None:
    op.drop_table('organization_storage')
