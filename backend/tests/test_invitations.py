"""Invitations: create, check, accept, expiry, single use (AC-05, AC-52)."""

from collections.abc import Callable
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Invitation, User
from app.models.base import utc_now
from tests.factories import DEFAULT_PASSWORD, add_member, make_org, sign_in

NEW_PASSWORD = "a-brand-new-password"


def _invite(admin: TestClient, org_id: object, email: str = "new@a.test") -> dict[str, str]:
    response = admin.post(
        f"/api/v1/organizations/{org_id}/invitations",
        json={"email": email, "org_role": "org_member"},
    )
    assert response.status_code == 201, response.text
    body: dict[str, str] = response.json()
    return body


def _token(invite_url: str) -> str:
    return invite_url.rsplit("/", 1)[-1]


def test_invitation_link_is_shown_once_and_creates_account(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    org = make_org(db)
    admin = sign_in(make_client(), "admin@a.test")

    created = _invite(admin, org.id)
    assert created["invite_url"].startswith("http://testserver/invite/")
    listed = admin.get(f"/api/v1/organizations/{org.id}/invitations").json()["items"]
    assert len(listed) == 1 and "invite_url" not in listed[0]  # AC-52: not shown again

    newcomer = make_client()
    token = _token(created["invite_url"])
    info = newcomer.get(f"/api/v1/auth/invitations/{token}")
    assert info.status_code == 200
    assert info.json() == {
        "organization_name": "City A",
        "email": "new@a.test",
        "org_role": "org_member",
        "account_exists": False,
    }
    accepted = newcomer.post(
        f"/api/v1/auth/invitations/{token}/accept",
        json={"full_name": "New Person", "password": NEW_PASSWORD},
    )
    assert accepted.status_code == 200
    assert accepted.json() == {"result": "signed_in"}
    me = newcomer.get("/api/v1/auth/me").json()
    assert me["user"]["full_name"] == "New Person"
    assert me["memberships"][0]["organization_id"] == str(org.id)


def test_invitation_works_only_once(db: Session, make_client: Callable[[], TestClient]) -> None:
    """AC-05 (single use)."""
    org = make_org(db)
    admin = sign_in(make_client(), "admin@a.test")
    token = _token(_invite(admin, org.id)["invite_url"])
    body = {"full_name": "New Person", "password": NEW_PASSWORD}
    assert (
        make_client().post(f"/api/v1/auth/invitations/{token}/accept", json=body).status_code == 200
    )

    again = make_client().post(f"/api/v1/auth/invitations/{token}/accept", json=body)

    assert again.status_code == 410
    assert again.json()["error"]["details"] == {"reason": "used"}


def test_expired_invitation_is_refused(db: Session, make_client: Callable[[], TestClient]) -> None:
    """AC-05 (expiry)."""
    org = make_org(db)
    admin = sign_in(make_client(), "admin@a.test")
    token = _token(_invite(admin, org.id)["invite_url"])
    invitation = db.scalar(select(Invitation))
    assert invitation is not None
    invitation.expires_at = utc_now() - timedelta(seconds=1)
    db.commit()

    response = make_client().get(f"/api/v1/auth/invitations/{token}")

    assert response.status_code == 410
    assert response.json()["error"]["details"] == {"reason": "expired"}


def test_invitation_expires_after_seven_days(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    org = make_org(db)
    admin = sign_in(make_client(), "admin@a.test")
    _invite(admin, org.id)
    invitation = db.scalar(select(Invitation))
    assert invitation is not None

    lifetime = invitation.expires_at - invitation.created_at

    assert timedelta(days=7) - timedelta(minutes=1) < lifetime <= timedelta(days=7)


def test_new_invitation_replaces_the_old_link(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    org = make_org(db)
    admin = sign_in(make_client(), "admin@a.test")
    first = _token(_invite(admin, org.id)["invite_url"])
    second = _token(_invite(admin, org.id)["invite_url"])

    assert make_client().get(f"/api/v1/auth/invitations/{first}").json()["error"]["details"] == {
        "reason": "revoked"
    }
    assert make_client().get(f"/api/v1/auth/invitations/{second}").status_code == 200


def test_revoked_invitation_is_refused(db: Session, make_client: Callable[[], TestClient]) -> None:
    org = make_org(db)
    admin = sign_in(make_client(), "admin@a.test")
    created = _invite(admin, org.id)

    assert (
        admin.delete(f"/api/v1/organizations/{org.id}/invitations/{created['id']}").status_code
        == 204
    )
    response = make_client().get(f"/api/v1/auth/invitations/{_token(created['invite_url'])}")

    assert response.status_code == 410


def test_unknown_link_is_refused(db: Session, client: TestClient) -> None:
    response = client.get("/api/v1/auth/invitations/not-a-real-token")

    assert response.status_code == 410
    assert response.json()["error"]["details"] == {"reason": "invalid"}


def test_inviting_an_existing_member_is_a_conflict(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    org = make_org(db)
    add_member(db, org, "worker@a.test", "org_member")
    admin = sign_in(make_client(), "admin@a.test")

    response = admin.post(
        f"/api/v1/organizations/{org.id}/invitations",
        json={"email": "Worker@a.test", "org_role": "org_member"},
    )

    assert response.status_code == 409


def test_new_account_needs_name_and_password(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    org = make_org(db)
    admin = sign_in(make_client(), "admin@a.test")
    token = _token(_invite(admin, org.id)["invite_url"])

    short = make_client().post(
        f"/api/v1/auth/invitations/{token}/accept", json={"full_name": "X", "password": "short"}
    )
    missing = make_client().post(f"/api/v1/auth/invitations/{token}/accept", json={})

    assert short.status_code == 422
    assert missing.status_code == 422


def test_existing_account_joins_without_password_change(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    """An invite link must never let someone take over an existing account."""
    org_a = make_org(db, "City A", "admin@a.test")
    make_org(db, "City B", "admin@b.test")
    admin_b = sign_in(make_client(), "admin@b.test")
    other_org = admin_b.get("/api/v1/auth/me").json()["memberships"][0]["organization_id"]
    token = _token(_invite(admin_b, other_org, email="admin@a.test")["invite_url"])
    hash_before = db.scalar(select(User.password_hash).where(User.email == "admin@a.test"))

    newcomer = make_client()
    assert newcomer.get(f"/api/v1/auth/invitations/{token}").json()["account_exists"] is True
    response = newcomer.post(
        f"/api/v1/auth/invitations/{token}/accept",
        json={"full_name": "Attacker", "password": "attacker-password"},
    )

    assert response.json() == {"result": "sign_in_required"}
    assert newcomer.get("/api/v1/auth/me").status_code == 401  # not signed in
    db.expire_all()
    assert db.scalar(select(User.password_hash).where(User.email == "admin@a.test")) == hash_before
    me = sign_in(make_client(), "admin@a.test", DEFAULT_PASSWORD).get("/api/v1/auth/me").json()
    assert {m["organization_name"] for m in me["memberships"]} == {"City A", "City B"}
    assert org_a.id  # City A membership kept
