"""Road-risk forecasting jobs (F4b; documentation/04-design/forecasting-f4b-design.md).

The forecasting code lives in ml/forecasting (mounted at /ml in the worker). This module decides
what to run and when, and copies the results the screens need into the app database:

- `enable` / `setup`: a manager switches forecasting on; the project's area is checked (largest
  500 km², F4-D4) and set up: Chicago projects use the Chicago area (Level 2), others become their
  own Level 1 area.
- `daily`: new weather, the risk factors and the NWS 7-day outlook for every ready project.
- `weekly`: new Chicago 311 reports and the B1 levels (top 1% high, next 9% medium; F4-D2).
- `monitor`: the monthly check of the raw model values against what happened (F4-D2; never
  shown as a percentage).
- `tick`: run hourly by Celery Beat; runs each part when it is due (06:00 daily, Monday 07:00
  weekly, Chicago time, B-D1), so days missed while the computer was off are caught up (F4-D5).
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    ForecastMonitoring,
    ForecastSection,
    ForecastSettings,
    RiskFactorValue,
    RiskLevel,
    RiskRun,
    WeatherOutlook,
)

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("America/Chicago")
DAILY_HOUR, WEEKLY_HOUR = 6, 7  # B-D1
CHICAGO = "chicago"
LEVEL1 = "level1"


class ForecastingOffError(RuntimeError):
    """FORECAST_DATABASE_URL is not set, so the forecasting jobs cannot run."""


def forecast_url() -> str:
    url = (
        get_settings()
        .forecast_database_url.strip()
        .replace("postgresql+psycopg://", "postgresql://")
    )
    if not url:
        raise ForecastingOffError("Forecasting is off: FORECAST_DATABASE_URL is not set.")
    if url.rstrip("/").rsplit("/", 1)[-1].split("?")[0] in {"geoinfralens", "geoinfralens_test"}:
        raise ForecastingOffError("FORECAST_DATABASE_URL points at the app database.")
    return url


def project_areas_dir() -> Path:
    from forecasting import settings as fsettings

    return Path(fsettings.FORECAST_DIR) / "data" / "_project_areas"


def _session() -> Any:
    """A web session naming us in the User-Agent (FORECAST_CONTACT_EMAIL; NWS asks for one)."""
    from forecasting.download import new_session

    return new_session()


# ---------- when is a part due (pure, tested) ----------


def local_now(now: datetime) -> datetime:
    return now.astimezone(LOCAL_TZ)


def daily_due(now: datetime, last: date | None) -> bool:
    local = local_now(now)
    return local.hour >= DAILY_HOUR and (last is None or last < local.date())


def this_monday(now: datetime) -> date:
    local = local_now(now).date()
    return local - timedelta(days=local.weekday())


def weekly_due(now: datetime, last: date | None) -> bool:
    local = local_now(now)
    monday = this_monday(now)
    if local.date() == monday and local.hour < WEEKLY_HOUR:
        return False
    return last is None or last < monday


# ---------- switching on and setting up ----------


@dataclass
class ProjectArea:
    km2: float
    ewkt: str
    geojson: dict[str, Any]
    lat: float
    lon: float
    name: str


def project_area(db: Session, project_id: uuid.UUID) -> ProjectArea:
    row = db.execute(
        text(
            "SELECT ST_Area(boundary::geography) / 1e6, ST_AsEWKT(boundary), "
            "ST_AsGeoJSON(boundary), ST_Y(ST_PointOnSurface(boundary)), "
            "ST_X(ST_PointOnSurface(boundary)), name FROM projects WHERE id = :id"
        ),
        {"id": project_id},
    ).one()
    return ProjectArea(
        float(row[0]), row[1], json.loads(row[2]), float(row[3]), float(row[4]), row[5]
    )


def enable(db: Session, project_id: uuid.UUID, user_id: uuid.UUID) -> ForecastSettings:
    """Switch forecasting on (or back on). Set-up runs afterwards (`setup`, a background task)."""
    row = db.scalar(select(ForecastSettings).where(ForecastSettings.project_id == project_id))
    area = project_area(db, project_id)
    limit = get_settings().forecast_max_area_km2
    if row is None:
        row = ForecastSettings(
            project_id=project_id, level=1, area_key="pending", changed_by=user_id
        )
        db.add(row)
    row.enabled, row.changed_by, row.area_km2 = True, user_id, round(area.km2, 2)
    if area.km2 > limit:
        row.status = "too_large"
        row.message = (
            f"The project area is {area.km2:,.0f} km²; forecasting is set up for areas "
            f"up to {limit:,.0f} km²."
        )
    else:
        row.status, row.message = "setting_up", None
    db.commit()
    return row


def disable(db: Session, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
    row = db.scalar(select(ForecastSettings).where(ForecastSettings.project_id == project_id))
    if row is not None:
        row.enabled, row.status, row.changed_by = False, "off", user_id
        db.commit()


def _start_run(
    db: Session, project_id: uuid.UUID, kind: str, as_of: date, model_version: str
) -> RiskRun:
    run = RiskRun(
        project_id=project_id, kind=kind, as_of=as_of, model_version=model_version, data_dates={}
    )
    db.add(run)
    db.flush()
    return run


def _finish(
    run: RiskRun, status: str = "completed", message: str | None = None, **data_dates: Any
) -> None:
    run.status, run.message, run.finished_at = status, message, datetime.now(UTC)
    run.data_dates = {
        **(run.data_dates or {}),
        **{k: (str(v) if v is not None else None) for k, v in data_dates.items()},
    }


def copy_sections(db: Session, fconn: Any, area_key: str, schema: str, ewkt: str) -> int:
    from forecasting import live

    rows = live.sections_in(fconn, schema, ewkt)
    if rows:
        db.execute(
            insert(ForecastSection)
            .values(
                [
                    {
                        "id": uuid.uuid4(),
                        "area_key": area_key,
                        "section_key": sid,
                        "name": name,
                        "road_type": highway,
                        "length_m": float(length),
                        "line": line,
                    }
                    for sid, name, highway, length, line in rows
                ]
            )
            .on_conflict_do_nothing(index_elements=["area_key", "section_key"])
        )
    return len(rows)


def setup(db: Session, settings_id: uuid.UUID, session: Any = None) -> ForecastSettings:
    """Set up the project's area (Chicago: the Chicago area; else a new Level 1 area)."""
    from forecasting import live
    from forecasting import settings as fsettings

    row = db.get(ForecastSettings, settings_id)
    if row is None or not row.enabled or row.status in ("too_large", "off"):
        raise ValueError("Forecasting is not waiting to be set up for this project.")
    url = forecast_url()
    area = project_area(db, row.project_id)
    run = _start_run(db, row.project_id, "setup", datetime.now(UTC).date(), "-")
    started = local_now(datetime.now(UTC)).strftime("%H:%M")

    def progress(step: int, total: int, text: str) -> None:
        """Shown on the screens while setting up (owner request 2026-11-02)."""
        row.message = f"Step {step} of {total}: {text} (started {started} Chicago time)"
        db.commit()

    progress(1, 4, "checking where the project is")
    try:
        with fsettings.connect(url) as fconn:
            chicago = live.in_chicago(fconn, area.ewkt)
        if chicago:
            row.level, row.area_key, schema = 2, CHICAGO, CHICAGO
            progress(4, 4, "copying the Chicago road sections inside the project")
        else:
            from forecasting import area_check, load
            from forecasting import areas as fareas
            from forecasting.download import download_all

            key = live.project_area_key(str(row.project_id))
            folder = live.write_project_area(
                str(row.project_id), area.name, area.geojson, base=project_areas_dir()
            )
            rules = fsettings.rules()
            farea = fareas.load_area(key, areas_dir=folder)
            area_check.run(farea, rules, terms_confirmed=False, session=session)
            progress(
                2,
                4,
                "downloading roads, ground height, flood zones and about 10 years of weather "
                "(the longest step: usually 10-60 minutes)",
            )
            download_all(
                farea.raw_dir,
                fareas.ready_sources(farea, need_box=False),
                rules,
                terms_confirmed=False,
                session=session,
            )
            progress(3, 4, "splitting the roads into 100 m sections and working out risk factors")
            load.run_load(
                url, farea.raw_dir, fareas.ready_sources(farea), rules, schema=farea.schema
            )
            row.level, row.area_key, schema = 1, key, key
            progress(4, 4, "copying the road sections into the app")
        with fsettings.connect(url) as fconn:
            count = copy_sections(db, fconn, row.area_key, schema, area.ewkt)
        row.status = "ready"
        kind = "tested Chicago levels" if chicago else "risk factors only (no pothole history)"
        row.message = f"{count:,} road sections; {kind}."
        run.model_version = "level2" if chicago else LEVEL1
        _finish(run)
    except Exception as error:  # noqa: BLE001 (any failure must be recorded with a plain reason, never lost)
        db.rollback()
        row = db.get(ForecastSettings, settings_id)
        run = db.get(RiskRun, run.id)
        row.status, row.message = "failed", f"Set-up failed: {str(error)[:500]}"
        _finish(run, "failed", row.message)
        logger.warning("Forecast set-up failed for project %s: %s", row.project_id, error)
    db.commit()
    return row


# ---------- daily: weather, risk factors, outlook ----------


def _ready(db: Session, **where: Any) -> list[ForecastSettings]:
    query = select(ForecastSettings).where(
        ForecastSettings.enabled.is_(True), ForecastSettings.status == "ready"
    )
    for key, value in where.items():
        query = query.where(getattr(ForecastSettings, key) == value)
    return list(db.scalars(query))


def project_section_ids(db: Session, project_id: uuid.UUID, area_key: str) -> dict[str, uuid.UUID]:
    """section_key -> forecast_sections id, for the sections touching the project's area."""
    rows = db.execute(
        text(
            "SELECT s.section_key, s.id FROM forecast_sections s "
            "JOIN projects p ON p.id = :project "
            "WHERE s.area_key = :area AND ST_Intersects(s.line, p.boundary)"
        ),
        {"project": project_id, "area": area_key},
    ).all()
    return {key: sid for key, sid in rows}


def _area(area_key: str) -> Any:
    from forecasting import areas

    if area_key == CHICAGO:
        return areas.load_area(CHICAGO)
    return areas.load_area(area_key, areas_dir=project_areas_dir())


def daily(
    db: Session, now: datetime, session: Any = None, nws_session: Any = None
) -> dict[str, Any]:
    from forecasting import areas, nws, risk_factors
    from forecasting import settings as fsettings

    url = forecast_url()
    due = [row for row in _ready(db) if daily_due(now, row.last_daily_run)]
    if not due:
        return {"projects": 0}
    today = local_now(now).date()
    cfg, cutoffs = fsettings.load_config("f2.yaml"), risk_factors.read_cutoffs()
    background = list(cutoffs.get("background", []))
    by_area: dict[str, list[ForecastSettings]] = defaultdict(list)
    for row in due:
        by_area[row.area_key].append(row)
    session = session or _session()
    done = 0
    for area_key, rows in by_area.items():
        area = _area(area_key)
        src = areas.ready_sources(area)
        try:
            with fsettings.connect(url, area.schema) as fconn:
                weather_last = _refresh_weather(fconn, area, session)
                factor_rows, info = risk_factors.compute(
                    fconn, src, cfg, cutoffs["cutoffs"], background=background
                )
        except Exception as error:  # noqa: BLE001
            for row in rows:
                run = _start_run(db, row.project_id, "daily_factors", today, LEVEL1)
                _finish(run, "failed", f"Weather or risk factors failed: {str(error)[:400]}")
            db.commit()
            logger.warning("Daily forecasting failed for area %s: %s", area_key, error)
            continue
        by_section: dict[str, list[tuple]] = defaultdict(list)
        for r in factor_rows:
            by_section[r[0]].append(r)
        for row in rows:
            ids = project_section_ids(db, row.project_id, area_key)
            run = _start_run(
                db, row.project_id, "daily_factors", date.fromisoformat(info["as_of"]), LEVEL1
            )
            db.add_all(
                RiskFactorValue(
                    run_id=run.id, section_id=ids[key], factor=f, value=v, level=lv, kind=kind
                )
                for key in ids
                for (_, _, f, v, lv, kind) in by_section.get(key, [])
            )
            _finish(
                run,
                weather_up_to=info["weather_up_to"],
                stations=",".join(info["stations"]),
                **weather_last,
            )
            _outlook(db, row, today, nws_session or session, nws)
            row.last_daily_run = today
            done += 1
        db.commit()
    return {"projects": done}


def _refresh_weather(fconn: Any, area: Any, session: Any) -> dict[str, Any]:
    from forecasting import live

    last = live.refresh_weather(fconn, area, session)
    fconn.commit()
    return {f"weather_{k}": v for k, v in last.items()}


def _outlook(db: Session, row: ForecastSettings, today: date, session: Any, nws: Any) -> None:
    area = project_area(db, row.project_id)
    run = _start_run(db, row.project_id, "outlook", today, "nws")
    try:
        out = nws.fetch_outlook(session, area.lat, area.lon, today)
    except Exception as error:  # noqa: BLE001
        _finish(run, "failed", f"Weather outlook failed: {str(error)[:400]}")
        return
    issued = datetime.fromisoformat(out["issued_at"]) if out.get("issued_at") else datetime.now(UTC)
    db.add(
        WeatherOutlook(
            project_id=row.project_id,
            issued_at=issued,
            source=out["source"],
            days=out["days"],
            freeze_thaw_days=out["freeze_thaw_days"],
            frost_days=out["frost_days"],
            heavy_rain_days=out["heavy_rain_days"],
            snow_mm=out["snow_mm"],
        )
    )
    _finish(run, issued_at=out.get("issued_at"), source=out["source"])


# ---------- weekly: Chicago levels ----------


def weekly(db: Session, now: datetime, session: Any = None) -> dict[str, Any]:
    import numpy as np
    from forecasting import live
    from forecasting import settings as fsettings
    from forecasting import weekly as fweekly

    rows = [row for row in _ready(db, area_key=CHICAGO) if weekly_due(now, row.last_weekly_run)]
    if not rows:
        return {"projects": 0}
    monday = this_monday(now)
    url, cfg = forecast_url(), fsettings.load_config("f2.yaml")
    area = _area(CHICAGO)
    cfg["snow_station"] = area.src.get("snow_station", cfg["snow_station"])
    model, version = live.load_model(get_settings().forecast_models_dir)
    try:
        with fsettings.connect(url, CHICAGO) as fconn:
            added = live.download_new_reports(fconn, area, session or _session())
            matched = fweekly.match_new_reports(
                fconn, fsettings.rules()["target"]["match_distance_m"]
            )
            fconn.commit()
            newest = fconn.execute("SELECT max(created_at)::date FROM pothole_reports").fetchone()[
                0
            ]
            levels = live.weekly_levels(fconn, monday, cfg, area.crs, model)
    except Exception as error:  # noqa: BLE001
        for row in rows:
            run = _start_run(db, row.project_id, "weekly_levels", monday, version)
            _finish(run, "failed", f"Weekly levels failed: {str(error)[:400]}")
        db.commit()
        logger.warning("Weekly Chicago levels failed: %s", error)
        return {"projects": 0, "failed": str(error)}
    # all sections' raw values, for the monthly check (never shown)
    weekly_dir = area.data_dir / "weekly"
    weekly_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        weekly_dir / f"{monday}.npz",
        section_ids=np.array([r["section_id"] for r in levels]),
        value=np.array([r["monitor_value"] for r in levels]),
    )
    by_key = {r["section_id"]: r for r in levels}
    for row in rows:
        ids = project_section_ids(db, row.project_id, CHICAGO)
        run = _start_run(db, row.project_id, "weekly_levels", monday, version)
        db.add_all(
            RiskLevel(
                run_id=run.id,
                section_id=sid,
                rank=by_key[key]["rank"],
                level=by_key[key]["level"],
                reasons=by_key[key]["reasons"],
                missing_inputs=by_key[key]["missing_inputs"],
                monitor_value=by_key[key]["monitor_value"],
            )
            for key, sid in ids.items()
            if key in by_key
        )
        _finish(
            run,
            reports_until=newest,
            new_reports=added,
            new_matches=matched,
            sections_in_city=len(levels),
        )
        row.last_weekly_run = monday
    db.commit()
    return {"projects": len(rows), "new_reports": added}


# ---------- monthly check of the raw values (F4-D2) ----------


def monitor(db: Session, now: datetime) -> dict[str, Any]:
    """Each month whose Mondays have a complete 30-day answer: raw values vs what happened."""
    import numpy as np
    from forecasting import live
    from forecasting import settings as fsettings
    from forecasting.metrics import calibration_table

    area = _area(CHICAGO)
    files = (
        sorted((area.data_dir / "weekly").glob("*.npz"))
        if (area.data_dir / "weekly").exists()
        else []
    )
    if not files:
        return {"months": 0}
    _, version = live.load_model(get_settings().forecast_models_dir)
    url = forecast_url()
    by_month: dict[date, list[Path]] = defaultdict(list)
    for path in files:
        monday = date.fromisoformat(path.stem)
        by_month[monday.replace(day=1)].append(path)
    done = {
        m
        for (m,) in db.execute(
            select(ForecastMonitoring.month).where(ForecastMonitoring.area_key == CHICAGO)
        )
    }
    checked = 0
    with fsettings.connect(url, CHICAGO) as fconn:
        newest = fconn.execute("SELECT max(day) FROM report_matches").fetchone()[0]
        for month, paths in sorted(by_month.items()):
            last_monday = max(date.fromisoformat(p.stem) for p in paths)
            if (
                month in done
                or newest is None
                or (last_monday - date(1970, 1, 1)).days + 30 > newest
            ):
                continue
            predicted, happened = [], []
            for path in paths:
                data = np.load(path)
                start = (date.fromisoformat(path.stem) - date(1970, 1, 1)).days
                hits = {
                    s
                    for (s,) in fconn.execute(
                        "SELECT DISTINCT section_id FROM report_matches "
                        "WHERE NOT is_duplicate AND day >= %s AND day < %s",
                        (start, start + 30),
                    )
                }
                predicted.append(data["value"])
                happened.append(np.array([s in hits for s in data["section_ids"]], dtype=float))
            table = calibration_table(np.concatenate(predicted), np.concatenate(happened))
            gap = max(abs(p - h) for p, h, _ in table) if table else None
            db.add(
                ForecastMonitoring(
                    area_key=CHICAGO,
                    month=month,
                    model_version=version,
                    sections=len(predicted[0]),
                    groups=[{"predicted": p, "happened": h, "rows": n} for p, h, n in table],
                    largest_gap=gap,
                    within_rule=None if gap is None else gap <= 0.02,
                )
            )
            checked += 1
    db.commit()
    return {"months": checked}


# ---------- hourly tick (Celery Beat) ----------


def tick(db: Session, now: datetime | None = None) -> dict[str, Any]:
    """Run every part that is due. Each part is separate, so one failure never stops the others."""
    now = now or datetime.now(UTC)
    out: dict[str, Any] = {}
    for name, part in (("daily", daily), ("weekly", weekly), ("monitor", monitor)):
        try:
            out[name] = part(db, now)
        except ForecastingOffError as off:
            return {"off": str(off)}
        except Exception as error:  # noqa: BLE001
            db.rollback()
            out[name] = {"failed": str(error)[:300]}
            logger.warning("Forecast %s step failed: %s", name, error)
    try:  # F4e: alert rules after the jobs (each project separately; never stops the tick)
        from app.services import alerts

        out["alerts"] = alerts.run_all(db, now)
    except Exception as error:  # noqa: BLE001
        db.rollback()
        out["alerts"] = {"failed": str(error)[:300]}
        logger.warning("Forecast alerts failed: %s", error)
    return out
