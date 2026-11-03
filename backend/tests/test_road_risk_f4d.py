"""Road risk screens, backend part (F4d; forecasting-f4d-design.md, approved 2026-10-30).

Checks: the project manager chooses who else sees road risk (owner request), road inspections
with no finding (plan, inspected, resolved, reopened; one open per road), the labelled export,
and that migration 0010 matches the models and can be undone.
"""

import csv
import io
import json
import uuid
from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from alembic import command
from app.core.database import get_engine
from app.models import AuditEvent, Base, ForecastSettings, Inspection
from tests.analysis_fixtures import Setup
from tests.conftest import BACKEND_DIR
from tests.factories import create_project
from tests.test_road_risk import _url, seed, sent  # noqa: F401 (sent is a fixture)


def _detail(client: Any, s: Setup) -> dict[str, Any]:
    response = client.get(f"/api/v1/projects/{s.project_id}")
    assert response.status_code == 200, response.text
    out: dict[str, Any] = response.json()
    return out


# ------------------------------------------------------------------ who can see road risk
def test_the_manager_chooses_who_else_sees_road_risk(s: Setup, db: Session) -> None:
    seed(db, s.project_id)
    # defaults: reviewers and viewers yes, field collectors no
    assert s.reviewer.get(_url(s, "risk")).status_code == 200
    assert s.viewer.get(_url(s, "risk")).status_code == 200
    assert s.ann_client.get(_url(s, "risk")).status_code == 403
    assert "risk.view" not in _detail(s.ann_client, s)["my_permissions"]
    assert "risk.view" in _detail(s.viewer, s)["my_permissions"]
    assert _detail(s.viewer, s)["road_risk_enabled"] is True

    # only managers change it
    body = {"visible_to_roles": ["technical_reviewer", "field_collector"]}
    assert s.reviewer.put(_url(s, "forecast-settings"), json=body).status_code == 403
    changed = s.admin.put(_url(s, "forecast-settings"), json=body)
    assert changed.status_code == 200, changed.text
    assert changed.json()["visible_to_roles"] == ["technical_reviewer", "field_collector"]
    assert changed.json()["status"] == "ready"  # switching visibility changes nothing else

    assert s.ann_client.get(_url(s, "risk")).status_code == 200
    assert "risk.view" in _detail(s.ann_client, s)["my_permissions"]
    assert s.viewer.get(_url(s, "risk")).status_code == 403
    assert s.viewer.get(_url(s, "risk/map")).status_code == 403
    assert "risk.view" not in _detail(s.viewer, s)["my_permissions"]
    assert s.admin.get(_url(s, "risk")).status_code == 200  # managers always

    events = list(
        db.scalars(select(AuditEvent).where(AuditEvent.action == "forecast.visibility_changed"))
    )
    assert len(events) == 1
    assert events[0].details == {
        "before": ["technical_reviewer", "viewer"],
        "after": ["technical_reviewer", "field_collector"],
    }
    bad = s.admin.put(_url(s, "forecast-settings"), json={"visible_to_roles": ["project_manager"]})
    assert bad.status_code == 422
    assert s.admin.put(_url(s, "forecast-settings"), json={}).status_code == 422


def test_visibility_can_be_chosen_before_switching_on(
    s: Setup,
    db: Session,
    sent: dict[str, list[Any]],  # noqa: F811
) -> None:
    body = s.admin.put(_url(s, "forecast-settings"), json={"visible_to_roles": []}).json()
    assert body["visible_to_roles"] == [] and body["enabled"] is False and body["status"] == "off"
    assert sent["setup"] == []
    assert _detail(s.admin, s)["road_risk_enabled"] is False

    on = s.admin.put(_url(s, "forecast-settings"), json={"enabled": True}).json()
    assert on["status"] == "setting_up" and on["visible_to_roles"] == []
    assert len(sent["setup"]) == 1
    assert s.reviewer.get(_url(s, "forecast-settings")).status_code == 403


# ------------------------------------------------------------------ road inspections
def test_road_inspection_from_plan_to_reopen(s: Setup, db: Session) -> None:
    data = seed(db, s.project_id)
    a = data["sections"]["a"]
    plan = {"owner_user_id": str(s.ann.user.id), "planned_date": "2026-11-02"}
    url = _url(s, f"road-sections/{a.id}/inspections")

    assert s.reviewer.post(url, json=plan).status_code == 403  # only managers plan
    created = s.admin.post(url, json=plan)
    assert created.status_code == 201, created.text
    inspection = created.json()
    assert inspection["section_id"] == str(a.id) and inspection["finding_id"] is None
    assert inspection["status"] == "planned" and inspection["owner_name"] == "ann"
    row = db.get(Inspection, uuid.UUID(inspection["id"]))
    assert row is not None and row.risk_level_id is not None  # linked to this week's level
    assert s.admin.post(url, json=plan).status_code == 409  # one open per road

    # the field collector owner sees the road (not its level) in "My inspections"
    mine = s.ann_client.get(_url(s, "inspections")).json()
    assert mine["total"] == 1
    item = mine["items"][0]
    assert item["finding"] is None and item["road"]["name"] == "Road A"
    assert "level" not in json.dumps(item["road"])
    assert s.bob_client.get(_url(s, "inspections")).json()["total"] == 0

    history_url = _url(s, f"road-sections/{a.id}/inspections")
    assert len(s.ann_client.get(history_url).json()) == 1  # the owner sees it
    assert s.viewer.get(history_url).status_code == 200  # road risk is visible to viewers
    assert s.bob_client.get(history_url).status_code == 403  # not his, and road risk hidden

    iid = inspection["id"]
    assert (
        s.ann_client.patch(f"/api/v1/inspections/{iid}", json={"status": "inspected"}).status_code
        == 200
    )
    need_note = s.ann_client.patch(f"/api/v1/inspections/{iid}", json={"status": "resolved"})
    assert need_note.status_code == 422
    done = s.ann_client.patch(
        f"/api/v1/inspections/{iid}", json={"status": "resolved", "outcome_note": "Two potholes"}
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "resolved"
    assert (
        s.bob_client.patch(f"/api/v1/inspections/{iid}", json={"status": "inspected"}).status_code
        == 404
    )

    again = s.admin.post(
        f"/api/v1/inspections/{iid}/reopen",
        json={
            "reason": "Check after the thaw",
            "owner_user_id": str(s.ann.user.id),
            "planned_date": "2026-12-01",
        },
    )
    assert again.status_code == 201, again.text
    assert again.json()["section_id"] == str(a.id) and again.json()["status"] == "planned"

    detail = s.admin.get(_url(s, f"road-sections/{a.id}/risk")).json()
    assert [i["status"] for i in detail["inspections"]] == ["planned", "reopened"]
    actions = list(
        db.scalars(
            select(AuditEvent.action)
            .where(AuditEvent.target_type == "inspection")
            .order_by(AuditEvent.created_at)
        )
    )
    assert actions == [
        "inspection.planned",
        "inspection.inspected",
        "inspection.resolved",
        "inspection.reopened",
    ]


def test_road_inspection_needs_a_road_of_this_project(s: Setup, db: Session) -> None:
    data = seed(db, s.project_id)
    other = str(create_project(s.admin, name="Second survey")["id"])
    plan = {"owner_user_id": str(s.ann.user.id), "planned_date": "2026-11-02"}
    a = data["sections"]["a"]
    wrong_project = s.admin.post(_url(s, f"road-sections/{a.id}/inspections", other), json=plan)
    assert wrong_project.status_code == 404
    unknown = s.admin.post(_url(s, f"road-sections/{uuid.uuid4()}/inspections"), json=plan)
    assert unknown.status_code == 404
    viewer_owner = {"owner_user_id": str(s.view.user.id), "planned_date": "2026-11-02"}
    refused = s.admin.post(_url(s, f"road-sections/{a.id}/inspections"), json=viewer_owner)
    assert refused.status_code == 422  # viewers cannot record inspections


# ------------------------------------------------------------------ export
def test_export_is_labelled_and_recorded(s: Setup, db: Session) -> None:
    seed(db, s.project_id)
    response = s.viewer.get(_url(s, "risk/export"), params={"format": "csv"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    text_body = response.text
    assert text_body.startswith("# TRIAL FORECAST. Risk estimate, not a confirmed defect.")
    assert "monitor" not in text_body and "0.31" not in text_body
    rows = list(csv.DictReader(line for line in io.StringIO(text_body) if not line.startswith("#")))
    assert [r["road"] for r in rows] == ["Road A", "Road B", "Road C"]
    assert rows[0]["level"] == "high"
    assert rows[0]["reason_1"] == "Pothole reports here, last 12 months: 4"
    assert rows[1]["high_or_medium_risk_factors"] == "Freeze-thaw days, last 14 days (high)"

    geo = s.admin.get(_url(s, "risk/export"), params={"format": "geojson"})
    collection = geo.json()
    assert collection["metadata"]["label"].startswith("TRIAL FORECAST")
    assert collection["features"][0]["geometry"]["type"] == "LineString"
    assert s.ann_client.get(_url(s, "risk/export")).status_code == 403
    exported = list(
        db.scalars(
            select(AuditEvent.details)
            .where(AuditEvent.action == "forecast.exported")
            .order_by(AuditEvent.created_at)
        )
    )
    assert exported == [{"format": "csv", "rows": 3}, {"format": "geojson", "rows": 3}]


# ------------------------------------------------------------------ migration 0010
def _alembic() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


def test_migration_0010_matches_the_models_and_can_be_undone(database_ready: None) -> None:
    with get_engine().connect() as connection:
        diffs = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    touched = [d for d in diffs if "inspections" in repr(d) or "visible_to_roles" in repr(d)]
    assert touched == []
    try:
        command.downgrade(_alembic(), "0009")
        columns = {c["name"] for c in inspect(get_engine()).get_columns("inspections")}
        assert {"project_id", "section_id"}.isdisjoint(columns)
        assert "visible_to_roles" not in {
            c["name"] for c in inspect(get_engine()).get_columns("forecast_settings")
        }
    finally:
        command.upgrade(_alembic(), "head")
    columns = {c["name"] for c in inspect(get_engine()).get_columns("inspections")}
    assert {"project_id", "section_id"} <= columns


def test_existing_settings_get_the_default_visibility(s: Setup, db: Session) -> None:
    seed(db, s.project_id)
    row = db.scalar(select(ForecastSettings))
    assert row is not None and row.visible_to_roles == ["technical_reviewer", "viewer"]
