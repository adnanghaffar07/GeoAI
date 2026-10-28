"""Requests from new organizations and their review by platform admins (CR-004)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AuditEvent, Organization, OrganizationMembership, OrganizationRequest, User
from tests.factories import make_org, sign_in

SEND = "/api/v1/organization-requests"
LIST = "/api/v1/platform/organization-requests"
NEW_PASSWORD = "a-brand-new-password"

FORM = {
    "organization_name": "Naperville Public Works",
    "contact_name": "Pat Rivera",
    "contact_email": "Pat@Naperville.test",
    "phone": "630-555-0100",
    "city_or_agency": "City of Naperville",
    "note": "Pilot for spring road survey",
}


def _platform_admin(db: Session, make_client: Callable[[], TestClient]) -> TestClient:
    make_org(db, name="Code Automation", admin_email="boss@platform.test")
    user = db.scalar(select(User).where(User.email == "boss@platform.test"))
    assert user is not None
    user.is_platform_admin = True
    db.commit()
    return sign_in(make_client(), "boss@platform.test")


def _send(client: TestClient, **change: str) -> str:
    response = client.post(SEND, json={**FORM, **change})
    assert response.status_code == 202, response.text
    return response.json()["message"]


def test_anyone_can_send_a_request_and_nothing_else_is_created(
    db: Session, client: TestClient
) -> None:
    message = _send(client)

    assert "will review" in message
    saved = db.scalar(select(OrganizationRequest))
    assert saved is not None and saved.status == "pending"
    assert saved.contact_email == "pat@naperville.test"
    assert db.scalar(select(Organization)) is None  # no organization until approved
    assert db.scalar(select(User)) is None  # and no account


def test_a_second_waiting_request_for_the_same_email_is_refused(
    db: Session, client: TestClient
) -> None:
    _send(client)

    again = client.post(SEND, json={**FORM, "contact_email": "pat@naperville.test"})

    assert again.status_code == 409
    assert "already waiting" in again.json()["error"]["message"]


def test_robots_filling_the_hidden_field_are_ignored(db: Session, client: TestClient) -> None:
    response = client.post(SEND, json={**FORM, "website": "http://spam.test"})

    assert response.status_code == 202
    assert db.scalar(select(OrganizationRequest)) is None


def test_too_many_requests_from_one_address_are_refused(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "organization_requests_per_hour", 2)
    _send(client, contact_email="a@x.test")
    _send(client, contact_email="b@x.test")

    third = client.post(SEND, json={**FORM, "contact_email": "c@x.test"})

    assert third.status_code == 429


def test_missing_fields_are_explained(client: TestClient) -> None:
    response = client.post(SEND, json={**FORM, "organization_name": "", "contact_email": "x"})

    assert response.status_code == 422


def test_only_platform_admins_can_see_and_decide(
    db: Session, client: TestClient, make_client: Callable[[], TestClient]
) -> None:
    _send(client)
    request_id = str(db.scalar(select(OrganizationRequest.id)))
    make_org(db, name="Other City", admin_email="admin@other.test")
    org_admin = sign_in(make_client(), "admin@other.test")

    assert make_client().get(LIST).status_code == 401
    assert org_admin.get(LIST).status_code == 403
    assert org_admin.post(f"{LIST}/{request_id}/approve", json={}).status_code == 403
    assert org_admin.post(f"{LIST}/{request_id}/reject", json={"reason": "no"}).status_code == 403


def test_approving_creates_the_organization_and_an_invitation_that_works(
    db: Session, client: TestClient, make_client: Callable[[], TestClient]
) -> None:
    _send(client)
    boss = _platform_admin(db, make_client)
    listed = boss.get(LIST).json()
    assert listed["pending_count"] == 1
    request_id = listed["items"][0]["id"]

    approved = boss.post(f"{LIST}/{request_id}/approve", json={"note": "Known pilot"})

    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["request"]["status"] == "approved"
    assert body["request"]["decided_by_name"] == "Admin"
    org = db.scalar(select(Organization).where(Organization.name == FORM["organization_name"]))
    assert org is not None and body["request"]["organization_id"] == str(org.id)
    # The contact opens the link, sets a password and is the new organization's admin.
    token = body["invitation_url"].rsplit("/", 1)[1]
    newcomer = make_client()
    accepted = newcomer.post(
        f"/api/v1/auth/invitations/{token}/accept",
        json={"full_name": "Pat Rivera", "password": NEW_PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    me = newcomer.get("/api/v1/auth/me").json()
    assert me["memberships"][0]["organization_name"] == FORM["organization_name"]
    assert me["memberships"][0]["org_role"] == "org_admin"
    assert me["user"]["is_platform_admin"] is False
    actions = set(db.scalars(select(AuditEvent.action)))
    assert {"organization_request.created", "organization_request.approved"} <= actions
    assert boss.get(LIST).json()["pending_count"] == 0


def test_a_request_can_be_decided_only_once(
    db: Session, client: TestClient, make_client: Callable[[], TestClient]
) -> None:
    _send(client)
    boss = _platform_admin(db, make_client)
    request_id = boss.get(LIST).json()["items"][0]["id"]
    assert boss.post(f"{LIST}/{request_id}/approve", json={}).status_code == 200

    again = boss.post(f"{LIST}/{request_id}/approve", json={})
    reject = boss.post(f"{LIST}/{request_id}/reject", json={"reason": "Changed my mind"})

    assert again.status_code == 409 and reject.status_code == 409
    assert len(list(db.scalars(select(Organization)))) == 2  # platform org + the new one


def test_rejecting_needs_a_reason_and_creates_nothing(
    db: Session, client: TestClient, make_client: Callable[[], TestClient]
) -> None:
    _send(client)
    boss = _platform_admin(db, make_client)
    request_id = boss.get(LIST).json()["items"][0]["id"]

    assert boss.post(f"{LIST}/{request_id}/reject", json={"reason": ""}).status_code == 422
    rejected = boss.post(f"{LIST}/{request_id}/reject", json={"reason": "Not a road agency"})

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["decision_note"] == "Not a road agency"
    assert boss.get(LIST, params={"status": "rejected"}).json()["items"][0]["id"] == request_id
    new_org = select(Organization).where(Organization.name == FORM["organization_name"])
    assert db.scalar(new_org) is None
    # After a rejection the same email may ask again.
    _send(client)


def test_a_new_link_replaces_the_old_one(
    db: Session, client: TestClient, make_client: Callable[[], TestClient]
) -> None:
    _send(client)
    boss = _platform_admin(db, make_client)
    request_id = boss.get(LIST).json()["items"][0]["id"]
    first = boss.post(f"{LIST}/{request_id}/approve", json={}).json()["invitation_url"]

    second = boss.post(f"{LIST}/{request_id}/invitation-link").json()["invitation_url"]

    assert first != second
    old_token = first.rsplit("/", 1)[1]
    assert make_client().get(f"/api/v1/auth/invitations/{old_token}").status_code == 410
    new_token = second.rsplit("/", 1)[1]
    assert make_client().get(f"/api/v1/auth/invitations/{new_token}").status_code == 200
    admins = select(OrganizationMembership).where(OrganizationMembership.org_role == "org_admin")
    assert db.scalar(admins) is not None
