"""Road risk API and permissions (F4c; api-spec.md section 3.10, forecasting-f4-plan.md section 4).

Checks: who may see and change what (risk.view, risk.configure, alert.view), levels only with no
percentage or raw model value anywhere (owner decision F4-D2), switching on and off (with the
background set-up), "update now", the weather outlook, and alerts with read/unread per person.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core import queue
from app.core.permissions import (
    CONDITIONS,
    ORG_ADMIN_PROJECT_PERMISSIONS,
    PROJECT_ROLE_PERMISSIONS,
    Perm,
)
from app.models import (
    Alert,
    AuditEvent,
    ForecastSection,
    ForecastSettings,
    RiskFactorValue,
    RiskLevel,
    RiskRun,
    User,
    WeatherOutlook,
)
from app.services import road_risk
from tests.analysis_fixtures import Setup
from tests.factories import create_project, make_org, sign_in

HUGE = {
    "type": "Polygon",
    "coordinates": [[[-90.0, 40.0], [-88.0, 40.0], [-88.0, 42.0], [-90.0, 42.0], [-90.0, 40.0]]],
}


# ------------------------------------------------------------------ the policy (no database)
def test_who_gets_the_forecasting_permissions() -> None:
    """Plan F4 section 4 and F4d section 1: every project role holds risk.view, but reviewers,
    viewers and field collectors only when the project's manager allows it ("project_setting";
    default reviewers and viewers). risk.configure and alert.view: project managers only
    (roadmap 7.5); org admins through the manager set."""
    for role, keys in PROJECT_ROLE_PERMISSIONS.items():
        assert Perm.RISK_VIEW in keys, role
        conditional = CONDITIONS.get((role, Perm.RISK_VIEW)) == "project_setting"
        assert conditional == (role != "project_manager"), role
        assert (Perm.RISK_CONFIGURE in keys) == (role == "project_manager"), role
        assert (Perm.ALERT_VIEW in keys) == (role == "project_manager"), role
    assert {Perm.RISK_VIEW, Perm.RISK_CONFIGURE, Perm.ALERT_VIEW} <= ORG_ADMIN_PROJECT_PERMISSIONS
    assert road_risk.visible_roles(None) == ["technical_reviewer", "viewer"]


# ------------------------------------------------------------------ helpers
@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Capture the background tasks instead of sending them to the queue."""
    out: dict[str, list[Any]] = {"setup": [], "tick": []}
    monkeypatch.setattr(queue, "send_forecast_setup", lambda sid: out["setup"].append(sid))
    monkeypatch.setattr(queue, "send_forecast_tick", lambda: out["tick"].append(True))
    return out


def _url(s: Setup, path: str, project_id: str | None = None) -> str:
    return f"/api/v1/projects/{project_id or s.project_id}/{path}"


def _admin_id(db: Session) -> uuid.UUID:
    user_id = db.scalar(select(User.id).where(User.email == "admin@a.test"))
    assert user_id is not None
    return user_id


def _line(x: float) -> str:
    return f"SRID=4326;LINESTRING({x} 41.80, {x + 0.001} 41.80)"


def _run(db: Session, project_id: uuid.UUID, kind: str, as_of: date, **kw: Any) -> RiskRun:
    run = RiskRun(
        project_id=project_id,
        kind=kind,
        as_of=as_of,
        model_version=kw.pop("model_version", "forecast-chicago-0.2"),
        data_dates=kw.pop("data_dates", {"reports_until": "2026-10-25"}),
        status=kw.pop("status", "completed"),
        finished_at=datetime(2026, 10, 30, 12, tzinfo=UTC),
    )
    db.add(run)
    db.flush()
    return run


def _factor(
    run: RiskRun, section: ForecastSection, factor: str, value: Any, level: str, kind: str
) -> RiskFactorValue:
    return RiskFactorValue(
        run_id=run.id, section_id=section.id, factor=factor, value=value, level=level, kind=kind
    )


def seed(db: Session, project_id: str, level: int = 2) -> dict[str, Any]:
    """A ready project with three sections: a (high), b (medium), c (low) in the latest week."""
    pid = uuid.UUID(project_id)
    area = "chicago" if level == 2 else f"p_{pid.hex[:12]}"
    db.add(
        ForecastSettings(
            project_id=pid,
            enabled=True,
            level=level,
            area_key=area,
            status="ready",
            area_km2=3.9,
            last_weekly_run=date(2026, 10, 26) if level == 2 else None,
            last_daily_run=date(2026, 10, 30),
            message="3 road sections.",
            changed_by=_admin_id(db),
        )
    )
    sections = {}
    for i, key in enumerate("abc"):
        sections[key] = ForecastSection(
            area_key=area,
            section_key=f"{area}-{key}",
            name=f"Road {key.upper()}",
            road_type="residential",
            length_m=100.0,
            line=_line(-87.70 + i * 0.01),
        )
    db.add_all(sections.values())
    db.flush()
    a, b, c = sections["a"], sections["b"], sections["c"]
    if level == 2:
        old = _run(db, pid, "weekly_levels", date(2026, 10, 19))
        db.add_all(
            [
                RiskLevel(
                    run_id=old.id, section_id=a.id, rank=5000, level="low", monitor_value=0.02
                ),
                RiskLevel(run_id=old.id, section_id=b.id, rank=1, level="high", monitor_value=0.4),
            ]
        )
        new = _run(db, pid, "weekly_levels", date(2026, 10, 26))
        reasons = [
            {"input": "reports_365d", "value": 4.0, "push": 0.8},
            {"input": "freeze_thaw_14d", "value": 2.0, "push": 0.2},
        ]
        db.add_all(
            [
                RiskLevel(
                    run_id=new.id,
                    section_id=a.id,
                    rank=3,
                    level="high",
                    reasons=reasons,
                    missing_inputs=["lanes"],
                    monitor_value=0.31234,
                ),
                RiskLevel(
                    run_id=new.id, section_id=b.id, rank=40, level="medium", monitor_value=0.1
                ),
                RiskLevel(
                    run_id=new.id, section_id=c.id, rank=900, level="low", monitor_value=0.01
                ),
            ]
        )
        _run(db, pid, "weekly_levels", date(2026, 11, 2), status="failed")  # never shown
    factors = _run(db, pid, "daily_factors", date(2026, 10, 30), model_version="level1")
    rows = []
    for key, section in sections.items():
        freeze = {"a": (4.0, "low"), "b": (11.0, "high"), "c": (8.0, "medium")}[key]
        rows += [
            _factor(factors, section, "freeze_thaw_14d", freeze[0], freeze[1], "risk"),
            _factor(factors, section, "snow_mm_30d", 0.0, "low", "risk"),
            _factor(factors, section, "heavy_rain_days_30d", 1.0, "medium", "background"),
            _factor(factors, section, "flood_zone", None, "missing", "background"),
        ]
    db.add_all(rows)
    db.add(
        WeatherOutlook(
            project_id=pid,
            issued_at=datetime(2026, 10, 30, 10, tzinfo=UTC),
            source="NWS LOT grid 74,71",
            days=[
                {
                    "date": "2026-10-31",
                    "max_c": 3.0,
                    "min_c": -2.0,
                    "rain_mm": None,
                    "snow_mm": None,
                }
            ],
            freeze_thaw_days=1,
            frost_days=0,
            heavy_rain_days=0,
            snow_mm=0.0,
        )
    )
    alerts = [
        Alert(
            project_id=pid,
            type="turned_high",
            event_key="turned_high:2026-10-26",
            title="1 road section turned high risk",
            details={"sections": [str(a.id)]},
        ),
        Alert(
            project_id=pid,
            type="freeze_thaw_coming",
            event_key="freeze_thaw:2026-10-19",
            title="Freeze-thaw coming",
            details={},
            closed_at=datetime(2026, 10, 25, tzinfo=UTC),
        ),
    ]
    db.add_all(alerts)
    db.commit()
    return {"sections": sections, "alerts": alerts}


# ------------------------------------------------------------------ settings
def test_status_is_off_until_switched_on(s: Setup) -> None:
    viewer = s.viewer.get(_url(s, "forecast-settings"))
    assert viewer.status_code == 200, viewer.text
    body = viewer.json()
    assert body["enabled"] is False and body["status"] == "off" and body["can_configure"] is False
    assert body["label"] == "TRIAL FORECAST"
    assert body["notice"] == "Risk estimate, not a confirmed defect."
    assert s.admin.get(_url(s, "forecast-settings")).json()["can_configure"] is True
    assert s.ann_client.get(_url(s, "forecast-settings")).status_code == 403  # field collector


def test_only_managers_switch_forecasting_on_and_off(
    s: Setup, db: Session, sent: dict[str, list[Any]]
) -> None:
    for client in (s.viewer, s.reviewer, s.ann_client):
        response = client.put(_url(s, "forecast-settings"), json={"enabled": True})
        assert response.status_code == 403
    on = s.admin.put(_url(s, "forecast-settings"), json={"enabled": True})
    assert on.status_code == 200, on.text
    assert on.json()["status"] == "setting_up" and on.json()["enabled"] is True
    assert on.json()["area_km2"] is not None and on.json()["area_km2"] < 500
    assert len(sent["setup"]) == 1
    # switching on again while it is setting up does not start a second set-up
    assert s.admin.put(_url(s, "forecast-settings"), json={"enabled": True}).status_code == 200
    assert len(sent["setup"]) == 1

    off = s.admin.put(_url(s, "forecast-settings"), json={"enabled": False})
    assert off.json()["status"] == "off" and off.json()["enabled"] is False
    actions = list(
        db.scalars(select(AuditEvent.action).where(AuditEvent.action.like("forecast.%")))
    )
    assert sorted(actions) == ["forecast.disabled", "forecast.enabled"]


def test_a_queue_problem_is_shown_and_can_be_retried(
    s: Setup, monkeypatch: pytest.MonkeyPatch, sent: dict[str, list[Any]]
) -> None:
    def refuse(_settings_id: uuid.UUID) -> None:
        raise ConnectionError("queue is down")

    monkeypatch.setattr(queue, "send_forecast_setup", refuse)
    failed = s.admin.put(_url(s, "forecast-settings"), json={"enabled": True}).json()
    assert failed["status"] == "failed" and failed["message"] == road_risk.QUEUE_DOWN

    monkeypatch.setattr(queue, "send_forecast_setup", lambda sid: sent["setup"].append(sid))
    retried = s.admin.put(_url(s, "forecast-settings"), json={"enabled": True}).json()
    assert retried["status"] == "setting_up" and len(sent["setup"]) == 1


def test_too_large_areas_are_refused_without_a_set_up(s: Setup, sent: dict[str, list[Any]]) -> None:
    big = str(create_project(s.admin, name="Whole region", area=HUGE)["id"])
    body = s.admin.put(_url(s, "forecast-settings", big), json={"enabled": True}).json()
    assert body["status"] == "too_large" and "500" in body["message"]
    assert sent["setup"] == []


def test_archived_projects_cannot_be_changed(
    s: Setup, db: Session, sent: dict[str, list[Any]]
) -> None:
    db.execute(text("UPDATE projects SET archived_at = now() WHERE id = :id"), {"id": s.project_id})
    db.commit()
    assert s.admin.put(_url(s, "forecast-settings"), json={"enabled": True}).status_code == 409


# ------------------------------------------------------------------ risk
def test_the_list_shows_levels_and_reasons_never_a_percentage(s: Setup, db: Session) -> None:
    seed(db, s.project_id)
    response = s.viewer.get(_url(s, "risk"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert "monitor_value" not in response.text and "push" not in response.text
    assert "0.31" not in response.text  # the raw model value never leaves the server
    assert body["label"] == "TRIAL FORECAST" and body["status"]["level"] == 2
    assert body["levels_run"]["as_of"] == "2026-10-26"  # the failed later run is not shown
    assert body["levels_run"]["model_version"] == "forecast-chicago-0.2"
    assert body["factors_run"]["as_of"] == "2026-10-30"
    assert body["counts"] == {"high": 1, "medium": 1, "low": 1}
    assert [i["name"] for i in body["items"]] == ["Road A", "Road B", "Road C"]
    top = body["items"][0]
    assert (top["position"], top["level"], top["rank_in_area"]) == (1, "high", 3)
    assert [r["label"] for r in top["reasons"]] == [
        "Pothole reports here, last 12 months",
        "Freeze-thaw days, last 14 days",
    ]
    assert top["reasons"][0]["value"] == 4.0
    assert top["missing_inputs"] == ["Number of lanes"]
    flood = next(f for f in top["factors"] if f["factor"] == "flood_zone")
    assert flood == {
        "factor": "flood_zone",
        "label": "Flood zone",
        "value": None,
        "level": "missing",
        "kind": "background",
    }
    high = s.reviewer.get(_url(s, "risk"), params={"level": "high"}).json()
    assert high["total"] == 1 and high["items"][0]["name"] == "Road A"
    assert s.ann_client.get(_url(s, "risk")).status_code == 403  # field collector


def test_level_1_projects_are_ordered_by_their_risk_factors(s: Setup, db: Session) -> None:
    seed(db, s.project_id, level=1)
    body = s.admin.get(_url(s, "risk")).json()
    assert body["status"]["level"] == 1 and body["levels_run"] is None
    assert [(i["name"], i["level"]) for i in body["items"]] == [
        ("Road B", "high"),
        ("Road C", "medium"),
        ("Road A", "low"),
    ]
    assert all(i["rank_in_area"] is None and i["reasons"] == [] for i in body["items"])


def test_nothing_is_listed_until_set_up_is_ready(s: Setup, db: Session) -> None:
    seed(db, s.project_id)
    db.execute(text("UPDATE forecast_settings SET status = 'setting_up'"))
    db.commit()
    body = s.admin.get(_url(s, "risk")).json()
    assert body["total"] == 0 and body["status"]["status"] == "setting_up"


def test_map_and_one_section(s: Setup, db: Session) -> None:
    data = seed(db, s.project_id)
    features = s.viewer.get(_url(s, "risk/map")).json()["features"]
    assert len(features) == 3 and features[0]["geometry"]["type"] == "LineString"
    assert features[0]["properties"]["level"] == "high"

    a = data["sections"]["a"]
    detail = s.reviewer.get(_url(s, f"road-sections/{a.id}/risk"))
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["section"]["name"] == "Road A" and body["geometry"]["type"] == "LineString"
    assert body["history"] == [
        {"as_of": "2026-10-26", "level": "high", "rank_in_area": 3},
        {"as_of": "2026-10-19", "level": "low", "rank_in_area": 5000},
    ]
    assert body["inspections"] == [] and "monitor_value" not in detail.text
    assert s.viewer.get(_url(s, f"road-sections/{uuid.uuid4()}/risk")).status_code == 404

    # a section of another project is not found through this one
    other = str(create_project(s.admin, name="Second survey")["id"])
    assert s.admin.get(_url(s, f"road-sections/{a.id}/risk", other)).status_code == 404


def test_weather_outlook_and_recent_weather(s: Setup, db: Session) -> None:
    seed(db, s.project_id)
    body = s.viewer.get(_url(s, "weather")).json()
    assert body["outlook"]["source"] == "NWS LOT grid 74,71"
    assert (
        body["outlook"]["freeze_thaw_days"] == 1 and body["outlook"]["days"][0]["rain_mm"] is None
    )
    recent = {v["factor"]: v for v in body["recent"]["values"]}
    assert recent["freeze_thaw_14d"]["value"] == 8.0  # the middle of 4, 8 and 11
    assert recent["below_freezing_days_30d"]["level"] == "missing"  # not computed: never guessed
    assert s.ann_client.get(_url(s, "weather")).status_code == 403


def test_update_now(s: Setup, db: Session, sent: dict[str, list[Any]]) -> None:
    assert s.admin.post(_url(s, "risk-runs")).status_code == 409  # not switched on yet
    seed(db, s.project_id)
    assert s.reviewer.post(_url(s, "risk-runs")).status_code == 403
    response = s.admin.post(_url(s, "risk-runs"))
    assert response.status_code == 202, response.text
    assert sent["tick"] == [True]
    row = db.scalar(
        select(ForecastSettings).where(ForecastSettings.project_id == uuid.UUID(s.project_id))
    )
    db.refresh(row)
    assert row is not None and row.last_daily_run is None and row.last_weekly_run is None


# ------------------------------------------------------------------ alerts
def test_alerts_are_for_project_managers_only(
    s: Setup, db: Session, make_client: Callable[[], TestClient]
) -> None:
    data = seed(db, s.project_id)
    open_only = s.admin.get(_url(s, "alerts")).json()
    assert open_only["total"] == 1 and open_only["items"][0]["type"] == "turned_high"
    assert s.admin.get(_url(s, "alerts"), params={"include_closed": True}).json()["total"] == 2
    for client in (s.reviewer, s.viewer, s.ann_client):
        assert client.get(_url(s, "alerts")).status_code == 403

    bell = s.admin.get("/api/v1/notifications").json()
    assert bell["unread_count"] == 2 and bell["items"][0]["type"] == "turned_high"
    assert bell["items"][0]["project_name"] == "Main Street survey"
    assert s.reviewer.get("/api/v1/notifications").json() == {
        "items": [],
        "unread_count": 0,
        "manages_projects": False,
    }
    assert bell["manages_projects"] is True

    alert = data["alerts"][0]
    assert s.reviewer.post(f"/api/v1/notifications/{alert.id}/read").status_code == 403
    for _ in range(2):  # reading twice is fine
        assert s.admin.post(f"/api/v1/notifications/{alert.id}/read").status_code == 204
    bell = s.admin.get("/api/v1/notifications").json()
    assert bell["unread_count"] == 1 and bell["items"][0]["read"] is True
    assert s.admin.post(f"/api/v1/notifications/{uuid.uuid4()}/read").status_code == 404

    make_org(db, name="City B", admin_email="admin@b.test")
    stranger = sign_in(make_client(), "admin@b.test")
    assert stranger.post(f"/api/v1/notifications/{alert.id}/read").status_code == 404
    assert stranger.get("/api/v1/notifications").json()["unread_count"] == 0
