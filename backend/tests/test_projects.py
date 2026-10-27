"""Projects and project teams: creation, visibility, editing, archiving, permissions.

Covers AC-02 (projects of another organization are invisible), AC-03 (blocked cells at
project level), AC-09 (drawn and uploaded areas), AC-11 (archived = read-only).
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import PROJECT_ROLE_PERMISSIONS, Perm
from app.models import ProjectMember
from tests.factories import (
    add_member,
    add_to_project,
    create_project,
    make_org,
    sign_in,
    user_id_of,
)
from tests.photos import AREA, make_photo

MULTI_AREA: dict[str, Any] = {
    "type": "MultiPolygon",
    "coordinates": [
        AREA["coordinates"],
        [
            [
                [-122.40, 37.77],
                [-122.39, 37.77],
                [-122.39, 37.78],
                [-122.40, 37.78],
                [-122.40, 37.77],
            ]
        ],
    ],
}


def test_creator_becomes_manager_and_reviewers_are_assigned(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    org = make_org(db)
    reviewer = add_member(db, org, "rev@a.test", "org_member")
    admin = sign_in(make_client(), "admin@a.test")

    project = create_project(admin, reviewer_ids=[str(reviewer.user.id)])

    detail = admin.get(f"/api/v1/projects/{project['id']}").json()
    assert detail["my_roles"] == ["project_manager"]
    assert detail["boundary"]["type"] == "MultiPolygon"
    assert detail["finding_type_keys"] == ["pothole", "surface_cracking"]
    assert Perm.PROJECT_EDIT in detail["my_permissions"]
    team = admin.get(f"/api/v1/projects/{project['id']}/members").json()["items"]
    assert {(m["email"], m["role"]) for m in team} == {
        ("admin@a.test", "project_manager"),
        ("rev@a.test", "technical_reviewer"),
    }


def test_uploaded_multipolygon_area_is_accepted(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    """AC-09 (GeoJSON upload path)."""
    make_org(db)
    admin = sign_in(make_client(), "admin@a.test")

    project = create_project(admin, area=MULTI_AREA)

    detail = admin.get(f"/api/v1/projects/{project['id']}").json()
    assert len(detail["boundary"]["coordinates"]) == 2


def test_self_crossing_area_is_refused_with_a_reason(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    make_org(db)
    admin = sign_in(make_client(), "admin@a.test")
    org_id = admin.get("/api/v1/auth/me").json()["memberships"][0]["organization_id"]
    bowtie = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]],
    }

    response = admin.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={
            "name": "Bad",
            "boundary": bowtie,
            "finding_type_keys": ["pothole"],
            "reviewer_user_ids": [user_id_of(admin)],
        },
    )

    assert response.status_code == 422
    assert "edges do not cross" in response.json()["error"]["message"]


@pytest.mark.parametrize(
    ("change", "expected_message"),
    [
        ({"finding_type_keys": ["not_a_type"]}, "finding types"),
        ({"reviewer_user_ids": ["00000000-0000-0000-0000-000000000001"]}, "not members"),
        ({"name": "   "}, "Some fields are invalid"),
        ({"survey_start": "2026-10-10", "survey_end": "2026-10-01"}, "Some fields are invalid"),
    ],
)
def test_invalid_project_input_is_refused(
    db: Session,
    make_client: Callable[[], TestClient],
    change: dict[str, Any],
    expected_message: str,
) -> None:
    make_org(db)
    admin = sign_in(make_client(), "admin@a.test")
    org_id = admin.get("/api/v1/auth/me").json()["memberships"][0]["organization_id"]
    body = {
        "name": "P",
        "boundary": AREA,
        "finding_type_keys": ["pothole"],
        "reviewer_user_ids": [user_id_of(admin)],
        **change,
    }

    response = admin.post(f"/api/v1/organizations/{org_id}/projects", json=body)

    assert response.status_code == 422
    assert expected_message in response.json()["error"]["message"]


def test_members_cannot_create_projects_but_managers_can(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    """Decision Q1."""
    org = make_org(db)
    add_member(db, org, "member@a.test", "org_member")
    add_member(db, org, "manager@a.test", "org_manager")

    def body_for(client: TestClient) -> dict[str, Any]:
        return {
            "name": "P",
            "boundary": AREA,
            "finding_type_keys": ["pothole"],
            "reviewer_user_ids": [user_id_of(client)],
        }

    member = sign_in(make_client(), "member@a.test")
    manager = sign_in(make_client(), "manager@a.test")

    assert (
        member.post(f"/api/v1/organizations/{org.id}/projects", json=body_for(member)).status_code
        == 403
    )
    assert (
        manager.post(f"/api/v1/organizations/{org.id}/projects", json=body_for(manager)).status_code
        == 201
    )


def test_projects_are_visible_only_to_their_team_and_org_admins(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    org = make_org(db)
    worker = add_member(db, org, "worker@a.test", "org_member")
    admin = sign_in(make_client(), "admin@a.test")
    worker_client = sign_in(make_client(), worker.email)
    project = create_project(admin)
    url = f"/api/v1/projects/{project['id']}"

    assert worker_client.get(url).status_code == 404
    assert worker_client.get(f"/api/v1/organizations/{org.id}/projects").json()["total"] == 0

    add_to_project(admin, project["id"], worker.user.id, "field_collector")

    assert worker_client.get(url).status_code == 200
    assert worker_client.get(f"/api/v1/organizations/{org.id}/projects").json()["total"] == 1


def test_other_organization_cannot_reach_project_or_its_photos(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    """AC-02: projects, members, uploads, and photo files of City A are invisible to City B."""
    make_org(db, "City A", "admin@a.test")
    make_org(db, "City B", "admin@b.test")
    admin_a = sign_in(make_client(), "admin@a.test")
    admin_b = sign_in(make_client(), "admin@b.test")
    project = create_project(admin_a)
    upload = admin_a.post(
        f"/api/v1/projects/{project['id']}/images",
        files={"file": ("a.jpg", make_photo(), "image/jpeg")},
    ).json()
    image_id = upload["image"]["id"]

    urls = [
        ("GET", f"/api/v1/projects/{project['id']}"),
        ("GET", f"/api/v1/projects/{project['id']}/members"),
        ("GET", f"/api/v1/projects/{project['id']}/images"),
        ("GET", f"/api/v1/images/{image_id}"),
        ("GET", f"/api/v1/images/{image_id}/file"),
        ("GET", f"/api/v1/images/{image_id}/preview"),
        ("POST", f"/api/v1/images/{image_id}/withdraw"),
    ]
    for method, url in urls:
        assert admin_b.request(method, url).status_code == 404, url
    files = {"file": ("b.jpg", make_photo(seed=9), "image/jpeg")}
    assert admin_b.post(f"/api/v1/projects/{project['id']}/images", files=files).status_code == 404


# (method, path, permission, body or "photo")
PROJECT_ENDPOINTS: list[tuple[str, str, str, Any]] = [
    ("GET", "", Perm.PROJECT_VIEW, None),
    ("PATCH", "", Perm.PROJECT_EDIT, {"road_category": "local"}),
    ("GET", "/members", Perm.PROJECT_VIEW, None),
    ("GET", "/eligible-members", Perm.PROJECT_MEMBERS_MANAGE, None),
    ("GET", "/audit-events", Perm.PROJECT_AUDIT_VIEW, None),
    ("GET", "/images", Perm.IMAGE_STATUS_VIEW, None),
    ("POST", "/images", Perm.IMAGE_UPLOAD, "photo"),
    ("POST", "/archive", Perm.PROJECT_ARCHIVE, None),  # last: it ends editing
]


@pytest.mark.parametrize("role", ["field_collector", "technical_reviewer", "viewer"])
def test_every_blocked_project_permission_is_refused(
    role: str, db: Session, make_client: Callable[[], TestClient]
) -> None:
    """AC-03 at project level, generated from the policy in app/core/permissions.py."""
    org = make_org(db)
    person = add_member(db, org, f"{role}@a.test", "org_member")
    admin = sign_in(make_client(), "admin@a.test")
    project = create_project(admin)
    add_to_project(admin, project["id"], person.user.id, role)
    client = sign_in(make_client(), person.email)
    allowed = PROJECT_ROLE_PERMISSIONS[role]

    for method, path, permission, body in PROJECT_ENDPOINTS:
        url = f"/api/v1/projects/{project['id']}{path}"
        if body == "photo":
            files = {"file": ("x.jpg", make_photo(seed=hash(role) % 1000), "image/jpeg")}
            status = client.post(url, files=files).status_code
        else:
            status = client.request(method, url, json=body).status_code
        if permission in allowed:
            assert status not in (403, 404), (
                f"{role} should be allowed {method} {path}, got {status}"
            )
        else:
            assert status == 403, f"{role} should be refused {method} {path}, got {status}"


def test_archived_project_is_read_only(db: Session, make_client: Callable[[], TestClient]) -> None:
    """AC-11."""
    make_org(db)
    admin = sign_in(make_client(), "admin@a.test")
    project = create_project(admin)
    url = f"/api/v1/projects/{project['id']}"

    assert admin.post(f"{url}/archive").json()["archived"] is True
    assert admin.patch(url, json={"name": "New"}).status_code == 409
    upload = admin.post(f"{url}/images", files={"file": ("a.jpg", make_photo(), "image/jpeg")})
    assert upload.status_code == 409
    assert admin.get(url).status_code == 200  # still readable
    assert admin.get(f"{url}/audit-events").json()["items"][0]["action"] == "project.archived"


def test_edit_project_is_recorded(db: Session, make_client: Callable[[], TestClient]) -> None:
    make_org(db)
    admin = sign_in(make_client(), "admin@a.test")
    project = create_project(admin)

    response = admin.patch(
        f"/api/v1/projects/{project['id']}", json={"name": "Renamed", "boundary": MULTI_AREA}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    events = admin.get(f"/api/v1/projects/{project['id']}/audit-events").json()["items"]
    changed = next(e for e in events if e["action"] == "project.changed")
    assert changed["details"]["name"] == {"old": "Main Street survey", "new": "Renamed"}
    assert changed["details"]["boundary"] == "changed"


def test_saving_without_changes_adds_no_history(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    make_org(db)
    admin = sign_in(make_client(), "admin@a.test")
    project = create_project(admin)
    url = f"/api/v1/projects/{project['id']}"

    response = admin.patch(url, json={"name": project["name"], "road_category": None})

    assert response.status_code == 200
    events = admin.get(f"{url}/audit-events").json()["items"]
    assert not [e for e in events if e["action"] == "project.changed"]


def test_team_roles_can_be_combined_and_last_manager_is_protected(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    org = make_org(db)
    bo = add_member(db, org, "bo@a.test", "org_member")
    admin = sign_in(make_client(), "admin@a.test")
    project = create_project(admin)
    base = f"/api/v1/projects/{project['id']}/members"

    add_to_project(admin, project["id"], bo.user.id, "field_collector")
    add_to_project(admin, project["id"], bo.user.id, "technical_reviewer")  # combined roles (Q2)
    repeat = admin.post(base, json={"user_id": str(bo.user.id), "role": "field_collector"})
    assert repeat.status_code == 201  # repeated click is harmless
    bo_roles = sorted(
        m["role"] for m in admin.get(base).json()["items"] if m["email"] == "bo@a.test"
    )
    assert bo_roles == ["field_collector", "technical_reviewer"]

    manager_row = next(m for m in admin.get(base).json()["items"] if m["role"] == "project_manager")
    assert admin.delete(f"{base}/{manager_row['id']}").status_code == 409


def test_only_organization_members_can_join_a_project(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    make_org(db, "City A", "admin@a.test")
    org_b = make_org(db, "City B", "admin@b.test")
    outsider = add_member(db, org_b, "out@b.test", "org_member")
    admin = sign_in(make_client(), "admin@a.test")
    project = create_project(admin)

    response = admin.post(
        f"/api/v1/projects/{project['id']}/members",
        json={"user_id": str(outsider.user.id), "role": "viewer"},
    )

    assert response.status_code == 422


def test_leaving_the_organization_removes_project_roles(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    org = make_org(db)
    bo = add_member(db, org, "bo@a.test", "org_member")
    admin = sign_in(make_client(), "admin@a.test")
    project = create_project(admin)
    add_to_project(admin, project["id"], bo.user.id, "field_collector")

    assert admin.delete(f"/api/v1/organizations/{org.id}/members/{bo.user.id}").status_code == 204

    assert db.scalars(select(ProjectMember).where(ProjectMember.user_id == bo.user.id)).all() == []
