"""Organization settings catalogue: finding types and severity rubrics."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FindingType, SeverityRubric
from app.models.settings import PLACEHOLDER_FINDING_TYPES, PLACEHOLDER_SEVERITY_LEVELS


def seed_placeholder_settings(db: Session, organization_id: uuid.UUID) -> None:
    """Give a new organization the placeholder finding types and severity rubric v1.

    They are labelled as placeholders until the customer confirms them (PI-05, PI-06).
    """
    for key, label, source in PLACEHOLDER_FINDING_TYPES:
        db.add(
            FindingType(
                organization_id=organization_id,
                key=key,
                label=label,
                source=source,
                is_placeholder=True,
            )
        )
    db.add(
        SeverityRubric(
            organization_id=organization_id,
            version=1,
            levels=PLACEHOLDER_SEVERITY_LEVELS,
            is_placeholder=True,
            is_current=True,
        )
    )


def list_finding_types(
    db: Session, organization_id: uuid.UUID, *, active_only: bool = False
) -> list[FindingType]:
    query = select(FindingType).where(FindingType.organization_id == organization_id)
    if active_only:
        query = query.where(FindingType.is_active.is_(True))
    return list(db.scalars(query.order_by(FindingType.source, FindingType.label)).all())
