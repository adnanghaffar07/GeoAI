"""Terms accepted after sign-in (team lead plan, Phase 1, 2026-11-10).

Add-only: the new table user_agreements. Nothing existing changes.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-10 04:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0013'
down_revision: str | None = '0012'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'user_agreements',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('version', sa.String(length=40), nullable=False),
        sa.Column('remember', sa.Boolean(), nullable=False),
        sa.Column('session_id', sa.Uuid(), nullable=True),
        sa.Column('accepted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_agreements_user_id_users'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], name=op.f('fk_user_agreements_session_id_sessions'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_user_agreements')),
    )
    op.create_index('ix_user_agreements_user_version', 'user_agreements', ['user_id', 'version'])


def downgrade() -> None:
    op.drop_index('ix_user_agreements_user_version', table_name='user_agreements')
    op.drop_table('user_agreements')
