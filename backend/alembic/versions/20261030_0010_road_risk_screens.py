"""Road risk screens (F4d). Nothing is deleted; existing inspections keep their finding.

Design: documentation/04-design/forecasting-f4d-design.md (approved 2026-10-30), section 2.

- forecast_settings.visible_to_roles: who else (besides project managers) can see road risk.
- inspections.project_id: the project of every inspection (existing rows copied from their finding).
- inspections.section_id: a road inspection is linked to a road section instead of a finding.
- inspections.finding_id may now be empty, with the rule: exactly one of finding or road section.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-30 14:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0010'
down_revision: str | None = '0009'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('forecast_settings', sa.Column(
        'visible_to_roles', postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text('\'["technical_reviewer", "viewer"]\'::jsonb'), nullable=False,
    ))

    op.add_column('inspections', sa.Column('project_id', sa.Uuid(), nullable=True))
    op.execute(
        'UPDATE inspections i SET project_id = f.project_id FROM findings f WHERE f.id = i.finding_id'
    )
    op.alter_column('inspections', 'project_id', nullable=False)
    op.create_foreign_key(op.f('fk_inspections_project_id_projects'), 'inspections', 'projects', ['project_id'], ['id'], ondelete='RESTRICT')
    op.create_index('ix_inspections_project_created', 'inspections', ['project_id', 'created_at'])

    op.add_column('inspections', sa.Column('section_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(op.f('fk_inspections_section_id_forecast_sections'), 'inspections', 'forecast_sections', ['section_id'], ['id'], ondelete='RESTRICT')
    op.alter_column('inspections', 'finding_id', nullable=True)
    op.create_check_constraint(
        op.f('ck_inspections_finding_or_section'), 'inspections',
        '(finding_id IS NULL) <> (section_id IS NULL)',
    )
    op.create_index(
        'uq_inspections_one_open_per_section', 'inspections', ['project_id', 'section_id'],
        unique=True, postgresql_where=sa.text("section_id IS NOT NULL AND status IN ('planned', 'inspected')"),
    )


def downgrade() -> None:
    road = op.get_bind().execute(sa.text('SELECT count(*) FROM inspections WHERE section_id IS NOT NULL')).scalar()
    if road:
        raise RuntimeError(
            f'{road} road inspections exist; they would be lost. Downgrade refused (nothing changed).'
        )
    op.drop_index('uq_inspections_one_open_per_section', table_name='inspections', postgresql_where=sa.text("section_id IS NOT NULL AND status IN ('planned', 'inspected')"))
    op.drop_constraint(op.f('ck_inspections_finding_or_section'), 'inspections', type_='check')
    op.alter_column('inspections', 'finding_id', nullable=False)
    op.drop_constraint(op.f('fk_inspections_section_id_forecast_sections'), 'inspections', type_='foreignkey')
    op.drop_column('inspections', 'section_id')
    op.drop_index('ix_inspections_project_created', table_name='inspections')
    op.drop_constraint(op.f('fk_inspections_project_id_projects'), 'inspections', type_='foreignkey')
    op.drop_column('inspections', 'project_id')
    op.drop_column('forecast_settings', 'visible_to_roles')
