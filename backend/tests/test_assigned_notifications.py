"""Personal "you have been asked to inspect" notifications (owner request 2026-11-03)."""

from sqlalchemy.orm import Session

from tests.analysis_fixtures import Setup
from tests.test_road_risk import _url, seed


def _plan(s: Setup, section_id: object, owner_id: object) -> str:
    response = s.admin.post(
        _url(s, f"road-sections/{section_id}/inspections"),
        json={"owner_user_id": str(owner_id), "planned_date": "2026-11-06"},
    )
    assert response.status_code == 201, response.text
    inspection_id: str = response.json()["id"]
    return inspection_id


def test_the_person_asked_to_inspect_gets_a_notification(s: Setup, db: Session) -> None:
    data = seed(db, s.project_id)
    road = data["sections"]["a"]
    assert s.ann_client.get("/api/v1/notifications").json()["manages_projects"] is False

    iid = _plan(s, road.id, s.ann.user.id)
    bell = s.ann_client.get("/api/v1/notifications").json()
    assert bell["manages_projects"] is True  # the bell shows for her now
    assert bell["unread_count"] == 1
    notice = bell["items"][0]
    assert notice["type"] == "inspection_assigned"
    assert notice["title"] == "You have been asked to inspect the road Road A by Friday 6 November"
    assert notice["details"]["path"] == f"/projects/{s.project_id}/priority"

    # only for her: not in the managers' project alert list, not for other people
    assert all(
        a["type"] != "inspection_assigned" for a in s.admin.get(_url(s, "alerts")).json()["items"]
    )
    assert s.bob_client.get("/api/v1/notifications").json()["unread_count"] == 0
    assert s.admin.get(f"/api/v1/notifications/{notice['id']}").status_code == 403
    assert s.ann_client.get(f"/api/v1/notifications/{notice['id']}").status_code == 200
    assert s.ann_client.post(f"/api/v1/notifications/{notice['id']}/read").status_code == 204
    assert s.ann_client.get("/api/v1/notifications").json()["unread_count"] == 0

    # it closes by itself when the inspection is resolved
    done = s.ann_client.patch(
        f"/api/v1/inspections/{iid}", json={"status": "resolved", "outcome_note": "Patched"}
    )
    assert done.status_code == 200, done.text
    closed = s.ann_client.get("/api/v1/notifications").json()["items"][0]
    assert closed["closed_at"] is not None


def test_no_notification_when_planning_for_yourself(s: Setup, db: Session) -> None:
    data = seed(db, s.project_id)
    admin_id = s.admin.get("/api/v1/auth/me").json()["user"]["id"]
    _plan(s, data["sections"]["b"].id, admin_id)
    items = s.admin.get("/api/v1/notifications").json()["items"]
    assert all(a["type"] != "inspection_assigned" for a in items)
