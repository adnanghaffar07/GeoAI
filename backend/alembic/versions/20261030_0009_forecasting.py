"""Road-risk forecasting in the app (F4b). Add-only: new tables and one new optional column.

Design: documentation/04-design/forecasting-f4b-design.md (approved 2026-10-30).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-30 10:40:00
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column:
    return sa.Column('id', sa.Uuid(), nullable=False)


def _created(name: str = 'created_at') -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False)


def upgrade() -> None:
    op.create_table('forecast_settings',
    _id(),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('enabled', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('level', sa.Integer(), nullable=False),
    sa.Column('area_key', sa.String(length=60), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='setting_up', nullable=False),
    sa.Column('area_km2', sa.Float(), nullable=True),
    sa.Column('last_weekly_run', sa.Date(), nullable=True),
    sa.Column('last_daily_run', sa.Date(), nullable=True),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('changed_by', sa.Uuid(), nullable=False),
    _created(),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('level IN (1, 2)', name=op.f('ck_forecast_settings_level_allowed')),
    sa.CheckConstraint("status IN ('setting_up', 'ready', 'failed', 'too_large', 'off')", name=op.f('ck_forecast_settings_status_allowed')),
    sa.CheckConstraint('area_km2 IS NULL OR area_km2 >= 0', name=op.f('ck_forecast_settings_area_not_negative')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_forecast_settings_project_id_projects'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['changed_by'], ['users.id'], name=op.f('fk_forecast_settings_changed_by_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_forecast_settings')),
    sa.UniqueConstraint('project_id', name='uq_forecast_settings_project')
    )
    op.create_table('forecast_sections',
    _id(),
    sa.Column('area_key', sa.String(length=60), nullable=False),
    sa.Column('section_key', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=True),
    sa.Column('road_type', sa.String(length=40), nullable=False),
    sa.Column('length_m', sa.Float(), nullable=False),
    sa.Column('line', geoalchemy2.types.Geometry(geometry_type='LINESTRING', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    _created(),
    sa.CheckConstraint('length_m > 0', name=op.f('ck_forecast_sections_length_positive')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_forecast_sections')),
    sa.UniqueConstraint('area_key', 'section_key', name='uq_forecast_sections_area_section')
    )
    op.create_index('ix_forecast_sections_line', 'forecast_sections', ['line'], unique=False, postgresql_using='gist')
    op.create_table('risk_runs',
    _id(),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('as_of', sa.Date(), nullable=False),
    sa.Column('model_version', sa.String(length=60), nullable=False),
    sa.Column('data_dates', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='running', nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    _created('started_at'),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("kind IN ('setup', 'weekly_levels', 'daily_factors', 'outlook', 'monitor')", name=op.f('ck_risk_runs_kind_allowed')),
    sa.CheckConstraint("status IN ('running', 'completed', 'failed')", name=op.f('ck_risk_runs_status_allowed')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_risk_runs_project_id_projects'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_risk_runs'))
    )
    op.create_index('ix_risk_runs_project_kind_as_of', 'risk_runs', ['project_id', 'kind', 'as_of'], unique=False)
    op.create_table('risk_levels',
    _id(),
    sa.Column('run_id', sa.Uuid(), nullable=False),
    sa.Column('section_id', sa.Uuid(), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=False),
    sa.Column('level', sa.String(length=10), nullable=False),
    sa.Column('reasons', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('missing_inputs', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('monitor_value', sa.Float(), nullable=True),
    sa.CheckConstraint("level IN ('high', 'medium', 'low')", name=op.f('ck_risk_levels_level_allowed')),
    sa.CheckConstraint('rank >= 1', name=op.f('ck_risk_levels_rank_positive')),
    sa.ForeignKeyConstraint(['run_id'], ['risk_runs.id'], name=op.f('fk_risk_levels_run_id_risk_runs'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['section_id'], ['forecast_sections.id'], name=op.f('fk_risk_levels_section_id_forecast_sections'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_risk_levels')),
    sa.UniqueConstraint('run_id', 'section_id', name='uq_risk_levels_run_section')
    )
    op.create_index('ix_risk_levels_run_rank', 'risk_levels', ['run_id', 'rank'], unique=False)
    op.create_table('risk_factor_values',
    _id(),
    sa.Column('run_id', sa.Uuid(), nullable=False),
    sa.Column('section_id', sa.Uuid(), nullable=False),
    sa.Column('factor', sa.String(length=40), nullable=False),
    sa.Column('value', sa.Float(), nullable=True),
    sa.Column('level', sa.String(length=10), nullable=False),
    sa.Column('kind', sa.String(length=12), nullable=False),
    sa.CheckConstraint("level IN ('high', 'medium', 'low', 'missing')", name=op.f('ck_risk_factor_values_level_allowed')),
    sa.CheckConstraint("kind IN ('risk', 'background')", name=op.f('ck_risk_factor_values_kind_allowed')),
    sa.ForeignKeyConstraint(['run_id'], ['risk_runs.id'], name=op.f('fk_risk_factor_values_run_id_risk_runs'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['section_id'], ['forecast_sections.id'], name=op.f('fk_risk_factor_values_section_id_forecast_sections'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_risk_factor_values')),
    sa.UniqueConstraint('run_id', 'section_id', 'factor', name='uq_risk_factor_values_run_section_factor')
    )
    op.create_table('weather_outlooks',
    _id(),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('source', sa.String(length=120), nullable=False),
    sa.Column('days', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('freeze_thaw_days', sa.Integer(), nullable=False),
    sa.Column('frost_days', sa.Integer(), nullable=False),
    sa.Column('heavy_rain_days', sa.Integer(), nullable=False),
    sa.Column('snow_mm', sa.Float(), nullable=False),
    _created('fetched_at'),
    sa.CheckConstraint('freeze_thaw_days >= 0 AND frost_days >= 0 AND heavy_rain_days >= 0', name=op.f('ck_weather_outlooks_counts_not_negative')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_weather_outlooks_project_id_projects'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_weather_outlooks'))
    )
    op.create_index('ix_weather_outlooks_project_issued', 'weather_outlooks', ['project_id', 'issued_at'], unique=False)
    op.create_table('alerts',
    _id(),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('type', sa.String(length=30), nullable=False),
    sa.Column('event_key', sa.String(length=120), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('run_id', sa.Uuid(), nullable=True),
    _created(),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("type IN ('turned_high', 'freeze_thaw_coming', 'heavy_rain_coming', 'data_problem')", name=op.f('ck_alerts_type_allowed')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_alerts_project_id_projects'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['run_id'], ['risk_runs.id'], name=op.f('fk_alerts_run_id_risk_runs'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_alerts'))
    )
    op.create_index('uq_alerts_one_open_per_event', 'alerts', ['project_id', 'event_key'], unique=True, postgresql_where=sa.text('closed_at IS NULL'))
    op.create_index('ix_alerts_project_created', 'alerts', ['project_id', 'created_at'], unique=False)
    op.create_table('alert_reads',
    _id(),
    sa.Column('alert_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    _created('read_at'),
    sa.ForeignKeyConstraint(['alert_id'], ['alerts.id'], name=op.f('fk_alert_reads_alert_id_alerts'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_alert_reads_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_alert_reads')),
    sa.UniqueConstraint('alert_id', 'user_id', name='uq_alert_reads_alert_user')
    )
    op.create_table('forecast_monitoring',
    _id(),
    sa.Column('area_key', sa.String(length=60), nullable=False),
    sa.Column('month', sa.Date(), nullable=False),
    sa.Column('model_version', sa.String(length=60), nullable=False),
    sa.Column('sections', sa.Integer(), nullable=False),
    sa.Column('groups', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('largest_gap', sa.Float(), nullable=True),
    sa.Column('within_rule', sa.Boolean(), nullable=True),
    _created(),
    sa.CheckConstraint('sections >= 0', name=op.f('ck_forecast_monitoring_sections_not_negative')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_forecast_monitoring')),
    sa.UniqueConstraint('area_key', 'month', 'model_version', name='uq_forecast_monitoring_area_month')
    )
    op.add_column('inspections', sa.Column('risk_level_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(op.f('fk_inspections_risk_level_id_risk_levels'), 'inspections', 'risk_levels', ['risk_level_id'], ['id'], ondelete='RESTRICT')


def downgrade() -> None:
    op.drop_constraint(op.f('fk_inspections_risk_level_id_risk_levels'), 'inspections', type_='foreignkey')
    op.drop_column('inspections', 'risk_level_id')
    op.drop_table('forecast_monitoring')
    op.drop_table('alert_reads')
    op.drop_index('ix_alerts_project_created', table_name='alerts')
    op.drop_index('uq_alerts_one_open_per_event', table_name='alerts', postgresql_where=sa.text('closed_at IS NULL'))
    op.drop_table('alerts')
    op.drop_index('ix_weather_outlooks_project_issued', table_name='weather_outlooks')
    op.drop_table('weather_outlooks')
    op.drop_table('risk_factor_values')
    op.drop_index('ix_risk_levels_run_rank', table_name='risk_levels')
    op.drop_table('risk_levels')
    op.drop_index('ix_risk_runs_project_kind_as_of', table_name='risk_runs')
    op.drop_table('risk_runs')
    op.drop_index('ix_forecast_sections_line', table_name='forecast_sections')
    op.drop_table('forecast_sections')
    op.drop_table('forecast_settings')
