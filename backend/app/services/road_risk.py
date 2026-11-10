"""Road risk for the screens (F4c; api-spec.md section 3.10, forecasting-f4-plan.md section 4).

Reads the results the background jobs (`app.services.forecasting`, F4b) stored in the app
database. Owner decision F4-D2 (2026-10-30): **levels only**: high / medium / low and the main
reasons, never a percentage, and never the raw model value (`risk_levels.monitor_value` is only
for the monthly check).

- Level 2 (Chicago): the weekly B1 levels; sections are listed riskiest first.
- Level 1 (other areas): risk factors only; sections are listed by their highest risk factor
  (the number of "high", then "medium" risk factors), and the level shown is that factor level.
"""

import json
import logging
import statistics
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.auth import ProjectContext
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.core.permissions import Perm
from app.models import (
    Alert,
    AlertRead,
    ForecastSection,
    ForecastSettings,
    Inspection,
    Project,
    ProjectMember,
    RiskFactorValue,
    RiskLevel,
    RiskRun,
    User,
    WeatherOutlook,
)
from app.models.forecast import DEFAULT_VISIBLE_ROLES, VISIBILITY_ROLES
from app.schemas.road_risk import (
    AlertOut,
    FactorOut,
    ForecastStatusOut,
    HistoryPoint,
    LevelCounts,
    LinkedInspection,
    OutlookOut,
    ReasonOut,
    RecentWeatherOut,
    RunOut,
    SectionRiskOut,
)
from app.services import forecasting
from app.services.audit import record_event
from app.services.projects import ensure_not_archived

log = logging.getLogger(__name__)

LEVEL_LABELS = {1: "Risk factors only (no pothole history here)", 2: "Tested Chicago risk levels"}


def level_label(row: Any) -> str | None:
    """Level 2 outside Chicago: the Chicago model, tested on the city's own reports."""
    if row.level == 2 and row.area_key != forecasting.CHICAGO:
        return "Tested risk levels (Chicago model, tested on this city's reports)"
    return LEVEL_LABELS.get(row.level)


LEVEL_ORDER = {"high": 0, "medium": 1, "low": 2, "missing": 3}
WEATHER_FACTORS = (
    "freeze_thaw_14d",
    "below_freezing_days_30d",
    "snow_mm_30d",
    "heavy_rain_days_30d",
)
NOTIFICATION_LIMIT = 50

# Plain words for the model inputs and risk factors (names from ml/forecasting).
LABELS: dict[str, str] = {
    "reports_7d": "Pothole reports here, last 7 days",
    "reports_14d": "Pothole reports here, last 14 days",
    "reports_30d": "Pothole reports here, last 30 days",
    "reports_90d": "Pothole reports here, last 90 days",
    "reports_365d": "Pothole reports here, last 12 months",
    "reports_same_30d_last_year": "Pothole reports here, same 30 days last year",
    "reports_all_before": "Pothole reports here since records began",
    "reports_same_season_3y": "Pothole reports here in the same season, past 3 years",
    "years_with_reports_5y": "Years with pothole reports, past 5 years",
    "duplicate_reports_30d": "Repeat reports of the same pothole, last 30 days",
    "duplicate_reports_90d": "Repeat reports of the same pothole, last 90 days",
    "days_since_last_report": "Days since the last pothole report",
    "neighbour_reports_7d": "Reports on nearby roads (200 m), last 7 days",
    "neighbour_reports_30d": "Reports on nearby roads (200 m), last 30 days",
    "neighbour_reports_90d": "Reports on nearby roads (200 m), last 90 days",
    "neighbour_reports_365d": "Reports on nearby roads (200 m), last 12 months",
    "freeze_thaw_7d": "Freeze-thaw days, last 7 days",
    "freeze_thaw_14d": "Freeze-thaw days, last 14 days",
    "freeze_thaw_30d": "Freeze-thaw days, last 30 days",
    "below_freezing_days_30d": "Days below freezing, last 30 days",
    "rain_mm_7d": "Rain, last 7 days (mm)",
    "rain_mm_30d": "Rain, last 30 days (mm)",
    "heavy_rain_days_30d": "Heavy-rain days (25 mm or more), last 30 days",
    "snow_mm_7d": "Snow, last 7 days (mm)",
    "snow_mm_30d": "Snow, last 30 days (mm)",
    "hot_days_30d": "Hot days, last 30 days",
    "days_since_freeze": "Days since the last frost",
    "highway_code": "Road type",
    "length_m": "Section length (m)",
    "lanes": "Number of lanes",
    "surface_code": "Road surface",
    "slope_pct": "Slope (%)",
    "low_spot_m": "Low spot (m below its surroundings)",
    "flood_1pct": "In a 1% (100-year) flood zone",
    "flood_02pct": "In a 0.2% (500-year) flood zone",
    "flood_zone": "Flood zone",
    "probably_bridge": "Probably a bridge",
    "traffic_band": "Traffic (how busy the road is)",
    "heavy_vehicle_band": "Heavy vehicles (trucks and buses)",
    "bus_routes": "Bus routes on this road",
    "road_roughness": "Road roughness, measured by the state (IRI)",
    "cracking": "Cracking, measured by the state (% of the lane)",
    "rutting": "Rutting, measured by the state (inches)",
    "week_of_year": "Time of year",
    "month": "Month",
    "new_311_system": "Reported through the new 311 system",
}


def label(name: str) -> str:
    return LABELS.get(name, name.replace("_", " ").capitalize())


# ------------------------------------------------------------------ settings
def _settings(db: Session, project_id: uuid.UUID) -> ForecastSettings | None:
    return db.scalar(select(ForecastSettings).where(ForecastSettings.project_id == project_id))


def visible_roles(row: ForecastSettings | None) -> list[str]:
    """The roles, besides project managers, that can see road risk in the project."""
    roles = DEFAULT_VISIBLE_ROLES if row is None else row.visible_to_roles
    return [role for role in VISIBILITY_ROLES if role in roles]


def can_view(db: Session, ctx: ProjectContext) -> bool:
    """`risk.view` and, for reviewers, viewers and field collectors, the project's setting
    (CONDITIONS "project_setting"; owner request 2026-10-30). Managers and org admins always."""
    if not ctx.has(Perm.RISK_VIEW):
        return False
    if ctx.is_unconditional(Perm.RISK_VIEW):
        return True
    allowed = set(visible_roles(_settings(db, ctx.project.id)))
    return any(role in allowed for role in ctx.project_roles)


def effective_permissions(db: Session, ctx: ProjectContext) -> frozenset[str]:
    """The caller's permissions with `risk.view` removed where the project hides road risk."""
    if Perm.RISK_VIEW in ctx.permissions and not can_view(db, ctx):
        return ctx.permissions - {Perm.RISK_VIEW}
    return ctx.permissions


def is_enabled(db: Session, project_id: uuid.UUID) -> bool:
    row = _settings(db, project_id)
    return bool(row and row.enabled)


def status_out(db: Session, ctx: ProjectContext) -> ForecastStatusOut:
    row = _settings(db, ctx.project.id)
    limit = get_settings().forecast_max_area_km2
    can = ctx.has(Perm.RISK_CONFIGURE)
    if row is None:
        return ForecastStatusOut(
            visible_to_roles=visible_roles(None),
            enabled=False,
            status="off",
            level=None,
            level_label=None,
            message=None,
            area_km2=None,
            max_area_km2=limit,
            last_weekly_run=None,
            last_daily_run=None,
            can_configure=can,
        )
    ready = row.status == "ready"
    return ForecastStatusOut(
        visible_to_roles=visible_roles(row),
        assistant_enabled=row.assistant_enabled,
        enabled=row.enabled,
        status=row.status,
        level=row.level if ready else None,
        level_label=level_label(row) if ready else None,
        message=row.message,
        area_km2=row.area_km2,
        max_area_km2=limit,
        last_weekly_run=row.last_weekly_run,
        last_daily_run=row.last_daily_run,
        can_configure=can,
    )


def _audit(db: Session, ctx: ProjectContext, action: str, row_id: Any, **details: Any) -> None:
    record_event(
        db,
        action=action,
        organization_id=ctx.project.organization_id,
        project_id=ctx.project.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="forecast_settings",
        target_id=row_id,
        details=details,
    )


QUEUE_DOWN = (
    "Set-up could not start: the background worker could not be reached. "
    "Switch forecasting on again to retry."
)


def set_enabled(
    db: Session, ctx: ProjectContext, enabled: bool, send: Callable[[uuid.UUID], None]
) -> None:
    """Switch forecasting on (the area is set up in the background) or off (results are kept)."""
    ensure_not_archived(ctx)
    row = _settings(db, ctx.project.id)
    if not enabled:
        if row is not None and row.enabled:
            _audit(db, ctx, "forecast.disabled", row.id)
            forecasting.disable(db, ctx.project.id, ctx.user.id)
        return
    if row is not None and row.enabled and row.status in ("ready", "setting_up"):
        return  # already on: nothing to do (no second set-up)
    _audit(db, ctx, "forecast.enabled", row.id if row else None)
    row = forecasting.enable(db, ctx.project.id, ctx.user.id)
    if row.status != "setting_up":
        return  # e.g. too_large: the message says why
    try:
        send(row.id)
    except Exception:  # any queue problem means the same thing to the user
        log.warning("Could not queue forecast set-up %s", row.id, exc_info=True)
        row.status, row.message = "failed", QUEUE_DOWN
        db.commit()


def set_visibility(db: Session, ctx: ProjectContext, roles: list[str]) -> None:
    """Who else can see road risk (project managers always can). Recorded in the history."""
    ensure_not_archived(ctx)
    wanted = [role for role in VISIBILITY_ROLES if role in roles]
    row = _settings(db, ctx.project.id)
    before = visible_roles(row)
    if wanted == before:
        return
    if row is None:  # not switched on yet: keep the choice for when it is
        row = ForecastSettings(
            project_id=ctx.project.id,
            enabled=False,
            level=1,
            area_key="pending",
            status="off",
            changed_by=ctx.user.id,
        )
        db.add(row)
        db.flush()
    row.visible_to_roles, row.changed_by = wanted, ctx.user.id
    _audit(db, ctx, "forecast.visibility_changed", row.id, before=before, after=wanted)
    db.commit()


def set_assistant(db: Session, ctx: ProjectContext, on: bool) -> None:
    """CR-006: switch "Ask about road risk" on or off (needs road risk on to be used)."""
    ensure_not_archived(ctx)
    row = _settings(db, ctx.project.id)
    if row is None:
        row = ForecastSettings(
            project_id=ctx.project.id,
            enabled=False,
            level=1,
            area_key="pending",
            status="off",
            changed_by=ctx.user.id,
        )
        db.add(row)
        db.flush()
    if row.assistant_enabled == on:
        return
    row.assistant_enabled, row.changed_by = on, ctx.user.id
    _audit(db, ctx, "assistant.switched_on" if on else "assistant.switched_off", row.id)
    db.commit()


def request_update(db: Session, ctx: ProjectContext, send: Callable[[], None]) -> None:
    """ "Update now": mark this project's daily (and weekly) parts as due and wake the worker.

    If the worker cannot be reached now, the hourly check (Celery Beat) runs them anyway; the
    daily part runs from 06:00 Chicago time (B-D1)."""
    ensure_not_archived(ctx)
    row = _settings(db, ctx.project.id)
    if row is None or not row.enabled or row.status != "ready":
        raise ConflictError("Forecasting is not switched on and ready for this project.")
    row.last_daily_run = None
    if row.area_key in forecasting.TESTED_AREAS:
        row.last_weekly_run = None
    _audit(db, ctx, "forecast.update_requested", row.id)
    db.commit()
    try:
        send()
    except Exception:
        log.warning("Could not wake the worker for project %s", ctx.project.id, exc_info=True)


# ------------------------------------------------------------------ runs
def latest_run(db: Session, project_id: uuid.UUID, kind: str) -> RiskRun | None:
    return db.scalar(
        select(RiskRun)
        .where(
            RiskRun.project_id == project_id, RiskRun.kind == kind, RiskRun.status == "completed"
        )
        .order_by(RiskRun.as_of.desc(), RiskRun.finished_at.desc())
        .limit(1)
    )


def run_out(run: RiskRun | None) -> RunOut | None:
    if run is None:
        return None
    return RunOut(
        id=run.id,
        kind=run.kind,
        as_of=run.as_of,
        model_version=run.model_version,
        data_dates=run.data_dates or {},
        finished_at=run.finished_at,
    )


# ------------------------------------------------------------------ sections
@dataclass
class ProjectRisk:
    level: int | None
    levels_run: RiskRun | None
    factors_run: RiskRun | None
    items: list[SectionRiskOut]


def _factor_out(row: RiskFactorValue) -> FactorOut:
    return FactorOut(
        factor=row.factor, label=label(row.factor), value=row.value, level=row.level, kind=row.kind
    )


def _top_factor_level(factors: list[FactorOut]) -> str:
    levels = [f.level for f in factors if f.kind == "risk" and f.level != "missing"]
    return min(levels, key=LEVEL_ORDER.__getitem__) if levels else "low"


def project_risk(db: Session, ctx: ProjectContext) -> ProjectRisk:
    """Every section of the project with its level, reasons and factors, inspect-first order."""
    return project_risk_for(db, ctx.project.id)


def project_risk_for(db: Session, project_id: uuid.UUID) -> ProjectRisk:
    """Every section of the project with its level, reasons and factors, inspect-first order."""
    row = _settings(db, project_id)
    if row is None or row.status != "ready":
        return ProjectRisk(None, None, None, [])
    levels_run = latest_run(db, project_id, "weekly_levels") if row.level == 2 else None
    factors_run = latest_run(db, project_id, "daily_factors")

    factors: dict[uuid.UUID, list[FactorOut]] = defaultdict(list)
    if factors_run is not None:
        for value in db.scalars(
            select(RiskFactorValue)
            .where(RiskFactorValue.run_id == factors_run.id)
            .order_by(RiskFactorValue.kind.desc(), RiskFactorValue.factor)
        ):
            factors[value.section_id].append(_factor_out(value))

    levels: dict[uuid.UUID, RiskLevel] = {}
    if levels_run is not None:
        levels = {
            lv.section_id: lv
            for lv in db.scalars(select(RiskLevel).where(RiskLevel.run_id == levels_run.id))
        }
    section_ids = set(levels) | set(factors)
    sections = (
        {
            s.id: s
            for s in db.scalars(select(ForecastSection).where(ForecastSection.id.in_(section_ids)))
        }
        if section_ids
        else {}
    )

    def order(sid: uuid.UUID) -> tuple[Any, ...]:
        s = sections[sid]
        if sid in levels:
            return (0, levels[sid].rank, s.section_key)
        fs = factors.get(sid, [])
        high = sum(1 for f in fs if f.kind == "risk" and f.level == "high")
        medium = sum(1 for f in fs if f.kind == "risk" and f.level == "medium")
        return (1, -high, -medium, s.name or "~", s.section_key)

    items = []
    for position, sid in enumerate(sorted(sections, key=order), start=1):
        s, lv = sections[sid], levels.get(sid)
        fs = factors.get(sid, [])
        items.append(
            SectionRiskOut(
                section_id=sid,
                name=s.name,
                road_type=s.road_type,
                length_m=round(s.length_m, 1),
                position=position,
                level=lv.level if lv else (_top_factor_level(fs) if row.level == 1 else None),
                rank_in_area=lv.rank if lv else None,
                reasons=[
                    ReasonOut(input=r["input"], label=label(r["input"]), value=r.get("value"))
                    for r in (lv.reasons if lv else [])
                ],
                missing_inputs=[label(name) for name in (lv.missing_inputs if lv else [])],
                factors=fs,
            )
        )
    return ProjectRisk(row.level, levels_run, factors_run, items)


def counts(items: list[SectionRiskOut]) -> LevelCounts:
    out = LevelCounts()
    for item in items:
        if item.level in ("high", "medium", "low"):
            setattr(out, item.level, getattr(out, item.level) + 1)
    return out


def map_features(db: Session, ctx: ProjectContext) -> dict[str, Any]:
    """All sections as a GeoJSON FeatureCollection with their level (for the map)."""
    risk = project_risk(db, ctx)
    by_id = {item.section_id: item for item in risk.items}
    features = []
    if by_id:
        rows = db.execute(
            select(ForecastSection.id, func.ST_AsGeoJSON(ForecastSection.line, 6)).where(
                ForecastSection.id.in_(list(by_id))
            )
        ).all()
        geometry = {sid: geo for sid, geo in rows}
        for item in risk.items:
            features.append(
                {
                    "type": "Feature",
                    "geometry": json.loads(geometry[item.section_id]),
                    "properties": {
                        "section_id": str(item.section_id),
                        "name": item.name,
                        "level": item.level,
                        "position": item.position,
                    },
                }
            )
    return {"type": "FeatureCollection", "features": features}


def section_detail(
    db: Session, ctx: ProjectContext, section_id: uuid.UUID
) -> tuple[SectionRiskOut, dict[str, Any], list[HistoryPoint], list[LinkedInspection], ProjectRisk]:
    risk = project_risk(db, ctx)
    item = next((i for i in risk.items if i.section_id == section_id), None)
    if item is None:
        raise NotFoundError("Road section not found in this project.")
    geometry = json.loads(
        db.scalar(
            select(func.ST_AsGeoJSON(ForecastSection.line, 6)).where(
                ForecastSection.id == section_id
            )
        )
    )
    history_rows = db.execute(
        select(RiskRun.as_of, RiskLevel.level, RiskLevel.rank)
        .join(RiskRun, RiskRun.id == RiskLevel.run_id)
        .where(
            RiskRun.project_id == ctx.project.id,
            RiskRun.status == "completed",
            RiskLevel.section_id == section_id,
        )
        .order_by(RiskRun.as_of.desc(), RiskRun.finished_at.desc())
        .limit(52)
    ).all()
    seen, history = set(), []
    for as_of, level, rank in history_rows:  # one point per Monday (an "update now" may repeat one)
        if as_of not in seen:
            seen.add(as_of)
            history.append(HistoryPoint(as_of=as_of, level=level, rank_in_area=rank))
    inspections = [
        LinkedInspection(id=i.id, status=i.status, planned_date=i.planned_date)
        for i in db.scalars(
            select(Inspection)
            .where(Inspection.project_id == ctx.project.id, Inspection.section_id == section_id)
            .order_by(Inspection.created_at.desc())
        )
    ]
    return item, geometry, history, inspections, risk


# ------------------------------------------------------------------ weather
def outlook(db: Session, project_id: uuid.UUID) -> OutlookOut | None:
    row = db.scalar(
        select(WeatherOutlook)
        .where(WeatherOutlook.project_id == project_id)
        .order_by(WeatherOutlook.fetched_at.desc(), WeatherOutlook.issued_at.desc())
        .limit(1)
    )
    if row is None:
        return None
    return OutlookOut(
        source=row.source,
        issued_at=row.issued_at,
        fetched_at=row.fetched_at,
        days=row.days,
        freeze_thaw_days=row.freeze_thaw_days,
        frost_days=row.frost_days,
        heavy_rain_days=row.heavy_rain_days,
        snow_mm=row.snow_mm,
    )


def recent_weather(db: Session, project_id: uuid.UUID) -> RecentWeatherOut | None:
    """The weather inputs of the latest daily run; the middle value over the project's sections
    (a large project can span two weather stations)."""
    run = latest_run(db, project_id, "daily_factors")
    if run is None:
        return None
    by_factor: dict[str, list[RiskFactorValue]] = defaultdict(list)
    for value in db.scalars(
        select(RiskFactorValue).where(
            RiskFactorValue.run_id == run.id, RiskFactorValue.factor.in_(WEATHER_FACTORS)
        )
    ):
        by_factor[value.factor].append(value)
    values = []
    for name in WEATHER_FACTORS:
        rows = by_factor.get(name, [])
        known = sorted((r for r in rows if r.value is not None), key=lambda r: r.value or 0.0)
        if not known:
            values.append(
                FactorOut(
                    factor=name,
                    label=label(name),
                    value=None,
                    level="missing",
                    kind=rows[0].kind if rows else "risk",
                )
            )
            continue
        middle = known[(len(known) - 1) // 2]
        values.append(
            FactorOut(
                factor=name,
                label=label(name),
                value=round(statistics.median(r.value for r in known if r.value is not None), 1),
                level=middle.level,
                kind=middle.kind,
            )
        )
    return RecentWeatherOut(as_of=run.as_of, values=values)


# ------------------------------------------------------------------ alerts
def alert_outs(db: Session, user: User, alerts: list[Alert]) -> list[AlertOut]:
    if not alerts:
        return []
    ids = [a.id for a in alerts]
    read = set(
        db.scalars(
            select(AlertRead.alert_id).where(
                AlertRead.user_id == user.id, AlertRead.alert_id.in_(ids)
            )
        )
    )
    names = {
        pid: name
        for pid, name in db.execute(
            select(Project.id, Project.name).where(Project.id.in_({a.project_id for a in alerts}))
        )
    }
    return [
        AlertOut(
            id=a.id,
            project_id=a.project_id,
            project_name=names[a.project_id],
            type=a.type,
            title=a.title,
            details=a.details or {},
            created_at=a.created_at,
            closed_at=a.closed_at,
            read=a.id in read,
        )
        for a in alerts
    ]


def project_alerts(
    db: Session, ctx: ProjectContext, include_closed: bool, page: int, page_size: int
) -> tuple[list[AlertOut], int]:
    query = select(Alert).where(Alert.project_id == ctx.project.id, Alert.user_id.is_(None))
    if not include_closed:
        query = query.where(Alert.closed_at.is_(None))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    alerts = list(
        db.scalars(
            query.order_by(Alert.created_at.desc(), Alert.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return alert_outs(db, ctx.user, alerts), total


def managed_project_ids(db: Session, user: User) -> list[uuid.UUID]:
    """Projects the person manages (roadmap 7.5: alerts go to project managers only; an org admin
    sees a project's alerts when they open it, and in the bell for projects they manage)."""
    return list(
        db.scalars(
            select(Project.id)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(
                ProjectMember.user_id == user.id,
                ProjectMember.role == "project_manager",
                Project.archived_at.is_(None),
            )
        )
    )


def _mine(user: User, projects: list[uuid.UUID]) -> Any:
    """Project alerts of the projects I manage, plus personal notifications for me."""
    return or_(
        and_(Alert.user_id.is_(None), Alert.project_id.in_(projects)), Alert.user_id == user.id
    )


def notifications(db: Session, user: User) -> tuple[list[AlertOut], int]:
    projects = managed_project_ids(db, user)
    mine = _mine(user, projects)
    unread_filter = and_(
        mine,
        ~exists().where(AlertRead.alert_id == Alert.id, AlertRead.user_id == user.id),
    )
    unread = db.scalar(select(func.count()).select_from(Alert).where(unread_filter)) or 0
    alerts = list(
        db.scalars(
            select(Alert)
            .where(mine)
            .order_by(Alert.closed_at.is_not(None), Alert.created_at.desc(), Alert.id)
            .limit(NOTIFICATION_LIMIT)
        )
    )
    return alert_outs(db, user, alerts), unread


def mark_read(db: Session, user: User, alert: Alert) -> None:
    db.execute(
        insert(AlertRead)
        .values(id=uuid.uuid4(), alert_id=alert.id, user_id=user.id)
        .on_conflict_do_nothing(index_elements=["alert_id", "user_id"])
    )
    db.commit()


def alert_project(db: Session, alert_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(select(Alert.project_id).where(Alert.id == alert_id))


def get_alert(db: Session, alert_id: uuid.UUID) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise NotFoundError("Alert not found.")
    return alert


# ------------------------------------------------------------------ road inspections (F4d)
def section_in_project(db: Session, project_id: uuid.UUID, section_id: uuid.UUID) -> bool:
    """True when the section has levels or risk factors in one of the project's runs."""
    in_levels = exists().where(
        RiskLevel.section_id == section_id,
        RiskLevel.run_id == RiskRun.id,
        RiskRun.project_id == project_id,
    )
    in_factors = exists().where(
        RiskFactorValue.section_id == section_id,
        RiskFactorValue.run_id == RiskRun.id,
        RiskRun.project_id == project_id,
    )
    return bool(db.scalar(select(in_levels)) or db.scalar(select(in_factors)))


def current_level_id(db: Session, project_id: uuid.UUID, section_id: uuid.UUID) -> uuid.UUID | None:
    """The section's level in the latest weekly run (Level 2), to link an inspection to it."""
    run = latest_run(db, project_id, "weekly_levels")
    if run is None:
        return None
    return db.scalar(
        select(RiskLevel.id).where(RiskLevel.run_id == run.id, RiskLevel.section_id == section_id)
    )


# ------------------------------------------------------------------ export (F4d)
EXPORT_COLUMNS = [
    "position",
    "road",
    "road_type",
    "length_m",
    "level",
    "rank_in_area",
    "reason_1",
    "reason_2",
    "reason_3",
    "high_or_medium_risk_factors",
    "missing_inputs",
    "section_id",
]


def _reason_text(reason: ReasonOut) -> str:
    return reason.label if reason.value is None else f"{reason.label}: {reason.value:g}"


def _export_rows(risk: ProjectRisk) -> list[dict[str, Any]]:
    rows = []
    for item in risk.items:
        reasons = [_reason_text(r) for r in item.reasons] + ["", "", ""]
        flagged = [
            f"{f.label} ({f.level})"
            for f in item.factors
            if f.kind == "risk" and f.level in ("high", "medium")
        ]
        rows.append(
            {
                "position": item.position,
                "road": item.name or "",
                "road_type": item.road_type,
                "length_m": item.length_m,
                "level": item.level or "",
                "rank_in_area": item.rank_in_area or "",
                "reason_1": reasons[0],
                "reason_2": reasons[1],
                "reason_3": reasons[2],
                "high_or_medium_risk_factors": "; ".join(flagged),
                "missing_inputs": "; ".join(item.missing_inputs),
                "section_id": str(item.section_id),
            }
        )
    return rows


def _export_header(risk: ProjectRisk) -> list[str]:
    from app.schemas.road_risk import NOTICE, TRIAL_LABEL

    lines = [f"{TRIAL_LABEL}. {NOTICE}"]
    if risk.levels_run is not None:
        lines.append(
            f"Levels of {risk.levels_run.as_of}, model {risk.levels_run.model_version}; "
            "high = riskiest 1% of the area that week, medium = the next 9%"
        )
    if risk.factors_run is not None:
        lines.append(f"Risk factors of {risk.factors_run.as_of}")
    if risk.level == 1:
        lines.append("Risk factors only: no pothole history here (not a tested forecast)")
    return lines


def export(db: Session, ctx: ProjectContext, file_format: str) -> tuple[bytes, str, str]:
    """The road-risk list as CSV or GeoJSON, labelled. Returns (content, media type, file name)."""
    import csv
    import io

    risk = project_risk(db, ctx)
    rows = _export_rows(risk)
    name = f"road-risk-{ctx.project.id.hex[:8]}"
    if file_format == "csv":
        buffer = io.StringIO()
        for line in _export_header(risk):
            buffer.write(f"# {line}\n")
        writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        content, media, filename = buffer.getvalue().encode("utf-8"), "text/csv", f"{name}.csv"
    else:
        geometry = (
            {
                sid: json.loads(geo)
                for sid, geo in db.execute(
                    select(ForecastSection.id, func.ST_AsGeoJSON(ForecastSection.line, 6)).where(
                        ForecastSection.id.in_([i.section_id for i in risk.items])
                    )
                )
            }
            if risk.items
            else {}
        )
        collection = {
            "type": "FeatureCollection",
            "metadata": {
                "label": _export_header(risk)[0],
                "notes": _export_header(risk)[1:],
                "levels_run": str(risk.levels_run.as_of) if risk.levels_run else None,
                "factors_run": str(risk.factors_run.as_of) if risk.factors_run else None,
            },
            "features": [
                {
                    "type": "Feature",
                    "geometry": geometry[uuid.UUID(row["section_id"])],
                    "properties": row,
                }
                for row in rows
            ],
        }
        content = json.dumps(collection).encode("utf-8")
        media, filename = "application/geo+json", f"{name}.geojson"
    record_event(
        db,
        action="forecast.exported",
        organization_id=ctx.project.organization_id,
        project_id=ctx.project.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="project",
        target_id=ctx.project.id,
        details={"format": file_format, "rows": len(rows)},
    )
    db.commit()
    return content, media, filename


def mark_all_read(db: Session, user: User) -> None:
    ids = list(db.scalars(select(Alert.id).where(_mine(user, managed_project_ids(db, user)))))
    if ids:
        db.execute(
            insert(AlertRead)
            .values([{"id": uuid.uuid4(), "alert_id": i, "user_id": user.id} for i in ids])
            .on_conflict_do_nothing(index_elements=["alert_id", "user_id"])
        )
    db.commit()


def can_read_alert(ctx: ProjectContext, alert: Alert) -> bool:
    """A personal notification only for its person; a project alert for alert.view."""
    if alert.user_id is not None:
        return alert.user_id == ctx.user.id
    return ctx.has(Perm.ALERT_VIEW)


def has_personal(db: Session, user: User) -> bool:
    return db.scalar(select(exists().where(Alert.user_id == user.id))) or False
