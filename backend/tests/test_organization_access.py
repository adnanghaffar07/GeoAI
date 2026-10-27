"""Organization isolation, the permission gatekeeper, member management, and history.

Covers AC-01 (no cross-organization access), AC-03 (every blocked cell is blocked),
AC-04 (removed users lose access immediately), and AC-06 (role changes recorded).
"""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import ORG_ROLE_PERMISSIONS, Perm
from app.models import AuditEvent
from tests.factories import add_member, make_org, sign_in

ORG = "/api/v1/organizations/{org_id}"

# (method, path, required permission, JSON body). {user_id} is another member's ID.
ORG_ENDPOINTS: list[tuple[str, str, str, dict[str, Any] | None]] = [
    ("GET", ORG, Perm.ORG_VIEW, None),
    ("PATCH", ORG, Perm.ORG_SETTINGS_EDIT, {"name": "Renamed"}),
    ("GET", ORG + "/members", Perm.ORG_MEMBERS_VIEW, None),
    ("PATCH", ORG + "/members/{user_id}", Perm.ORG_MEMBERS_CHANGE_ROLE, {"org_role": "org_member"}),
    ("DELETE", ORG + "/members/{user_id}", Perm.ORG_MEMBERS_REMOVE, None),
    ("POST", ORG + "/members/{user_id}/password-reset", Perm.ORG_MEMBERS_RESET_PASSWORD, None),
    ("GET", ORG + "/invitations", Perm.ORG_MEMBERS_INVITE, None),
    (
        "POST",
        ORG + "/invitations",
        Perm.ORG_MEMBERS_INVITE,
        {"email": "x@a.test", "org_role": "org_member"},
    ),
    ("GET", ORG + "/audit-events", Perm.ORG_AUDIT_VIEW, None),
]


def _call(client: TestClient, method: str, path: str, body: dict[str, Any] | None) -> int:
    return client.request(method, path, json=body).status_code


def test_other_organization_is_invisible(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    """AC-01: an admin of City B gets 'not found' for everything in City A."""
    org_a = make_org(db, "City A", "admin@a.test")
    make_org(db, "City B", "admin@b.test")
    target = add_member(db, org_a, "worker@a.test", "org_member")
    b_admin = sign_in(make_client(), "admin@b.test")

    for method, path, _, body in ORG_ENDPOINTS:
        url = path.format(org_id=org_a.id, user_id=target.user.id)
        status = _call(b_admin, method, url, body)
        assert status == 404, f"{method} {url} returned {status}"


def test_unknown_organization_id_is_not_found(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    make_org(db)
    admin = sign_in(make_client(), "admin@a.test")

    assert admin.get(ORG.format(org_id=uuid.uuid4())).status_code == 404


@pytest.mark.parametrize("role", ["org_manager", "org_member"])
def test_every_blocked_permission_is_refused(
    role: str, db: Session, make_client: Callable[[], TestClient]
) -> None:
    """AC-03: for each endpoint, a role without its permission gets 403 (generated
    from the policy in app/core/permissions.py, so policy and tests stay in step)."""
    org = make_org(db)
    person = add_member(db, org, f"{role}@a.test", role)
    target = add_member(db, org, "target@a.test", "org_member")
    client = sign_in(make_client(), person.email)
    allowed = ORG_ROLE_PERMISSIONS[role]

    for method, path, permission, body in ORG_ENDPOINTS:
        url = path.format(org_id=org.id, user_id=target.user.id)
        status = _call(client, method, url, body)
        if permission in allowed:
            assert status not in (403, 404), f"{role} should be allowed {method} {url}"
        else:
            assert status == 403, f"{role} should be refused {method} {url}, got {status}"


def test_removed_member_loses_access_on_next_request(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    """AC-04."""
    org = make_org(db)
    worker = add_member(db, org, "worker@a.test", "org_member")
    admin = sign_in(make_client(), "admin@a.test")
    worker_client = sign_in(make_client(), worker.email)
    assert worker_client.get(ORG.format(org_id=org.id)).status_code == 200

    response = admin.delete(f"{ORG.format(org_id=org.id)}/members/{worker.user.id}")

    assert response.status_code == 204
    assert worker_client.get(ORG.format(org_id=org.id)).status_code == 401


def test_role_change_is_recorded_with_who_old_and_new(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    """AC-06."""
    org = make_org(db)
    worker = add_member(db, org, "worker@a.test", "org_member")
    admin = sign_in(make_client(), "admin@a.test")

    response = admin.patch(
        f"{ORG.format(org_id=org.id)}/members/{worker.user.id}", json={"org_role": "org_manager"}
    )

    assert response.status_code == 200
    assert response.json()["org_role"] == "org_manager"
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "member.role_changed"))
    assert event is not None
    assert event.target_id == worker.user.id
    assert event.details == {"old_role": "org_member", "new_role": "org_manager"}
    assert event.actor_roles == ["org_admin"]
    assert event.actor_user_id is not None and event.request_id


def test_last_admin_cannot_be_removed_or_demoted(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    org = make_org(db)
    admin = sign_in(make_client(), "admin@a.test")
    me = admin.get("/api/v1/auth/me").json()["user"]["id"]
    member_url = f"{ORG.format(org_id=org.id)}/members/{me}"

    demote = admin.patch(member_url, json={"org_role": "org_member"})
    remove = admin.delete(member_url)

    assert demote.status_code == remove.status_code == 409


def test_admin_can_step_down_when_another_admin_exists(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    org = make_org(db)
    add_member(db, org, "second@a.test", "org_admin")
    admin = sign_in(make_client(), "admin@a.test")
    me = admin.get("/api/v1/auth/me").json()["user"]["id"]

    response = admin.patch(
        f"{ORG.format(org_id=org.id)}/members/{me}", json={"org_role": "org_member"}
    )

    assert response.status_code == 200


def test_invalid_role_is_rejected(db: Session, make_client: Callable[[], TestClient]) -> None:
    org = make_org(db)
    worker = add_member(db, org, "worker@a.test", "org_member")
    admin = sign_in(make_client(), "admin@a.test")

    response = admin.patch(
        f"{ORG.format(org_id=org.id)}/members/{worker.user.id}", json={"org_role": "superuser"}
    )

    assert response.status_code == 422


def test_audit_log_lists_this_organizations_events_only(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    org_a = make_org(db, "City A", "admin@a.test")
    make_org(db, "City B", "admin@b.test")
    admin = sign_in(make_client(), "admin@a.test")
    admin.patch(ORG.format(org_id=org_a.id), json={"name": "City A Roads"})

    response = admin.get(f"{ORG.format(org_id=org_a.id)}/audit-events")

    assert response.status_code == 200
    body = response.json()
    actions = [item["action"] for item in body["items"]]
    assert "organization.settings_changed" in actions
    assert body["total"] == len(body["items"])
    names = [item["details"].get("name") for item in body["items"]]
    assert "City B" not in names


def test_history_rows_cannot_be_changed(db: Session) -> None:
    make_org(db)
    event = db.scalar(select(AuditEvent))
    assert event is not None
    event.action = "tampered"

    with pytest.raises(Exception, match="can only be added"):
        db.commit()
