"""Inspection priority and inspections (P7).

Covers FR-39 to FR-44 and the P7 checkpoints: only verified findings are scored, the
breakdown shows inputs, weights and missing values, settings changes are new versions and
are audited, and inspections can be planned, recorded, resolved with evidence, and reopened
with history kept.
"""

import io
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image as PillowImage
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AuditEvent, Finding, PriorityScore
from tests.analysis_fixtures import Setup

TODAY = "2026-10-20"


def _verify(s: Setup, finding: dict[str, Any], severity: str = "high") -> dict[str, Any]:
    response = s.reviewer.post(
        f"/api/v1/findings/{finding['id']}/review",
        json={
            "action": "verify",
            "version": finding["version"],
            "type_key": "pothole",
            "severity_key": severity,
        },
    )
    assert response.status_code == 200, response.text
    out: dict[str, Any] = response.json()
    return out


def _list(client: TestClient, s: Setup, **params: Any) -> Any:
    return client.get(f"/api/v1/projects/{s.project_id}/priority-list", params=params)


@pytest.fixture
def found(s: Setup, worker: list[str], use_detector: Any) -> list[dict[str, Any]]:
    s.upload(s.admin)
    s.start(s.admin)
    items: list[dict[str, Any]] = s.findings(s.reviewer).json()["items"]
    assert len(items) == 2
    return items


def _photo() -> bytes:
    buffer = io.BytesIO()
    PillowImage.new("RGB", (40, 30), (120, 120, 120)).save(buffer, format="JPEG")
    return buffer.getvalue()


# ------------------------------------------------------------------ scoring
def test_only_verified_findings_are_scored(s: Setup, found: list[dict[str, Any]]) -> None:
    """FR-39."""
    assert _list(s.admin, s).json()["total"] == 0

    _verify(s, found[0])

    listed = _list(s.admin, s).json()
    assert listed["total"] == 1
    assert listed["items"][0]["finding"]["id"] == found[0]["id"]


def test_the_breakdown_shows_inputs_weights_and_missing_values(
    s: Setup, found: list[dict[str, Any]]
) -> None:
    """FR-41: nothing is guessed. Placeholder settings: severity 0.5, road 0.3, facilities 0.2."""
    _verify(s, found[0], severity="high")

    item = _list(s.admin, s).json()["items"][0]

    inputs = {entry["key"]: entry for entry in item["breakdown"]["inputs"]}
    assert inputs["severity"]["value"] == "high"
    assert inputs["severity"]["points"] == 100
    assert inputs["severity"]["weight"] == 0.5
    assert inputs["severity"]["contribution"] == 50
    assert inputs["road_category"]["missing"] is True
    assert inputs["road_category"]["reason"] == "The project has no road category set."
    assert inputs["facility_proximity"]["missing"] is True
    assert "No facility map is loaded" in inputs["facility_proximity"]["reason"]
    assert item["score"] == 50
    assert item["breakdown"]["weight_covered"] == 0.5
    assert item["breakdown"]["missing"] == ["road_category", "facility_proximity"]

    s.admin.patch(f"/api/v1/projects/{s.project_id}", json={"road_category": "arterial"})
    item = _list(s.admin, s).json()["items"][0]
    assert item["score"] == 80  # 0.5 x 100 + 0.3 x 100
    assert item["breakdown"]["weight_covered"] == 0.8


def test_ranking_follows_the_score(s: Setup, found: list[dict[str, Any]]) -> None:
    low = _verify(s, found[0], severity="low")
    high = _verify(s, found[1], severity="high")

    items = _list(s.admin, s).json()["items"]

    assert [item["finding"]["id"] for item in items] == [high["id"], low["id"]]
    assert items[0]["score"] > items[1]["score"]


def test_settings_are_versions_and_changes_are_audited(
    db: Session, s: Setup, found: list[dict[str, Any]]
) -> None:
    _verify(s, found[0], severity="medium")
    first = _list(s.admin, s).json()
    assert first["config"]["version"] == 1 and first["config"]["is_placeholder"] is True
    body = {
        "weights": {"severity": 1, "road_category": 0, "facility_proximity": 0},
        "severity_points": {"low": 10, "medium": 20, "high": 30},
        "road_category_points": {"arterial": 100},
        "facility_types": ["school"],
        "facility_radius_m": 150,
        "is_placeholder": False,
    }

    saved = s.admin.post(f"/api/v1/projects/{s.project_id}/priority-configs", json=body)

    assert saved.status_code == 201, saved.text
    assert saved.json()["version"] == 2 and saved.json()["created_by_name"] == "Admin"
    second = _list(s.admin, s).json()
    assert second["items"][0]["score"] == 20
    configs = s.admin.get(f"/api/v1/projects/{s.project_id}/priority-configs").json()["items"]
    assert [(c["version"], c["is_current"]) for c in configs] == [(2, True), (1, False)]
    # The score made with version 1 is kept with version 1.
    scores = db.scalars(
        select(PriorityScore).where(PriorityScore.finding_id == found[0]["id"])
    ).all()
    assert sorted(float(score.score) for score in scores) == [20.0, 33.35]
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "priority_config.created"))
    assert event is not None and event.details["version"] == 2


@pytest.mark.parametrize(
    "change",
    [
        {"weights": {"severity": 0.5, "road_category": 0.3, "facility_proximity": 0.1}},
        {"weights": {"severity": 1}},
        {"severity_points": {"extreme": 50}},
        {"severity_points": {"low": 150}},
        {"facility_radius_m": 0},
    ],
)
def test_bad_settings_are_refused(s: Setup, change: dict[str, Any]) -> None:
    body = {
        "weights": {"severity": 0.5, "road_category": 0.3, "facility_proximity": 0.2},
        "severity_points": {"low": 33, "medium": 67, "high": 100},
        "road_category_points": {},
        "facility_types": [],
        "facility_radius_m": 200,
        **change,
    }
    assert (
        s.admin.post(f"/api/v1/projects/{s.project_id}/priority-configs", json=body).status_code
        == 422
    )


def test_who_sees_and_changes_priority(s: Setup, found: list[dict[str, Any]]) -> None:
    _verify(s, found[0])
    body = {
        "weights": {"severity": 0.5, "road_category": 0.3, "facility_proximity": 0.2},
        "severity_points": {"low": 33, "medium": 67, "high": 100},
        "road_category_points": {},
        "facility_types": [],
        "facility_radius_m": 200,
    }

    assert _list(s.viewer, s).status_code == 200
    assert _list(s.reviewer, s).status_code == 200
    assert _list(s.ann_client, s).status_code == 403
    assert (
        s.reviewer.post(f"/api/v1/projects/{s.project_id}/priority-configs", json=body).status_code
        == 403
    )


# ------------------------------------------------------------------ inspections
def _plan(client: TestClient, finding_id: str, owner_id: str, day: str = TODAY) -> Any:
    return client.post(
        f"/api/v1/findings/{finding_id}/inspections",
        json={"owner_user_id": owner_id, "planned_date": day},
    )


def test_inspection_plan_inspect_resolve_and_reopen(
    db: Session, s: Setup, found: list[dict[str, Any]]
) -> None:
    """FR-43, FR-44: history is kept when an inspection is reopened."""
    finding = _verify(s, found[0])
    ann_id = str(s.ann.user.id)

    planned = _plan(s.admin, finding["id"], ann_id)
    assert planned.status_code == 201, planned.text
    inspection = planned.json()
    assert inspection["status"] == "planned" and inspection["owner_name"] == "ann"
    assert _plan(s.admin, finding["id"], ann_id).status_code == 409  # one open at a time

    # The owner (a collector) records it; another collector may not.
    url = f"/api/v1/inspections/{inspection['id']}"
    assert s.bob_client.patch(url, json={"status": "inspected"}).status_code == 404
    inspected = s.ann_client.patch(
        url, json={"status": "inspected", "outcome_note": "Hole 30 cm wide"}
    )
    assert inspected.status_code == 200 and inspected.json()["inspected_by_name"] == "ann"
    mine = s.ann_client.get(f"/api/v1/projects/{s.project_id}/inspections").json()
    assert mine["total"] == 1 and mine["items"][0]["finding"]["id"] == finding["id"]

    evidence = s.ann_client.post(
        f"{url}/evidence", files={"file": ("after.jpg", _photo(), "image/jpeg")}
    )
    assert evidence.status_code == 200 and evidence.json()["has_evidence"] is True
    assert s.admin.get(f"{url}/evidence").headers["content-type"] == "image/jpeg"
    resolved = s.ann_client.patch(url, json={"status": "resolved"})
    assert resolved.status_code == 200 and resolved.json()["status"] == "resolved"
    assert (
        db.scalar(select(Finding.inspection_status).where(Finding.id == finding["id"]))
        == "resolved"
    )
    assert s.ann_client.patch(url, json={"status": "inspected"}).status_code == 409

    assert (
        s.ann_client.post(
            f"{url}/reopen", json={"reason": "x", "owner_user_id": ann_id, "planned_date": TODAY}
        ).status_code
        == 403
    )
    reopened = s.admin.post(
        f"{url}/reopen",
        json={
            "reason": "Water still pooling",
            "owner_user_id": ann_id,
            "planned_date": "2026-11-01",
        },
    )
    assert reopened.status_code == 201, reopened.text
    history = s.admin.get(f"/api/v1/findings/{finding['id']}/inspections").json()
    assert [item["status"] for item in history] == ["reopened", "planned"]
    assert history[0]["reopen_reason"] == "Water still pooling"
    assert history[0]["has_evidence"] is True
    actions = db.scalars(
        text("SELECT action FROM audit_events WHERE action LIKE 'inspection.%' ORDER BY created_at")
    ).all()
    assert actions == [
        "inspection.planned",
        "inspection.inspected",
        "inspection.evidence_added",
        "inspection.resolved",
        "inspection.reopened",
    ]


def test_resolved_needs_a_note_or_a_photo(s: Setup, found: list[dict[str, Any]]) -> None:
    finding = _verify(s, found[0])
    inspection = _plan(s.admin, finding["id"], str(s.ann.user.id)).json()
    url = f"/api/v1/inspections/{inspection['id']}"

    assert s.admin.patch(url, json={"status": "resolved"}).status_code == 422
    assert s.admin.patch(url, json={"status": "resolved", "outcome_note": "  "}).status_code == 422
    assert (
        s.admin.patch(url, json={"status": "resolved", "outcome_note": "Filled"}).status_code == 200
    )


def test_inspections_need_a_verified_finding_and_a_project_member(
    s: Setup, found: list[dict[str, Any]], make_client: Any, db: Session
) -> None:
    from tests.factories import add_member, make_org

    assert _plan(s.admin, found[0]["id"], str(s.ann.user.id)).status_code == 409  # not verified
    finding = _verify(s, found[0])
    org = make_org(db, name="City B", admin_email="admin@b.test")
    outsider = add_member(db, org, "out@b.test", "org_member")

    assert _plan(s.admin, finding["id"], str(outsider.user.id)).status_code == 422
    assert _plan(s.reviewer, finding["id"], str(s.ann.user.id)).status_code == 403  # not a manager


def test_findings_with_an_inspection_must_stay_verified(
    s: Setup, found: list[dict[str, Any]]
) -> None:
    finding = _verify(s, found[0])
    _plan(s.admin, finding["id"], str(s.ann.user.id))

    response = s.reviewer.post(
        f"/api/v1/findings/{finding['id']}/review",
        json={"action": "reject", "version": finding["version"]},
    )

    assert response.status_code == 409


def test_evidence_must_be_a_photo(s: Setup, found: list[dict[str, Any]]) -> None:
    finding = _verify(s, found[0])
    inspection = _plan(s.admin, finding["id"], str(s.ann.user.id)).json()

    response = s.admin.post(
        f"/api/v1/inspections/{inspection['id']}/evidence",
        files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 415


def test_dashboard_numbers(s: Setup, found: list[dict[str, Any]]) -> None:
    finding = _verify(s, found[0])
    s.reviewer.post(
        f"/api/v1/findings/{found[1]['id']}/review",
        json={"action": "needs_field_check", "version": found[1]["version"]},
    )
    _plan(s.admin, finding["id"], str(s.ann.user.id))

    counts = s.admin.get(f"/api/v1/projects/{s.project_id}").json()["counts"]

    assert counts["findings_verified"] == 1
    assert counts["findings_needs_field_check"] == 1
    assert counts["findings_to_review"] == 0
    assert counts["verified_location_unconfirmed"] == 1
    assert counts["verified_by_type"] == {"pothole": 1}
    assert counts["inspections_open"] == 1


def test_an_older_inspection_cannot_be_reopened(s: Setup, found: list[dict[str, Any]]) -> None:
    """Reopening is only for the newest inspection (no clash with an open one)."""
    finding = _verify(s, found[0])
    ann = str(s.ann.user.id)
    first = _plan(s.admin, finding["id"], ann).json()
    s.admin.patch(
        f"/api/v1/inspections/{first['id']}", json={"status": "resolved", "outcome_note": "ok"}
    )
    assert _plan(s.admin, finding["id"], ann).status_code == 201

    response = s.admin.post(
        f"/api/v1/inspections/{first['id']}/reopen",
        json={"reason": "again", "owner_user_id": ann, "planned_date": TODAY},
    )

    assert response.status_code == 409


def test_the_owner_must_be_able_to_record(s: Setup, found: list[dict[str, Any]]) -> None:
    finding = _verify(s, found[0])

    assert _plan(s.admin, finding["id"], str(s.view.user.id)).status_code == 422  # a viewer
    assert _plan(s.admin, finding["id"], str(s.rev.user.id)).status_code == 201  # a reviewer


def test_collectors_see_only_their_own_inspections_of_a_finding(
    s: Setup, found: list[dict[str, Any]]
) -> None:
    finding = _verify(s, found[0])
    first = _plan(s.admin, finding["id"], str(s.bob.user.id)).json()
    s.admin.patch(
        f"/api/v1/inspections/{first['id']}",
        json={"status": "resolved", "outcome_note": "Bob's note"},
    )
    s.admin.post(
        f"/api/v1/inspections/{first['id']}/reopen",
        json={"reason": "again", "owner_user_id": str(s.ann.user.id), "planned_date": TODAY},
    )

    mine = s.ann_client.get(f"/api/v1/findings/{finding['id']}/inspections").json()

    assert [item["owner_name"] for item in mine] == ["ann"]


def test_counts_people_may_not_see_are_hidden(s: Setup, found: list[dict[str, Any]]) -> None:
    viewer_counts = s.viewer.get(f"/api/v1/projects/{s.project_id}").json()["counts"]
    admin_counts = s.admin.get(f"/api/v1/projects/{s.project_id}").json()["counts"]

    assert admin_counts["findings_to_review"] == 2
    assert viewer_counts["findings_to_review"] == 0
