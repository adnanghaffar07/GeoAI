# ruff: noqa: E501
"""P9.3 failure paths (p9-system-testing-plan.md).

Already covered elsewhere: database or queue down in /api/health (test_health.py); queue down for
analysis, reports and road-risk set-up (test_analysis.py, test_reports.py, test_road_risk.py);
a broken or crashing detector (test_analysis.py); a failed area set-up (test_forecasting_jobs.py);
bad photo files (test_images.py); laptop off for days: catch-up and the data-problem alert
(test_forecasting_jobs.py, test_alerts.py).

Added here: a report that cannot be built, "Update now" with the worker down, one failing job part,
weather and outlook downloads failing, and the free AI model missing or unreachable. Each must give a
plain message, keep the rest working and recover by itself.
"""

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest
import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import queue
from app.models import ForecastSettings, RiskRun, WeatherOutlook
from app.services import alerts, assistant, forecasting, reports
from tests.analysis_fixtures import Setup
from tests.test_reports import _download, _request, report_worker  # noqa: F401 (fixture)
from tests.test_road_risk import _url, seed

NOW = datetime(2026, 11, 3, 14, tzinfo=UTC)  # 08:00 in Chicago: the daily part is due


def _row(db: Session, s: Setup) -> ForecastSettings:
    row = db.scalar(
        select(ForecastSettings).where(ForecastSettings.project_id == uuid.UUID(s.project_id))
    )
    assert row is not None
    return row


def test_a_report_that_cannot_be_built_fails_on_its_own(
    s: Setup,
    monkeypatch: pytest.MonkeyPatch,
    report_worker: None,  # noqa: F811
) -> None:
    def broken(_db: Session, _report: Any) -> Any:
        raise RuntimeError("disk full at /data/reports")

    monkeypatch.setattr(reports, "_render", broken)
    report = _request(s.admin, s, "csv").json()
    shown = s.admin.get(f"/api/v1/reports/{report['id']}").json()
    assert shown["status"] == "failed"
    assert (
        shown["failure_reason"] == "The report could not be created. Try again, or contact support."
    )
    assert "disk" not in shown["failure_reason"]  # no internal details
    assert _download(s.admin, report).status_code == 409


def test_update_now_works_while_the_worker_is_down(
    s: Setup, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(db, s.project_id)

    def refuse() -> None:
        raise ConnectionError("queue is down")

    monkeypatch.setattr(queue, "send_forecast_tick", refuse)
    assert s.admin.post(_url(s, "risk-runs")).status_code == 202  # the hourly check runs it later
    row = _row(db, s)
    db.refresh(row)
    assert row.last_daily_run is None


def test_one_failing_part_never_stops_the_others(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(_db: Session, _now: datetime) -> Any:
        raise RuntimeError("weather site down")

    monkeypatch.setattr(forecasting, "daily", crash)
    monkeypatch.setattr(forecasting, "weekly", lambda _db, _now: {"projects": 1})
    monkeypatch.setattr(forecasting, "monitor", lambda _db, _now: {"checked": 1})
    monkeypatch.setattr(alerts, "run_all", lambda _db, _now: {"opened": 0})
    out = forecasting.tick(db, NOW)
    assert "weather site down" in out["daily"]["failed"]
    assert out["weekly"] == {"projects": 1} and out["monitor"] == {"checked": 1}
    assert out["alerts"] == {"opened": 0}


def test_weather_download_failing_is_recorded_and_retried(
    s: Setup, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("forecasting")
    from forecasting import areas, risk_factors
    from forecasting import settings as fsettings

    seed(db, s.project_id)

    def no_network(*_a: Any, **_k: Any) -> Any:
        raise ConnectionError("Could not reach www.ncei.noaa.gov")

    monkeypatch.setattr(forecasting, "forecast_url", lambda: "postgresql://unused/forecast")
    monkeypatch.setattr(forecasting, "_area", lambda key: SimpleNamespace(key=key, schema=key))
    monkeypatch.setattr(forecasting, "_session", lambda: None)
    monkeypatch.setattr(areas, "ready_sources", lambda _area: None)
    monkeypatch.setattr(fsettings, "load_config", lambda _name: {})
    monkeypatch.setattr(risk_factors, "read_cutoffs", lambda: {"cutoffs": {}})
    monkeypatch.setattr(fsettings, "connect", no_network)

    assert forecasting.daily(db, NOW) == {"projects": 0}
    run = db.scalar(
        select(RiskRun).where(RiskRun.kind == "daily_factors", RiskRun.status == "failed")
    )
    assert run is not None and run.message is not None
    assert run.message == (
        "Weather and risk factors could not be updated. The weather history service (NOAA) could not be reached. "
        "This is usually a short internet or service problem."
    )
    row = _row(db, s)
    db.refresh(row)
    assert row.last_daily_run == date(2026, 10, 30)  # not marked done: the next hour tries again
    # The old results stay on screen while the download is failing.
    assert s.admin.get(_url(s, "risk")).status_code == 200


def test_outlook_download_failing_is_recorded(s: Setup, db: Session) -> None:
    seed(db, s.project_id)
    before = db.scalar(select(func.count()).select_from(WeatherOutlook))

    def no_network(*_a: Any, **_k: Any) -> Any:
        raise TimeoutError("api.weather.gov did not answer")

    forecasting._outlook(
        db, _row(db, s), date(2026, 11, 3), None, SimpleNamespace(fetch_outlook=no_network)
    )
    db.commit()
    run = db.scalar(select(RiskRun).where(RiskRun.kind == "outlook", RiskRun.status == "failed"))
    assert run is not None and run.message == (
        "Weather outlook could not be updated. The National Weather Service did not answer in time. "
        "This is usually a short internet or service problem."
    )
    assert db.scalar(select(func.count()).select_from(WeatherOutlook)) == before


def _missing_model(*_a: Any, **_k: Any) -> requests.Response:
    answer = requests.Response()
    answer.status_code = 404
    answer._content = b'{"error":"model \\"qwen2.5:0.5b\\" not found, try pulling it first"}'
    answer.url = "http://ollama:11434/api/chat"
    return answer


def _unreachable(*_a: Any, **_k: Any) -> requests.Response:
    raise requests.ConnectionError("ollama: Name or service not known")


@pytest.mark.parametrize(
    "model", [_missing_model, _unreachable], ids=["model-not-downloaded", "ollama-down"]
)
def test_assistant_answers_without_the_model(
    s: Setup, db: Session, monkeypatch: pytest.MonkeyPatch, model: Any
) -> None:
    seed(db, s.project_id)
    monkeypatch.setattr(assistant.requests, "post", model)
    assert (
        s.admin.put(_url(s, "forecast-settings"), json={"assistant_enabled": True}).status_code
        == 200
    )
    reply = s.admin.post(
        _url(s, "assistant"), json={"question": "Which roads should we inspect first?"}
    )
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["used_model"] is False and body["answer"] and body["sources"]
    assert "ollama" not in body["answer"].lower() and "not found" not in body["answer"]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            "HTTPSConnectionPool(host='www.ncei.noaa.gov', port=443): Read timed out.",
            "The weather history service (NOAA) did not answer in time. This is usually a short internet or service problem.",
        ),
        (
            "https://data.cityofchicago.org/x answered HTTP 503 after 3 tries",
            "Chicago's open data portal was busy or had a problem on its side. This is usually a short internet or service problem.",
        ),
        (
            "Name or service not known",
            "A data service could not be reached. Check that the internet is on.",
        ),
        ("area too large", "Unexpected problem: area too large"),
    ],
)
def test_download_problems_are_explained_in_plain_words(error: str, expected: str) -> None:
    assert forecasting.plain_reason(error) == expected
