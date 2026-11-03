"""Automatic road-risk alerts for project managers (F4e; forecasting-f4e-design.md).

Approved 2026-11-02. Checked every hour by the forecasting tick, after the daily and weekly parts.
Each rule creates at most one open alert per event and project (no repeats while it is open) and
closes it by itself when the event is over. Levels only (F4-D2): never a percentage.

- turned_high (Chicago, Level 2): roads high this Monday that were not high the Monday before.
- freeze_thaw_coming: 3+ freeze-thaw days in the NWS 7-day outlook (E-D1, configurable).
- heavy_rain_coming: a day with 25 mm or more in the outlook (E-D1, configurable).
- data_problem: the latest job of a kind failed, or the levels / daily update are out of date.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Alert, ForecastSettings, RiskLevel, RiskRun, WeatherOutlook
from app.schemas.road_risk import NOTICE, TRIAL_LABEL
from app.services import road_risk
from app.services.forecasting import CHICAGO, local_now

WEATHER_RISK_FACTORS = {
    "freeze_thaw_coming": {"freeze_thaw_14d", "low_spot_m", "flood_zone"},
    "heavy_rain_coming": {"low_spot_m", "flood_zone"},
}
DAY_NAMES = "%A %d %B"


def _day(text: str) -> str:
    return date.fromisoformat(text).strftime(DAY_NAMES).replace(" 0", " ")


def _open(db: Session, project_id: uuid.UUID, kind: str) -> list[Alert]:
    return list(
        db.scalars(
            select(Alert).where(
                Alert.project_id == project_id, Alert.type == kind, Alert.closed_at.is_(None)
            )
        )
    )


def _create(
    db: Session,
    project_id: uuid.UUID,
    kind: str,
    key: str,
    title: str,
    details: dict[str, Any],
    run_id: uuid.UUID | None,
) -> Alert | None:
    if any(a.event_key == key for a in _open(db, project_id, kind)):
        return None  # already open: never repeated
    alert = Alert(
        project_id=project_id,
        type=kind,
        event_key=key,
        title=title,
        details={"label": TRIAL_LABEL, "notice": NOTICE, **details},
        run_id=run_id,
    )
    db.add(alert)
    db.flush()
    return alert


def _close(alerts: list[Alert], now: datetime) -> int:
    for alert in alerts:
        alert.closed_at = now
    return len(alerts)


def _road(item: Any, previous: str | None = None) -> dict[str, Any]:
    road = {
        "section_id": str(item.section_id),
        "name": item.name or "Unnamed road",
        "level": item.level,
        "reasons": [
            r.label if r.value is None else f"{r.label}: {r.value:g}" for r in item.reasons
        ],
        "missing_inputs": item.missing_inputs,
    }
    if previous is not None:
        road["previous_level"] = previous
    if not item.reasons:  # Level 1: the risk factors that are high or medium
        road["reasons"] = [
            f"{f.label} ({f.level})"
            for f in item.factors
            if f.kind == "risk" and f.level in ("high", "medium")
        ]
    return road


def _model(risk: road_risk.ProjectRisk) -> dict[str, Any]:
    run = risk.levels_run or risk.factors_run
    return {
        "model_version": run.model_version if run else None,
        "data_dates": run.data_dates if run else {},
        "levels_of": str(risk.levels_run.as_of) if risk.levels_run else None,
    }


# ------------------------------------------------------------------ rules
def turned_high(db: Session, row: ForecastSettings, now: datetime) -> int:
    if row.level != 2:
        return 0
    runs = list(
        db.scalars(
            select(RiskRun)
            .where(
                RiskRun.project_id == row.project_id,
                RiskRun.kind == "weekly_levels",
                RiskRun.status == "completed",
            )
            .order_by(RiskRun.as_of.desc(), RiskRun.finished_at.desc())
        )
    )
    mondays: list[RiskRun] = []
    for run in runs:  # one run per Monday (an "update now" may repeat one)
        if not mondays or run.as_of != mondays[-1].as_of:
            mondays.append(run)
    if len(mondays) < 2:
        return 0  # the first Monday has nothing to compare with
    latest, before = mondays[0], mondays[1]
    key = f"turned_high:{latest.as_of}"
    closed = _close(
        [a for a in _open(db, row.project_id, "turned_high") if a.event_key != key], now
    )
    previous = {
        lv.section_id: lv.level
        for lv in db.scalars(select(RiskLevel).where(RiskLevel.run_id == before.id))
    }
    risk = road_risk.project_risk_for(db, row.project_id)
    roads = [
        _road(item, previous.get(item.section_id, "not listed"))
        for item in risk.items
        if item.level == "high" and previous.get(item.section_id) != "high"
    ]
    if not roads:
        return closed
    count = len(roads)
    _create(
        db,
        row.project_id,
        "turned_high",
        key,
        f"{count} road{'s' if count != 1 else ''} turned high risk this week",
        {
            "when": f"Levels of {_day(str(latest.as_of))}",
            "roads": roads,
            "suggested_action": "Inspect these roads first; plan an inspection from each road.",
            **_model(risk),
        },
        latest.id,
    )
    return closed + 1


def _event_days(outlook: WeatherOutlook, kind: str) -> list[str]:
    cfg = get_settings()
    days = []
    for day in outlook.days:
        if kind == "freeze_thaw_coming":
            hit = (
                day.get("max_c") is not None
                and day.get("min_c") is not None
                and day["max_c"] > 0
                and day["min_c"] < 0
            )
        else:
            hit = (day.get("rain_mm") or 0) >= cfg.forecast_alert_rain_mm
        if hit:
            days.append(str(day["date"]))
    if kind == "freeze_thaw_coming" and len(days) < cfg.forecast_alert_freeze_thaw_days:
        return []
    return days


def weather(db: Session, row: ForecastSettings, kind: str, today: date, now: datetime) -> int:
    open_alerts = _open(db, row.project_id, kind)
    over = [a for a in open_alerts if max(a.details.get("days", [""])) < today.isoformat()]
    changed = _close(over, now)
    outlook = db.scalar(
        select(WeatherOutlook)
        .where(WeatherOutlook.project_id == row.project_id)
        .order_by(WeatherOutlook.fetched_at.desc(), WeatherOutlook.issued_at.desc())
        .limit(1)
    )
    if outlook is None:
        return changed
    days = [d for d in _event_days(outlook, kind) if d >= today.isoformat()]
    if not days:
        return changed
    still_open = [a for a in open_alerts if a not in over]
    if any(max(a.details.get("days", [""])) >= days[0] for a in still_open):
        return changed  # the same weather spell already has an open alert
    risk = road_risk.project_risk_for(db, row.project_id)
    if row.level == 2:
        roads = [_road(i) for i in risk.items if i.level in ("high", "medium")]
        if not roads:
            return changed  # the rule is about roads already at medium or high risk
    else:
        wanted = WEATHER_RISK_FACTORS[kind]
        roads = [
            _road(i)
            for i in risk.items
            if any(f.factor in wanted and f.level in ("high", "medium") for f in i.factors)
        ]
    what = "Freeze-thaw" if kind == "freeze_thaw_coming" else "Heavy rain"
    count = len(roads)
    if row.level == 2:
        title = f"{what} coming: {count} road{'s' if count != 1 else ''} at high or medium risk"
    else:
        title = f"{what} coming in this project area" + (
            f": {count} road{'s' if count != 1 else ''} with risk factors" if count else ""
        )
    _create(
        db,
        row.project_id,
        kind,
        f"{kind}:{days[0]}",
        title,
        {
            "when": ", ".join(_day(d) for d in days),
            "days": days,
            "source": f"National Weather Service ({outlook.source})",
            "issued_at": outlook.issued_at.isoformat(),
            "roads": roads,
            "suggested_action": f"Inspect these roads before {_day(days[0])}.",
            **_model(risk),
        },
        None,
    )
    return changed + 1


def data_problem(db: Session, row: ForecastSettings, today: date, now: datetime) -> int:
    cfg = get_settings()
    problems: dict[str, str] = {}
    kinds = ["daily_factors", "outlook"] + (["weekly_levels"] if row.area_key == CHICAGO else [])
    for kind in kinds:
        latest = db.scalar(
            select(RiskRun)
            .where(RiskRun.project_id == row.project_id, RiskRun.kind == kind)
            .order_by(RiskRun.as_of.desc(), RiskRun.started_at.desc())
            .limit(1)
        )
        if latest is not None and latest.status == "failed":
            problems[f"data_problem:{kind}:{latest.as_of}"] = (
                latest.message or f"The {kind} job failed."
            )
    if (
        row.last_daily_run
        and (today - row.last_daily_run).days > cfg.forecast_alert_daily_stale_days
    ):
        problems["data_problem:daily_stale"] = (
            f"The weather and risk factors were last updated on {row.last_daily_run}."
        )
    if (
        row.area_key == CHICAGO
        and row.last_weekly_run
        and (today - row.last_weekly_run).days > cfg.forecast_alert_weekly_stale_days
    ):
        problems["data_problem:weekly_stale"] = (
            f"The risk levels are from {row.last_weekly_run}; the weekly update did not run."
        )
    changed = _close(
        [a for a in _open(db, row.project_id, "data_problem") if a.event_key not in problems], now
    )
    for key, reason in problems.items():
        if _create(
            db,
            row.project_id,
            "data_problem",
            key,
            "Road risk data problem: the forecast may be out of date",
            {
                "when": f"Found {today}",
                "reason": reason,
                "roads": [],
                "suggested_action": "Check that the computer, Docker and the internet are on. "
                "The next run catches up by itself.",
            },
            None,
        ):
            changed += 1
    return changed


def evaluate(db: Session, row: ForecastSettings, now: datetime | None = None) -> int:
    """All rules for one ready project. Returns how many alerts were created or closed."""
    now = now or datetime.now(UTC)
    today = local_now(now).date()
    changed = turned_high(db, row, now)
    changed += weather(db, row, "freeze_thaw_coming", today, now)
    changed += weather(db, row, "heavy_rain_coming", today, now)
    changed += data_problem(db, row, today, now)
    db.commit()
    return changed


def run_all(db: Session, now: datetime | None = None) -> dict[str, int]:
    rows = db.scalars(
        select(ForecastSettings).where(
            ForecastSettings.enabled.is_(True), ForecastSettings.status == "ready"
        )
    )
    return {"changed": sum(evaluate(db, row, now) for row in list(rows))}
