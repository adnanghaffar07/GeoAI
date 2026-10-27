"""The Overview dashboard: right numbers, and each role sees only what it may see."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.analysis_fixtures import Setup
from tests.factories import create_project, make_org, sign_in


def _org(client: TestClient) -> str:
    org_id: str = client.get("/api/v1/auth/me").json()["memberships"][0]["organization_id"]
    return org_id


def _dash(client: TestClient, **params: Any) -> Any:
    return client.get(f"/api/v1/organizations/{_org(client)}/dashboard", params=params)


@pytest.fixture
def data(s: Setup, worker: list[str], use_detector: Any) -> dict[str, Any]:
    """Ann (collector) uploads 2 photos, Bob 1; all analysed (2 suggestions each);
    the reviewer verifies one and rejects one."""
    s.upload(s.ann_client, seed=1)
    s.upload(s.ann_client, seed=2, gps=False)
    s.upload(s.bob_client, seed=3)
    s.start(s.admin)
    items = s.findings(s.reviewer).json()["items"]
    located = next(i for i in items if i["location"])
    verified = s.reviewer.post(
        f"/api/v1/findings/{located['id']}/review",
        json={
            "action": "verify",
            "version": located["version"],
            "type_key": "pothole",
            "severity_key": "high",
        },
    ).json()
    other = next(i for i in items if i["id"] != located["id"])
    s.reviewer.post(
        f"/api/v1/findings/{other['id']}/review",
        json={"action": "reject", "version": other["version"]},
    )
    return {"verified": verified}


def test_managers_see_everything(s: Setup, data: dict[str, Any]) -> None:
    dash = _dash(s.admin, days=7).json()

    totals = dash["totals"]
    assert totals["photos"] == 3 and totals["photos_analysed"] == 3
    assert totals["photos_waiting_for_ai"] == 0
    assert totals["photos_missing_location"] == 1
    assert totals["waiting_review"] == 4 and totals["verified"] == 1 and totals["rejected"] == 1
    assert dash["review_status"] == {"waiting": 4, "verified": 1, "rejected": 1}
    assert dash["verified_by_type"] == {"pothole": 1}
    assert dash["verified_by_severity"] == {"high": 1}
    assert dash["inspection_status"] == {"none": 1}
    assert len(dash["activity"]) == 7
    today = dash["activity"][-1]
    assert today["photos"] == 3 and today["suggestions"] == 6 and today["verified"] == 1
    assert [item["finding_id"] for item in dash["top_priority"]] == [data["verified"]["id"]]
    assert dash["top_priority"][0]["score"] == 50  # severity high only; other inputs missing
    assert len(dash["map_points"]) == 1
    assert dash["projects"][0]["photos"] == 3
    assert {level["key"] for level in dash["severity_levels"]} == {"low", "medium", "high"}
    assert dash["access"]["candidates"] is True and dash["access"]["priority"] is True


def test_collectors_see_only_their_own_photos_and_no_suggestions(
    s: Setup, data: dict[str, Any]
) -> None:
    dash = _dash(s.ann_client).json()

    assert dash["access"]["photos_own_only"] is True
    assert dash["access"]["candidates"] is False and dash["access"]["priority"] is False
    assert dash["totals"]["photos"] == 2  # Ann's own uploads only
    assert dash["totals"]["waiting_review"] == 0
    assert "waiting" not in dash["review_status"] and "rejected" not in dash["review_status"]
    assert dash["review_status"] == {"verified": 1}
    assert all(day["suggestions"] == 0 for day in dash["activity"])
    assert dash["top_priority"] == []


def test_viewers_see_verified_findings_and_priority_but_no_photos(
    s: Setup, data: dict[str, Any]
) -> None:
    dash = _dash(s.viewer).json()

    assert dash["access"]["photos"] is False
    assert dash["totals"]["photos"] == 0
    assert dash["totals"]["waiting_review"] == 0 and dash["totals"]["rejected"] == 0
    assert dash["totals"]["verified"] == 1
    assert dash["access"]["priority"] is True and len(dash["top_priority"]) == 1


def test_one_project_and_bad_requests(
    db: Session, s: Setup, data: dict[str, Any], make_client: Callable[[], TestClient]
) -> None:
    other_project = str(create_project(s.admin, name="Second")["id"])

    one = _dash(s.admin, project_id=s.project_id).json()
    empty = _dash(s.admin, project_id=other_project).json()

    assert one["totals"]["photos"] == 3 and len(one["projects"]) == 1
    assert empty["totals"]["photos"] == 0 and empty["activity"]
    assert _dash(s.ann_client, project_id=other_project).status_code == 404  # not on that project
    assert _dash(s.admin, project_id=str(uuid.uuid4())).status_code == 404
    assert _dash(s.admin, days=12).status_code == 422
    make_org(db, name="City B", admin_email="admin@b.test")
    other = sign_in(make_client(), "admin@b.test")
    assert _dash(other, project_id=s.project_id).status_code == 404
    assert other.get(f"/api/v1/organizations/{_org(s.admin)}/dashboard").status_code == 404
