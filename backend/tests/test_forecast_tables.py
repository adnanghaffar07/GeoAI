"""Road-risk forecasting tables (F4b, migration 0009; forecasting-f4b-design.md).

Checks that the migration matches the models, can be undone and redone, and that the tables'
rules hold: one setting per project, allowed levels and kinds, one open alert per event.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.core.database import get_engine
from app.models import (
    Alert,
    AlertRead,
    Base,
    ForecastMonitoring,
    ForecastSection,
    ForecastSettings,
    RiskFactorValue,
    RiskLevel,
    RiskRun,
    User,
    WeatherOutlook,
)
from tests.conftest import BACKEND_DIR
from tests.factories import create_project, make_org, sign_in

NEW_TABLES = {
    "forecast_settings",
    "forecast_sections",
    "risk_runs",
    "risk_levels",
    "risk_factor_values",
    "weather_outlooks",
    "alerts",
    "alert_reads",
    "forecast_monitoring",
}
LINE = "SRID=4326;LINESTRING(-87.70 41.80, -87.699 41.80)"


def _alembic() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


def _mentions_new(diff: object) -> bool:
    text_form = repr(diff)
    return any(name in text_form for name in NEW_TABLES) or "risk_level_id" in text_form


def test_migration_matches_the_models(database_ready: None) -> None:
    with get_engine().connect() as connection:
        diffs = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert [d for d in diffs if _mentions_new(d)] == []


def test_migration_can_be_undone_and_redone(database_ready: None) -> None:
    config = _alembic()
    try:
        command.downgrade(config, "0008")
        tables = set(inspect(get_engine()).get_table_names())
        assert not (NEW_TABLES & tables)
        columns = {c["name"] for c in inspect(get_engine()).get_columns("inspections")}
        assert "risk_level_id" not in columns
    finally:
        command.upgrade(config, "head")
    assert set(inspect(get_engine()).get_table_names()) >= NEW_TABLES


def _project(db: Session, make_client: Callable[[], TestClient]) -> tuple[uuid.UUID, uuid.UUID]:
    make_org(db)
    admin = sign_in(make_client(), "admin@a.test")
    project = create_project(admin)
    user_id = db.query(User.id).filter(User.email == "admin@a.test").scalar()
    return uuid.UUID(str(project["id"])), user_id


def test_rows_and_rules(db: Session, make_client: Callable[[], TestClient]) -> None:
    project_id, user_id = _project(db, make_client)
    settings = ForecastSettings(
        project_id=project_id, level=2, area_key="chicago", changed_by=user_id
    )
    section = ForecastSection(
        area_key="chicago",
        section_key="100-0-0",
        name="Test Ave",
        road_type="residential",
        length_m=100.0,
        line=LINE,
    )
    db.add_all([settings, section])
    db.flush()
    run = RiskRun(
        project_id=project_id,
        kind="weekly_levels",
        as_of=date(2026, 9, 28),
        model_version="forecast-chicago-0.2",
        data_dates={"reports_until": "2026-10-27"},
    )
    db.add(run)
    db.flush()
    db.add_all(
        [
            RiskLevel(
                run_id=run.id,
                section_id=section.id,
                rank=1,
                level="high",
                reasons=[{"input": "reports_365d", "value": 4}],
                monitor_value=0.21,
            ),
            RiskFactorValue(
                run_id=run.id,
                section_id=section.id,
                factor="freeze_thaw_14d",
                value=9.0,
                level="medium",
                kind="risk",
            ),
            WeatherOutlook(
                project_id=project_id,
                issued_at=datetime(2026, 10, 30, 10, tzinfo=UTC),
                source="NWS LOT grid 74,71",
                days=[],
                freeze_thaw_days=3,
                frost_days=1,
                heavy_rain_days=0,
                snow_mm=0.0,
            ),
            ForecastMonitoring(
                area_key="chicago",
                month=date(2026, 10, 1),
                model_version="forecast-chicago-0.2",
                sections=71979,
                groups=[],
            ),
        ]
    )
    db.commit()
    assert settings.status == "setting_up" and settings.enabled is True

    alert = Alert(
        project_id=project_id,
        type="freeze_thaw_coming",
        event_key="freeze_thaw:2026-11-02",
        title="Freeze-thaw warning",
        details={"sections": 1},
    )
    db.add(alert)
    db.commit()
    db.add(AlertRead(alert_id=alert.id, user_id=user_id))
    db.commit()

    # the same event cannot be open twice; once closed, a new one may open
    db.add(
        Alert(
            project_id=project_id,
            type="freeze_thaw_coming",
            event_key="freeze_thaw:2026-11-02",
            title="again",
            details={},
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.execute(text("UPDATE alerts SET closed_at = now()"))
    db.add(
        Alert(
            project_id=project_id,
            type="freeze_thaw_coming",
            event_key="freeze_thaw:2026-11-02",
            title="again",
            details={},
        )
    )
    db.commit()


@pytest.mark.parametrize(
    ("sql", "why"),
    [
        ("UPDATE forecast_settings SET level = 3", "level must be 1 or 2"),
        ("UPDATE forecast_settings SET status = 'maybe'", "status must be known"),
        (
            "INSERT INTO forecast_settings (id, project_id, level, area_key, changed_by) "
            "SELECT gen_random_uuid(), project_id, 1, 'x', changed_by FROM forecast_settings",
            "one per project",
        ),
        ("UPDATE risk_levels SET level = 'very high'", "only high / medium / low"),
        ("UPDATE risk_levels SET rank = 0", "rank starts at 1"),
        ("UPDATE risk_factor_values SET kind = 'warning'", "risk or background"),
        ("UPDATE risk_runs SET kind = 'hourly'", "known run kinds"),
        ("UPDATE forecast_sections SET length_m = 0", "length positive"),
    ],
)
def test_rules_are_enforced(
    db: Session, make_client: Callable[[], TestClient], sql: str, why: str
) -> None:
    test_rows_and_rules(db, make_client)
    with pytest.raises(IntegrityError):
        db.execute(text(sql))
        db.commit()
    db.rollback()
