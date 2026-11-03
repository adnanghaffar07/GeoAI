"""Automatic alerts (F4e; forecasting-f4e-design.md).

Each rule creates one alert, never repeats it while open, closes it when the event is over, and
never carries a percentage."""

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Alert, ForecastSettings, WeatherOutlook
from app.services import alerts
from tests.analysis_fixtures import Setup
from tests.test_road_risk import seed

NOW = datetime(2026, 10, 30, 15, tzinfo=UTC)  # Friday 30 October, 10:00 Chicago time


def _seed(db: Session, s: Setup, level: int = 2) -> None:
    """The road-risk sample data, without its two sample alerts (these tests make their own)."""
    seed(db, s.project_id, level=level)
    db.execute(text("DELETE FROM alerts"))
    db.commit()


def _row(db: Session, s: Setup) -> ForecastSettings:
    row = db.scalar(
        select(ForecastSettings).where(ForecastSettings.project_id == uuid.UUID(s.project_id))
    )
    assert row is not None
    return row


def _open(db: Session, kind: str) -> list[Alert]:
    db.expire_all()
    return list(db.scalars(select(Alert).where(Alert.type == kind, Alert.closed_at.is_(None))))


def _outlook(db: Session, s: Setup, freeze_days: int, rain_mm: float = 0) -> None:
    db.execute(text("DELETE FROM weather_outlooks"))  # only the new outlook is the latest
    days = [
        {
            "date": f"2026-11-0{i + 1}",
            "max_c": 3.0 if i < freeze_days else 8.0,
            "min_c": -2.0 if i < freeze_days else 2.0,
            "rain_mm": rain_mm if i == 4 else 0.0,
            "snow_mm": 0.0,
        }
        for i in range(7)
    ]
    db.add(
        WeatherOutlook(
            project_id=uuid.UUID(s.project_id),
            issued_at=NOW,
            source="NWS LOT grid 74,71",
            days=days,
            freeze_thaw_days=freeze_days,
            frost_days=0,
            heavy_rain_days=1 if rain_mm >= 25 else 0,
            snow_mm=0.0,
        )
    )
    db.commit()


def test_road_turned_high_once_per_monday(s: Setup, db: Session) -> None:
    _seed(db, s)  # Road A: low on 19 Oct, high on 26 Oct; Road B: high, then medium
    alerts.evaluate(db, _row(db, s), NOW)
    found = _open(db, "turned_high")
    assert len(found) == 1 and found[0].title == "1 road turned high risk this week"
    roads = found[0].details["roads"]
    assert [(r["name"], r["level"], r["previous_level"]) for r in roads] == [
        ("Road A", "high", "low")
    ]
    assert roads[0]["reasons"][0] == "Pothole reports here, last 12 months: 4"
    assert found[0].details["label"] == "TRIAL FORECAST"
    assert "monitor_value" not in json.dumps(found[0].details) and "%" not in json.dumps(
        found[0].details
    )
    alerts.evaluate(db, _row(db, s), NOW)  # no repeat while open
    assert len(list(db.scalars(select(Alert).where(Alert.type == "turned_high")))) == 1


def test_freeze_thaw_needs_three_days_and_closes_after(s: Setup, db: Session) -> None:
    _seed(db, s)
    _outlook(db, s, freeze_days=2)
    alerts.evaluate(db, _row(db, s), NOW)
    assert _open(db, "freeze_thaw_coming") == []

    _outlook(db, s, freeze_days=3)
    alerts.evaluate(db, _row(db, s), NOW)
    found = _open(db, "freeze_thaw_coming")
    assert len(found) == 1
    assert found[0].title == "Freeze-thaw coming: 2 roads at high or medium risk"
    assert found[0].details["days"] == ["2026-11-01", "2026-11-02", "2026-11-03"]
    assert "National Weather Service" in found[0].details["source"]
    alerts.evaluate(db, _row(db, s), NOW)
    assert len(list(db.scalars(select(Alert).where(Alert.type == "freeze_thaw_coming")))) == 1

    later = datetime(2026, 11, 5, 15, tzinfo=UTC)  # the spell is over
    alerts.evaluate(db, _row(db, s), later)
    assert _open(db, "freeze_thaw_coming") == []


def test_heavy_rain_outside_chicago_is_for_the_whole_area(s: Setup, db: Session) -> None:
    _seed(db, s, level=1)
    _outlook(db, s, freeze_days=0, rain_mm=30)
    alerts.evaluate(db, _row(db, s), NOW)
    found = _open(db, "heavy_rain_coming")
    assert len(found) == 1 and found[0].title == "Heavy rain coming in this project area"
    assert found[0].details["days"] == ["2026-11-05"]
    assert _open(db, "turned_high") == []  # no weekly levels outside Chicago


def test_data_problem_opens_and_closes(s: Setup, db: Session) -> None:
    _seed(db, s)  # the latest weekly run (2 Nov) failed
    alerts.evaluate(db, _row(db, s), NOW)
    keys = sorted(a.event_key for a in _open(db, "data_problem"))
    assert keys == ["data_problem:weekly_levels:2026-11-02"]

    db.execute(text("UPDATE risk_runs SET status = 'completed' WHERE status = 'failed'"))
    db.commit()
    stale = datetime(2026, 11, 3, 15, tzinfo=UTC)  # daily last ran 30 Oct: more than 2 days ago
    alerts.evaluate(db, _row(db, s), stale)
    assert sorted(a.event_key for a in _open(db, "data_problem")) == ["data_problem:daily_stale"]


def test_alert_page_and_mark_all_read(s: Setup, db: Session) -> None:
    _seed(db, s)
    alerts.evaluate(db, _row(db, s), NOW)
    bell = s.admin.get("/api/v1/notifications").json()
    assert bell["unread_count"] == 2  # turned high and the data problem
    first = bell["items"][0]["id"]
    page = s.admin.get(f"/api/v1/notifications/{first}")
    assert page.status_code == 200 and page.json()["id"] == first
    assert s.reviewer.get(f"/api/v1/notifications/{first}").status_code == 403
    assert s.admin.post("/api/v1/notifications/read-all").status_code == 204
    assert s.admin.get("/api/v1/notifications").json()["unread_count"] == 0
