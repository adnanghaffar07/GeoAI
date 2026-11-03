"""Personal notifications: "you have been asked to inspect" (owner request 2026-11-03).

Add-only for data: alerts.user_id (empty = a project alert for managers, as before) and the new alert
type inspection_assigned in the allowed list. Nothing existing changes.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-03 10:50:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0012'
down_revision: str | None = '0011'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "type IN ('turned_high', 'freeze_thaw_coming', 'heavy_rain_coming', 'data_problem')"
NEW = "type IN ('turned_high', 'freeze_thaw_coming', 'heavy_rain_coming', 'data_problem', 'inspection_assigned')"


def upgrade() -> None:
    op.add_column('alerts', sa.Column('user_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(op.f('fk_alerts_user_id_users'), 'alerts', 'users', ['user_id'], ['id'], ondelete='RESTRICT')
    op.create_index('ix_alerts_user_created', 'alerts', ['user_id', 'created_at'])
    op.drop_constraint(op.f('ck_alerts_type_allowed'), 'alerts', type_='check')
    op.create_check_constraint(op.f('ck_alerts_type_allowed'), 'alerts', NEW)


def downgrade() -> None:
    op.execute("DELETE FROM alert_reads WHERE alert_id IN (SELECT id FROM alerts WHERE user_id IS NOT NULL)")
    op.execute("DELETE FROM alerts WHERE user_id IS NOT NULL")
    op.drop_constraint(op.f('ck_alerts_type_allowed'), 'alerts', type_='check')
    op.create_check_constraint(op.f('ck_alerts_type_allowed'), 'alerts', OLD)
    op.drop_index('ix_alerts_user_created', table_name='alerts')
    op.drop_constraint(op.f('fk_alerts_user_id_users'), 'alerts', type_='foreignkey')
    op.drop_column('alerts', 'user_id')
