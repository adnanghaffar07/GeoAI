"""Inspection priority (FR-39 to FR-42).

- Only verified findings get a score. It is an *inspection* priority: it helps decide
  what to look at first. It does not decide repairs or compliance.
- Score (0-100) = sum over inputs of weight x points. Inputs: the reviewer's severity, the
  project's road category, and nearness to selected facilities.
- A missing input is never guessed: it adds nothing and is listed with the reason, and the
  breakdown shows how much of the weight had a value ("weight_covered").
- Settings are numbered versions per project; a new version never changes old scores.
  Placeholder values (PI-08) are used until the customer confirms theirs.
"""

import logging
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.auth import ProjectContext
from app.core.errors import ValidationFailedError
from app.models import Finding, PriorityConfig, PriorityScore, Project, User
from app.models.base import utc_now
from app.schemas.priority import (
    PriorityBreakdown,
    PriorityConfigIn,
    PriorityConfigOut,
    PriorityInput,
)
from app.services.audit import record_event
from app.services.findings import current_rubric
from app.services.projects import ensure_not_archived

log = logging.getLogger(__name__)

INPUT_LABELS = {
    "severity": "Reviewed severity",
    "road_category": "Road category",
    "facility_proximity": "Near selected facilities",
}

# Placeholder settings (partner-inputs.md PI-08, PI-09, PI-10) until the customer confirms.
PLACEHOLDER_WEIGHTS = {"severity": 0.5, "road_category": 0.3, "facility_proximity": 0.2}
PLACEHOLDER_ROAD_POINTS = {"arterial": 100.0, "collector": 70.0, "local": 40.0, "other": 20.0}
PLACEHOLDER_FACILITY_TYPES = ["school", "hospital"]
PLACEHOLDER_RADIUS_M = 200


def _placeholder_severity_points(levels: list[dict[str, Any]]) -> dict[str, float]:
    """Spread the scale's levels evenly from low to high (e.g. 3 levels -> 33, 67, 100)."""
    count = len(levels)
    return {level["key"]: round(100 * (index + 1) / count, 1) for index, level in enumerate(levels)}


def current_config(db: Session, project: Project) -> PriorityConfig:
    """The project's current settings; version 1 (placeholders) is created on first use."""
    query = select(PriorityConfig).where(
        PriorityConfig.project_id == project.id, PriorityConfig.is_current.is_(True)
    )
    config = db.scalar(query)
    if config is not None:
        return config
    rubric = current_rubric(db, project.organization_id)
    # Two first requests at the same moment: the second one's insert is skipped, and both
    # read the same version 1.
    db.execute(
        pg_insert(PriorityConfig)
        .values(
            id=uuid.uuid4(),
            project_id=project.id,
            version=1,
            weights=dict(PLACEHOLDER_WEIGHTS),
            severity_points=_placeholder_severity_points(rubric.levels),
            road_category_points=dict(PLACEHOLDER_ROAD_POINTS),
            facility_types=list(PLACEHOLDER_FACILITY_TYPES),
            facility_radius_m=PLACEHOLDER_RADIUS_M,
            is_placeholder=True,
            is_current=True,
        )
        .on_conflict_do_nothing(index_elements=["project_id", "version"])
    )
    db.commit()
    config = db.scalar(query)
    assert config is not None
    return config


def config_out(db: Session, config: PriorityConfig) -> PriorityConfigOut:
    name = (
        db.scalar(select(User.full_name).where(User.id == config.created_by))
        if config.created_by
        else None
    )
    return PriorityConfigOut(
        id=config.id,
        version=config.version,
        weights=config.weights,
        severity_points=config.severity_points,
        road_category_points=config.road_category_points,
        facility_types=list(config.facility_types),
        facility_radius_m=config.facility_radius_m,
        is_placeholder=config.is_placeholder,
        is_current=config.is_current,
        created_by_name=name,
        created_at=config.created_at,
    )


def list_configs(db: Session, project: Project) -> list[PriorityConfig]:
    current_config(db, project)
    db.commit()
    return list(
        db.scalars(
            select(PriorityConfig)
            .where(PriorityConfig.project_id == project.id)
            .order_by(PriorityConfig.version.desc())
        )
    )


def save_config(db: Session, ctx: ProjectContext, body: PriorityConfigIn) -> PriorityConfig:
    """Save a new settings version (audited). Scores for it are added on the next listing;
    scores made with earlier versions stay as they were."""
    ensure_not_archived(ctx)
    # Lock the project so two saves at the same moment get versions one after the other.
    db.execute(select(Project.id).where(Project.id == ctx.project.id).with_for_update())
    rubric = current_rubric(db, ctx.project.organization_id)
    unknown = set(body.severity_points) - {level["key"] for level in rubric.levels}
    if unknown:
        raise ValidationFailedError(
            "Severity points must use the levels of the current severity scale.",
            details={"unknown_levels": sorted(unknown)},
        )
    previous = current_config(db, ctx.project)
    db.refresh(previous)  # read it again now that the project is locked
    db.execute(select(Project.id).where(Project.id == ctx.project.id).with_for_update())
    previous.is_current = False
    db.flush()  # only one current version may exist at a time
    config = PriorityConfig(
        project_id=ctx.project.id,
        version=previous.version + 1,
        weights=body.weights,
        severity_points=body.severity_points,
        road_category_points=body.road_category_points,
        facility_types=body.facility_types,
        facility_radius_m=body.facility_radius_m,
        is_placeholder=body.is_placeholder,
        is_current=True,
        created_by=ctx.user.id,
    )
    db.add(config)
    db.flush()
    record_event(
        db,
        action="priority_config.created",
        organization_id=ctx.project.organization_id,
        project_id=ctx.project.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="priority_config",
        target_id=config.id,
        details={
            "version": config.version,
            "previous_version": previous.version,
            "weights": body.weights,
            "severity_points": body.severity_points,
            "road_category_points": body.road_category_points,
            "facility_types": body.facility_types,
            "facility_radius_m": body.facility_radius_m,
            "is_placeholder": body.is_placeholder,
        },
    )
    db.commit()
    db.refresh(config)
    return config


# ----------------------------------------------------------------- scoring
def compute(
    finding: Finding, project: Project, config: PriorityConfig
) -> tuple[float, PriorityBreakdown]:
    """The score and its full breakdown. Missing inputs add nothing and are explained."""
    inputs: list[PriorityInput] = []

    def add(key: str, value: str | None, points: float | None, reason: str | None) -> None:
        weight = float(config.weights.get(key, 0))
        missing = points is None
        inputs.append(
            PriorityInput(
                key=key,
                label=INPUT_LABELS[key],
                value=value,
                points=points,
                weight=weight,
                contribution=None if missing else round(weight * points, 2),  # type: ignore[operator]
                missing=missing,
                reason=reason,
            )
        )

    severity = finding.severity_key
    if severity is None:
        add("severity", None, None, "No severity was chosen.")
    elif severity not in config.severity_points:
        add("severity", severity, None, f"The settings give no points for severity '{severity}'.")
    else:
        add("severity", severity, float(config.severity_points[severity]), None)

    road = project.road_category
    if not road:
        add("road_category", None, None, "The project has no road category set.")
    elif road not in config.road_category_points:
        add("road_category", road, None, f"The settings give no points for road category '{road}'.")
    else:
        add("road_category", road, float(config.road_category_points[road]), None)

    types = ", ".join(config.facility_types) or "facilities"
    add(
        "facility_proximity",
        None,
        None,
        f"No facility map is loaded yet (partner input PI-10), so nearness to {types} within "
        f"{config.facility_radius_m} m cannot be checked.",
    )

    score = round(sum(item.contribution or 0 for item in inputs), 2)
    covered = round(sum(item.weight for item in inputs if not item.missing), 4)
    return score, PriorityBreakdown(
        inputs=inputs, weight_covered=covered, missing=[item.key for item in inputs if item.missing]
    )


def scores_for(
    db: Session, project: Project, findings: list[Finding], *, keep: bool = True
) -> tuple[PriorityConfig, dict[uuid.UUID, tuple[float, PriorityBreakdown]]]:
    """Score verified findings with the current settings.

    With `keep`, the results are stored: one score per finding and settings version,
    updated if the finding's inputs changed (e.g. a new severity); a new settings version
    gets new rows. Two requests at the same moment never clash (insert-or-update).
    """
    config = current_config(db, project)
    results = {
        finding.id: compute(finding, project, config)
        for finding in findings
        if finding.review_status == "verified"
    }
    if not keep or not results:
        return config, results
    stored = {
        row.finding_id: row
        for row in db.scalars(
            select(PriorityScore).where(
                PriorityScore.priority_config_id == config.id,
                PriorityScore.finding_id.in_(list(results)),
            )
        )
    }
    for finding_id, (score, breakdown) in results.items():
        data = breakdown.model_dump()
        row = stored.get(finding_id)
        if row is not None and float(row.score) == score and row.breakdown == data:
            continue  # unchanged: nothing to write
        statement = pg_insert(PriorityScore).values(
            id=uuid.uuid4(),
            finding_id=finding_id,
            priority_config_id=config.id,
            score=Decimal(str(score)),
            breakdown=data,
            computed_at=utc_now(),
        )
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["finding_id", "priority_config_id"],
                set_={
                    "score": statement.excluded.score,
                    "breakdown": statement.excluded.breakdown,
                    "computed_at": statement.excluded.computed_at,
                },
            )
        )
    db.commit()
    return config, results
