"""Shareable photo links (team lead plan, item 9, 2026-11-10).

Add-only: the new table image_share_links.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-10 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0015'
down_revision: str | None = '0014'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'image_share_links',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('image_id', sa.Uuid(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['image_id'], ['images.id'], name=op.f('fk_image_share_links_image_id_images'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_image_share_links_created_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_image_share_links')),
        sa.UniqueConstraint('token_hash', name=op.f('uq_image_share_links_token_hash')),
    )
    op.create_index(op.f('ix_image_share_links_image_id'), 'image_share_links', ['image_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_image_share_links_image_id'), table_name='image_share_links')
    op.drop_table('image_share_links')
