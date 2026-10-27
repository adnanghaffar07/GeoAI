"""Review of findings, manual observations and history (P6).

Covers FR-25 to FR-38 and the P6 checkpoints: verify needs a type and a severity chosen by
a person, the AI original is kept after edits, a stale save is refused with 409, every
action is in the history, manual observations start "awaiting review", and who may do what.
"""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.auth import load_project_context
from app.core.errors import ConflictError
from app.models import Finding, ReviewEvent, SeverityRubric, User
from app.schemas.findings import ReviewRequest
from app.services import findings as service
from tests.analysis_fixtures import Setup
from tests.factories import add_member, add_to_project, make_org, sign_in
from tests.photos import INSIDE


def _analysed(s: Setup) -> list[dict[str, Any]]:
    """Upload one photo, analyse it (2 suggestions) and return them, newest first."""
    s.upload(s.admin)
    s.start(s.admin)
    items: list[dict[str, Any]] = s.findings(s.reviewer).json()["items"]
    assert len(items) == 2
    return items


def _review(client: TestClient, finding: dict[str, Any], **body: Any) -> Any:
    payload = {"version": finding["version"], **body}
    return client.post(f"/api/v1/findings/{finding['id']}/review", json=payload)


@pytest.fixture
def found(s: Setup, worker: list[str], use_detector: Any) -> list[dict[str, Any]]:
    return _analysed(s)


# ------------------------------------------------------------------ verify
def test_verify_needs_a_type_and_a_severity_chosen_by_a_person(
    s: Setup,
    found: list[dict[str, Any]],
) -> None:
    """FR-31, FR-38: the AI's guess and score are never used as the type or severity."""
    finding = found[0]

    nothing = _review(s.reviewer, finding, action="verify")
    no_severity = _review(s.reviewer, finding, action="verify", type_key="pothole")

    assert nothing.status_code == 422
    assert nothing.json()["error"]["message"] == "Choose a type and a severity before verifying."
    assert no_severity.status_code == 422
    assert s.reviewer.get(f"/api/v1/findings/{finding['id']}").json()["version"] == 1


def test_verify_keeps_the_ai_original(
    db: Session,
    s: Setup,
    found: list[dict[str, Any]],
) -> None:
    """FR-33: the AI's answer and the original location stay as they were."""
    finding = found[0]

    response = _review(
        s.reviewer,
        finding,
        action="verify",
        type_key="surface_cracking",
        severity_key="high",
        notes="Edge of lane",
    )

    assert response.status_code == 200, response.text
    out = response.json()
    assert out["review_status"] == "verified"
    assert out["version"] == 2
    assert out["type_key"] == "surface_cracking" and out["severity_key"] == "high"
    assert out["severity_rubric_version"] == 1
    assert out["reviewed_by_name"] == "rev"
    for key in ("predicted_type_key", "predicted_confidence", "predicted_bbox", "model_version"):
        assert out[key] == finding[key]
    assert out["original_location"] == finding["original_location"]


def test_a_stale_save_is_refused(
    s: Setup,
    found: list[dict[str, Any]],
) -> None:
    """FR-35: two people review the same finding; the second save is refused."""
    finding = found[0]
    first = _review(s.admin, finding, action="needs_field_check")

    second = _review(s.reviewer, finding, action="reject", reason="Shadow")

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["details"] == {"current_version": 2}
    assert "changed by someone else" in second.json()["error"]["message"]
    current = s.reviewer.get(f"/api/v1/findings/{finding['id']}").json()
    assert current["review_status"] == "needs_field_check"


def test_a_save_based_on_an_older_copy_is_refused(
    db: Session,
    s: Setup,
    found: list[dict[str, Any]],
) -> None:
    """FR-35 when two saves arrive at the same moment: the request already holds a copy of
    the finding read before the other person's save. The check must use the database."""
    reviewer = db.scalar(select(User).where(User.email == "rev@a.test"))
    assert reviewer is not None
    ctx = load_project_context(db, reviewer, uuid.UUID(s.project_id))
    stale = service.get_visible_finding(db, ctx, uuid.UUID(found[0]["id"]))
    assert stale.version == 1

    assert _review(s.admin, found[0], action="needs_field_check").status_code == 200

    with pytest.raises(ConflictError):
        service.review(db, ctx, stale.id, ReviewRequest(action="reject", version=1))
    db.rollback()
    events = db.scalars(select(ReviewEvent).where(ReviewEvent.finding_id == stale.id)).all()
    assert [event.action for event in events] == ["needs_field_check"]


def test_a_new_severity_scale_is_recorded_even_for_the_same_level(
    db: Session,
    s: Setup,
    found: list[dict[str, Any]],
) -> None:
    """Saving "low" under scale v2 records v2, even if the finding was "low" on v1."""
    finding = _review(
        s.reviewer, found[0], action="verify", type_key="pothole", severity_key="low"
    ).json()
    assert finding["severity_rubric_version"] == 1
    v1 = db.scalar(select(SeverityRubric).where(SeverityRubric.is_current.is_(True)))
    assert v1 is not None
    v1.is_current = False
    db.flush()
    db.add(
        SeverityRubric(
            organization_id=v1.organization_id,
            version=2,
            levels=v1.levels,
            is_placeholder=True,
            is_current=True,
        )
    )
    db.commit()

    again = _review(s.reviewer, finding, action="edit", severity_key="low").json()

    assert again["severity_rubric_version"] == 2


def test_moving_the_pin_keeps_the_original_location(
    s: Setup,
    found: list[dict[str, Any]],
) -> None:
    finding = found[0]
    moved = {"latitude": 37.776, "longitude": -122.421}

    out = _review(s.reviewer, finding, action="edit", corrected_location=moved).json()

    assert out["corrected_location"] == moved
    assert out["location"] == moved
    assert out["location_quality"] == "reviewer_confirmed"
    assert out["original_location"]["latitude"] == pytest.approx(INSIDE[0], abs=1e-4)
    assert out["review_status"] == "ai_generated"  # editing is not a decision

    cleared = _review(s.reviewer, out, action="edit", corrected_location=None).json()

    assert cleared["corrected_location"] is None
    assert cleared["location"] == cleared["original_location"]
    assert cleared["location_quality"] == "approximate"


def test_the_ai_original_cannot_be_changed_through_review(
    db: Session,
    s: Setup,
    found: list[dict[str, Any]],
) -> None:
    """Unknown fields in a review request are ignored; the AI's answer stays the same."""
    finding = found[0]

    _review(
        s.reviewer,
        finding,
        action="edit",
        notes="x",
        predicted_type_key="other",
        predicted_confidence=0.01,
    )

    row = db.scalar(select(Finding).where(Finding.id == finding["id"]))
    assert row is not None
    assert row.predicted_type_key == finding["predicted_type_key"]
    assert float(row.predicted_confidence or 0) == pytest.approx(finding["predicted_confidence"])


def test_edit_without_changes_and_bad_values_are_refused(
    s: Setup,
    found: list[dict[str, Any]],
) -> None:
    finding = found[0]

    assert _review(s.reviewer, finding, action="edit").status_code == 422
    assert _review(s.reviewer, finding, action="edit", type_key="unicorn").status_code == 422
    assert _review(s.reviewer, finding, action="edit", severity_key="extreme").status_code == 422
    assert _review(s.reviewer, finding, action="nonsense").status_code == 422
    bad_point = {"latitude": 95, "longitude": 0}
    assert (
        _review(s.reviewer, finding, action="edit", corrected_location=bad_point).status_code == 422
    )


def test_decisions_can_be_changed_and_are_all_in_the_history(
    s: Setup,
    found: list[dict[str, Any]],
) -> None:
    """FR-34: who, when, what changed and the decision."""
    finding = found[0]
    rejected = _review(s.reviewer, finding, action="reject", reason="Shadow, not a pothole").json()
    verified = _review(
        s.reviewer, rejected, action="verify", type_key="pothole", severity_key="low"
    ).json()

    history = s.reviewer.get(f"/api/v1/findings/{finding['id']}/history").json()

    assert verified["version"] == 3
    assert [event["action"] for event in history] == ["reject", "verify"]
    assert history[0]["note"] == "Shadow, not a pothole"
    assert history[0]["actor_name"] == "rev"
    assert history[0]["actor_roles"] == ["org_member", "technical_reviewer"]
    assert history[0]["changes"]["review_status"] == {"old": "ai_generated", "new": "rejected"}
    assert history[1]["changes"]["severity_key"] == {"old": None, "new": "low"}
    assert history[1]["finding_version"] == 3


def test_history_rows_can_never_be_changed(
    db: Session,
    s: Setup,
    found: list[dict[str, Any]],
) -> None:
    _review(s.reviewer, found[0], action="reject")
    event_id = db.scalar(select(ReviewEvent.id))

    for statement in (
        "UPDATE review_events SET note = 'x' WHERE id = :id",
        "DELETE FROM review_events WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="can only be added"):
            db.execute(text(statement), {"id": event_id})
        db.rollback()


# ------------------------------------------------------------------ who may review
def test_only_technical_reviewers_review(
    db: Session,
    s: Setup,
    make_client: Callable[[], TestClient],
    found: list[dict[str, Any]],
) -> None:
    """Decision Q3: managers cannot review; people who cannot see the finding get not found."""
    org_id = s.admin.get("/api/v1/auth/me").json()["memberships"][0]["organization_id"]
    from app.models import Organization

    org = db.get(Organization, org_id)
    assert org is not None
    pm = add_member(db, org, "pm@a.test", "org_member")
    add_to_project(s.admin, s.project_id, pm.user.id, "project_manager")
    manager = sign_in(make_client(), pm.email)
    finding = found[0]
    body = {"action": "reject"}

    assert _review(manager, finding, **body).status_code == 403
    # Collectors and viewers cannot see unreviewed suggestions: "not found", existence hidden.
    assert _review(s.ann_client, finding, **body).status_code == 404
    assert _review(s.viewer, finding, **body).status_code == 404
    make_org(db, name="City B", admin_email="admin@b.test")
    other = sign_in(make_client(), "admin@b.test")
    assert _review(other, finding, **body).status_code == 404
    assert other.get(f"/api/v1/findings/{finding['id']}/history").status_code == 404
    assert s.ann_client.get(f"/api/v1/findings/{finding['id']}/history").status_code == 404


def test_archived_projects_cannot_be_reviewed(
    s: Setup,
    found: list[dict[str, Any]],
) -> None:
    assert s.admin.post(f"/api/v1/projects/{s.project_id}/archive").status_code == 200

    response = _review(s.reviewer, found[0], action="reject")

    assert response.status_code == 409


# ------------------------------------------------------------------ list, filters, map
def test_rejected_are_hidden_unless_asked_for(
    s: Setup,
    found: list[dict[str, Any]],
) -> None:
    """FR-28."""
    _review(s.reviewer, found[0], action="reject")

    assert s.findings(s.reviewer).json()["total"] == 1
    assert s.findings(s.reviewer, include_rejected="true").json()["total"] == 2
    assert s.findings(s.reviewer, review_status="rejected").json()["total"] == 1


def test_filters_apply_to_the_list_and_the_map_alike(
    s: Setup,
    worker: list[str],
    use_detector: Any,
) -> None:
    """FR-26, FR-27: findings without a location are in the list, not on the map."""
    s.upload(s.admin, seed=1)
    s.upload(s.admin, seed=2, gps=False)
    s.start(s.admin)
    items = s.findings(s.reviewer).json()["items"]
    pothole = next(i for i in items if i["predicted_type_key"] == "pothole" and i["location"])
    _review(s.reviewer, pothole, action="verify", type_key="pothole", severity_key="high")

    def both(**params: Any) -> tuple[int, int]:
        listed = s.reviewer.get(f"/api/v1/projects/{s.project_id}/findings", params=params).json()
        mapped = s.reviewer.get(
            f"/api/v1/projects/{s.project_id}/findings.geojson", params=params
        ).json()
        return listed["total"], len(mapped["features"])

    assert both() == (4, 2)
    assert both(has_location="false") == (2, 0)
    assert both(has_location="true") == (2, 2)
    assert both(review_status="verified") == (1, 1)
    assert both(severity_key="high") == (1, 1)
    assert both(type_key="surface_cracking") == (2, 1)
    assert both(review_status=["verified", "ai_generated"]) == (4, 2)
    assert both(created_from="2000-01-01", created_to="2000-01-02") == (0, 0)
    feature = s.reviewer.get(
        f"/api/v1/projects/{s.project_id}/findings.geojson", params={"review_status": "verified"}
    ).json()["features"][0]
    assert feature["properties"]["severity_key"] == "high"
    assert feature["properties"]["review_status"] == "verified"
    bad = s.reviewer.get(f"/api/v1/projects/{s.project_id}/findings?review_status=maybe")
    assert bad.status_code == 422


def test_viewers_see_verified_findings_and_their_photos_only(
    s: Setup,
    found: list[dict[str, Any]],
) -> None:
    """Decisions Q4 and Q5."""
    finding = found[0]
    photo = finding["photo"]["id"]
    assert s.findings(s.viewer).json()["total"] == 0
    assert s.viewer.get(f"/api/v1/images/{photo}/preview").status_code == 403

    _review(s.reviewer, finding, action="verify", type_key="pothole", severity_key="medium")

    listed = s.findings(s.viewer).json()
    assert listed["total"] == 1 and listed["items"][0]["review_status"] == "verified"
    assert s.viewer.get(f"/api/v1/images/{photo}/preview").status_code == 200
    assert s.findings(s.ann_client).json()["total"] == 1  # collectors see verified too


# ------------------------------------------------------------------ manual observations
def _add(client: TestClient, s: Setup, **body: Any) -> Any:
    return client.post(f"/api/v1/projects/{s.project_id}/findings", json=body)


def test_manual_observation_starts_awaiting_review(
    s: Setup,
) -> None:
    """FR-37: sidewalk problems are added by people and reviewed like AI ones."""
    response = _add(
        s.ann_client,
        s,
        type_key="sidewalk_observation",
        notes="  Raised slab near the bus stop  ",
        location={"latitude": INSIDE[0], "longitude": INSIDE[1]},
    )

    assert response.status_code == 201, response.text
    out = response.json()
    assert out["origin"] == "manual"
    assert out["review_status"] == "awaiting_review"
    assert out["type_key"] == "sidewalk_observation"
    assert out["notes"] == "Raised slab near the bus stop"
    assert out["location_source"] == "manual" and out["location_quality"] == "approximate"
    assert out["predicted_type_key"] is None and out["predicted_confidence"] is None
    assert out["created_by_name"] == "ann"

    queue = s.findings(s.reviewer, review_status="awaiting_review").json()
    assert queue["total"] == 1
    verified = _review(
        s.reviewer, out, action="verify", type_key="sidewalk_observation", severity_key="low"
    )
    assert verified.status_code == 200
    history = s.reviewer.get(f"/api/v1/findings/{out['id']}/history").json()
    assert [event["action"] for event in history] == ["create", "verify"]


def test_manual_observation_with_a_photo(
    s: Setup,
) -> None:
    own = s.upload(s.ann_client, seed=1)
    bobs = s.upload(s.bob_client, seed=2)

    with_photo = _add(s.ann_client, s, type_key="sidewalk_observation", notes="Crack", image_id=own)
    others = _add(s.ann_client, s, type_key="sidewalk_observation", notes="Crack", image_id=bobs)

    assert with_photo.status_code == 201
    assert with_photo.json()["photo"]["id"] == own
    assert with_photo.json()["location_source"] == "photo_gps"  # copied from the photo
    assert others.status_code == 404  # collectors use their own photos only


def test_manual_observation_needs_a_note_and_a_known_type(s: Setup) -> None:
    assert _add(s.ann_client, s, type_key="sidewalk_observation", notes="   ").status_code == 422
    assert _add(s.ann_client, s, type_key="unicorn", notes="x").status_code == 422
    assert _add(s.viewer, s, type_key="sidewalk_observation", notes="x").status_code == 403
    without_location = _add(s.ann_client, s, type_key="sidewalk_observation", notes="x").json()
    assert without_location["location"] is None
    assert without_location["location_quality"] == "missing"


# ------------------------------------------------------------------ settings for review
def test_review_options_and_severity_scales(s: Setup) -> None:
    options = s.reviewer.get(f"/api/v1/projects/{s.project_id}/review-options").json()

    types = {t["key"]: t for t in options["finding_types"]}
    assert types["pothole"]["in_project"] is True
    assert types["pavement_deterioration"]["in_project"] is False
    assert types["sidewalk_observation"]["source"] == "manual"
    rubric = options["severity_rubric"]
    assert [level["key"] for level in rubric["levels"]] == ["low", "medium", "high"]
    assert rubric["is_placeholder"] is True and rubric["version"] == 1

    org_id = s.admin.get("/api/v1/auth/me").json()["memberships"][0]["organization_id"]
    scales = s.admin.get(f"/api/v1/organizations/{org_id}/severity-rubrics").json()
    assert scales["total"] == 1 and scales["items"][0]["is_current"] is True
