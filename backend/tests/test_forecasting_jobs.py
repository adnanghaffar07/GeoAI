"""Road-risk forecasting jobs (F4b): when parts are due, switching on, set-up, weekly levels,
daily factors and outlook, the monthly check, and recorded failures.

The flow tests need FORECAST_TEST_DATABASE_URL (a throwaway forecast database, set in
docker-compose.yml) and the forecasting code on the path (/ml in Docker). They load the made-up
city of the forecasting tests into that database and use fake web answers; the real forecast data
and folders are never touched.
"""

import importlib.util
import json
import os
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    ForecastMonitoring,
    ForecastSection,
    ForecastSettings,
    RiskFactorValue,
    RiskLevel,
    RiskRun,
    User,
    WeatherOutlook,
)
from app.services import forecasting
from tests.factories import create_project, make_org, sign_in

CHI = ZoneInfo("America/Chicago")
FORECAST_TEST_URL = os.environ.get("FORECAST_TEST_DATABASE_URL", "")
NEAR_TEST_ROAD = {  # around the made-up city's test road (lat 41.805, lon -87.695 to -87.684)
    "type": "Polygon",
    "coordinates": [
        [[-87.70, 41.80], [-87.68, 41.80], [-87.68, 41.81], [-87.70, 41.81], [-87.70, 41.80]]
    ],
}
HUGE = {"type": "Polygon", "coordinates": [[[-90, 40], [-88, 40], [-88, 42], [-90, 42], [-90, 40]]]}


def at(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=CHI)


# ---------- when parts are due ----------


def test_daily_is_due_from_six_once_a_day() -> None:
    assert forecasting.daily_due(at(2026, 11, 2, 5), None)  # never run yet: at once, at any hour
    assert not forecasting.daily_due(at(2026, 11, 2, 5), date(2026, 11, 1))
    assert forecasting.daily_due(at(2026, 11, 2, 6), None)
    assert forecasting.daily_due(at(2026, 11, 2, 6), date(2026, 11, 1))
    assert not forecasting.daily_due(at(2026, 11, 2, 23), date(2026, 11, 2))
    assert forecasting.daily_due(at(2026, 11, 5, 9), date(2026, 11, 2))  # days missed: caught up


def test_weekly_is_due_from_monday_seven_and_caught_up_later() -> None:
    assert forecasting.this_monday(at(2026, 11, 4, 12)) == date(2026, 11, 2)
    assert not forecasting.weekly_due(at(2026, 11, 2, 6), date(2026, 10, 26))  # Monday before 07:00
    assert forecasting.weekly_due(at(2026, 11, 2, 7), date(2026, 10, 26))
    assert not forecasting.weekly_due(at(2026, 11, 3, 7), date(2026, 11, 2))
    assert forecasting.weekly_due(
        at(2026, 11, 4, 1), date(2026, 10, 26)
    )  # missed Monday: caught up
    # UTC times are read as Chicago time: 12:30 UTC on a Monday is 06:30 in Chicago (winter)
    assert not forecasting.weekly_due(datetime(2026, 11, 2, 12, 30, tzinfo=UTC), date(2026, 10, 26))
    assert forecasting.weekly_due(at(2026, 11, 2, 6), None)  # never run yet: at once


def test_off_without_a_forecast_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORECAST_DATABASE_URL", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(forecasting.ForecastingOffError):
            forecasting.forecast_url()
    finally:
        get_settings.cache_clear()


# ---------- switching on ----------


def _manager(
    db: Session, make_client: Callable[[], TestClient], area: dict[str, Any]
) -> tuple[uuid.UUID, uuid.UUID]:
    make_org(db)
    admin = sign_in(make_client(), "admin@a.test")
    project = create_project(admin, area=area)
    user_id = db.scalar(select(User.id).where(User.email == "admin@a.test"))
    assert user_id is not None
    return uuid.UUID(str(project["id"])), user_id


def test_too_large_areas_are_not_set_up(db: Session, make_client: Callable[[], TestClient]) -> None:
    project_id, user_id = _manager(db, make_client, HUGE)
    row = forecasting.enable(db, project_id, user_id)
    assert row.status == "too_large" and row.area_km2 is not None and row.area_km2 > 30_000
    assert "500" in (row.message or "")
    with pytest.raises(ValueError, match="not waiting"):
        forecasting.setup(db, row.id)
    forecasting.disable(db, project_id, user_id)
    assert db.get(ForecastSettings, row.id).status == "off"  # type: ignore[union-attr]


# ---------- the whole flow on the made-up city ----------


class Response:
    def __init__(self, data: Any = None, body: bytes | None = None) -> None:
        self.status_code = 200
        self.content = body if body is not None else json.dumps(data).encode()
        self.text = self.content.decode()
        self._data = data

    def json(self) -> Any:
        return self._data

    def iter_content(self, _size: int) -> Iterator[bytes]:
        yield self.content


class FakeWeb:
    """Answers in order; records every request (no network)."""

    def __init__(self, answers: list[Response]) -> None:
        self.answers = list(answers)
        self.urls: list[str] = []

    def request(self, method: str, url: str, **kwargs: Any) -> Response:
        self.urls.append(url)
        return self.answers.pop(0)


def _fixture_module() -> Any:
    path = Path("/ml/tests/test_forecast_load.py")
    spec = importlib.util.spec_from_file_location("ml_forecast_fixture", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GRID = {
    "properties": {
        "updateTime": "2011-11-05T10:00:00+00:00",
        "maxTemperature": {
            "uom": "wmoUnit:degC",
            "values": [{"validTime": "2011-11-05T13:00:00+00:00/PT12H", "value": 2.0}],
        },
        "minTemperature": {
            "uom": "wmoUnit:degC",
            "values": [{"validTime": "2011-11-05T00:00:00+00:00/PT13H", "value": -3.0}],
        },
        "quantitativePrecipitation": {
            "uom": "wmoUnit:mm",
            "values": [{"validTime": "2011-11-06T12:00:00+00:00/PT6H", "value": 28.0}],
        },
        "snowfallAmount": {"uom": "wmoUnit:mm", "values": []},
    }
}
POINT = {
    "properties": {
        "forecastGridData": "https://api.weather.gov/gridpoints/LOT/1,1",
        "timeZone": "America/Chicago",
        "gridId": "LOT",
        "gridX": 1,
        "gridY": 1,
    }
}


@pytest.fixture
def forecast_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    if not FORECAST_TEST_URL:
        pytest.skip("Forecasting job tests need FORECAST_TEST_DATABASE_URL (docker-compose.yml).")
    pytest.importorskip("forecasting")
    from forecasting import load, weekly
    from forecasting import settings as fsettings

    fixture = _fixture_module()
    monkeypatch.setattr(
        fsettings, "FORECAST_DIR", tmp_path
    )  # every forecast data folder goes to a temporary place
    raw = tmp_path / "data" / "chicago" / "raw"
    raw.parent.mkdir(parents=True)
    fixture.make_raw_dir(raw)
    load.ensure_database(FORECAST_TEST_URL)
    with fsettings.connect(FORECAST_TEST_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS chicago CASCADE")
    load.run_load(FORECAST_TEST_URL, raw, fixture.SRC, fixture.RULES)
    with fsettings.connect(FORECAST_TEST_URL, "chicago") as conn:
        weekly.match_new_reports(conn, 20)
        conn.commit()
    models = tmp_path / "models"
    models.mkdir()
    _tiny_model(models)
    monkeypatch.setenv("FORECAST_DATABASE_URL", FORECAST_TEST_URL)
    monkeypatch.setenv("FORECAST_MODELS_DIR", str(models))
    get_settings.cache_clear()
    yield fixture
    get_settings.cache_clear()


def _tiny_model(folder: Path) -> None:
    """A small model built like forecast-chicago-0.2 (same inputs, same steps) + fingerprint."""
    import joblib
    import numpy as np
    from forecasting.download import sha256_file
    from forecasting.f2_store import CATEGORICAL, FEATURES
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline, make_pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    numeric = [i for i, n in enumerate(FEATURES) if n not in CATEGORICAL]
    categorical = [i for i, n in enumerate(FEATURES) if n in CATEGORICAL]
    prepare = ColumnTransformer(
        [
            (
                "numbers",
                make_pipeline(
                    SimpleImputer(strategy="median", add_indicator=True), StandardScaler()
                ),
                numeric,
            ),
            ("categories", OneHotEncoder(handle_unknown="ignore"), categorical),
        ]
    )
    rng = np.random.default_rng(1)
    x = rng.integers(0, 4, (300, len(FEATURES))).astype(np.float32)
    x[::2, FEATURES.index("lanes")] = np.nan
    y = (x[:, FEATURES.index("reports_365d")] + rng.random(300) > 2.5).astype(int)
    model = Pipeline([("prepare", prepare), ("model", LogisticRegression(max_iter=2000))]).fit(x, y)
    joblib.dump(model, folder / "b1_logistic_v0.2.joblib")
    (folder / "f4a-models.json").write_text(
        json.dumps(
            {
                "version": "forecast-chicago-0.2",
                "fingerprints": {
                    "b1_logistic_v0.2.joblib": sha256_file(folder / "b1_logistic_v0.2.joblib")
                },
            }
        )
    )


def test_chicago_project_flow(
    db: Session, make_client: Callable[[], TestClient], forecast_db: Any, tmp_path: Path
) -> None:
    project_id, user_id = _manager(db, make_client, NEAR_TEST_ROAD)

    # switch on and set up: inside the (made-up) city, so Level 2 on the Chicago area
    row = forecasting.enable(db, project_id, user_id)
    assert row.status == "setting_up" and row.area_km2 is not None and 1 < row.area_km2 < 5
    row = forecasting.setup(db, row.id)
    assert (row.status, row.level, row.area_key) == ("ready", 2, "chicago"), row.message
    sections = db.scalar(select(func.count()).select_from(ForecastSection))
    assert sections == 9 and "9 road sections" in (row.message or "")

    # weekly: no new reports (an answer with only the header), then the levels for Monday 2017-03-27
    header = ",".join(forecast_db.CURR_HEADER).encode() + b"\n"
    web = FakeWeb([Response(body=header)])
    out = forecasting.weekly(db, at(2017, 3, 27, 8), session=web)
    assert out == {"projects": 1, "new_reports": 0}
    assert web.urls == ["https://data.cityofchicago.org/resource/v6vf-nfxy.csv"]
    levels = list(db.scalars(select(RiskLevel)))
    assert len(levels) == 9 and sorted(level.rank for level in levels) == list(range(1, 10))
    assert [level.level for level in levels].count("high") == 1
    assert all(level.monitor_value is not None for level in levels)
    run = db.scalar(select(RiskRun).where(RiskRun.kind == "weekly_levels"))
    assert (
        run is not None
        and run.status == "completed"
        and run.model_version == "forecast-chicago-0.2"
    )
    assert run.data_dates["reports_until"] == "2023-03-01"
    assert (tmp_path / "data" / "chicago" / "weekly" / "2017-03-27.npz").exists()
    assert forecasting.weekly(db, at(2017, 3, 28, 9), session=FakeWeb([])) == {
        "projects": 0
    }  # once a week

    # daily: weather files again (both stations), risk factors, then the NWS outlook
    raw = tmp_path / "data" / "chicago" / "raw"
    weather = [
        Response(body=(raw / f"weather_{s}.csv").read_bytes())
        for s in ("USW00094846", "USW00014819")
    ]
    web = FakeWeb([*weather, Response(POINT), Response(GRID)])
    assert forecasting.daily(db, at(2011, 11, 5, 7), session=web) == {"projects": 1}
    values = list(db.scalars(select(RiskFactorValue)))
    assert len(values) == 9 * 10 and {v.kind for v in values} == {"risk", "background"}
    assert {v.level for v in values if v.factor == "freeze_thaw_14d"} == {
        "high"
    }  # every fixture day thaws and freezes
    outlook = db.scalar(select(WeatherOutlook))
    assert outlook is not None and outlook.source == "NWS LOT grid 1,1"
    assert (outlook.freeze_thaw_days, outlook.heavy_rain_days) == (1, 1)
    assert forecasting.daily(db, at(2011, 11, 5, 9), session=FakeWeb([])) == {
        "projects": 0
    }  # once a day

    # monthly check: March 2017 has its whole 30-day answer (reports known until 2023)
    assert forecasting.monitor(db, at(2023, 3, 2, 8)) == {"months": 1}
    check = db.scalar(select(ForecastMonitoring))
    assert (
        check is not None
        and check.month == date(2017, 3, 1)
        and check.sections == 9
        and check.within_rule is not None
    )
    assert forecasting.monitor(db, at(2023, 3, 3, 8)) == {"months": 0}  # each month once


def test_a_failed_set_up_is_recorded(
    db: Session,
    make_client: Callable[[], TestClient],
    forecast_db: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from forecasting import area_check

    outside = {
        "type": "Polygon",
        "coordinates": [
            [[-88.2, 41.7], [-88.19, 41.7], [-88.19, 41.71], [-88.2, 41.71], [-88.2, 41.7]]
        ],
    }
    project_id, user_id = _manager(db, make_client, outside)
    row = forecasting.enable(db, project_id, user_id)

    def no_network(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("Could not reach overpass-api.de")

    monkeypatch.setattr(area_check, "run", no_network)
    row = forecasting.setup(db, row.id)
    assert row.status == "failed"
    assert row.message == (
        "Set-up failed. OpenStreetMap could not be reached. "
        "This is usually a short internet or service problem."
    )
    run = db.scalar(select(RiskRun).where(RiskRun.kind == "setup"))
    assert run is not None and run.status == "failed"


def test_first_results_are_worked_out_right_after_set_up(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from app.workers import forecast_tasks

    ticks: list[object] = []
    for status, expected in (("ready", 1), ("failed", 1)):
        monkeypatch.setattr(
            forecasting, "setup", lambda _db, _id, status=status: SimpleNamespace(status=status)
        )
        monkeypatch.setattr(forecasting, "tick", lambda db: ticks.append(db) or {})
        forecast_tasks.setup_area(str(uuid.uuid4()))
        assert len(ticks) == expected  # only a finished set-up starts the first run
