"""Admin-created password reset links (CR-001, AC-51)."""

from collections.abc import Callable
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PasswordReset
from app.models.base import utc_now
from tests.factories import add_member, make_org, sign_in

NEW_PASSWORD = "my-new-secret-password"


def _create_link(admin: TestClient, org_id: object, user_id: object) -> str:
    response = admin.post(f"/api/v1/organizations/{org_id}/members/{user_id}/password-reset")
    assert response.status_code == 201, response.text
    url: str = response.json()["reset_url"]
    assert url.startswith("http://testserver/reset-password/")
    return url.rsplit("/", 1)[-1]


def test_reset_link_sets_password_once_and_signs_out_everywhere(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    org = make_org(db)
    worker = add_member(db, org, "worker@a.test", "org_member")
    admin = sign_in(make_client(), "admin@a.test")
    worker_session = sign_in(make_client(), worker.email)
    token = _create_link(admin, org.id, worker.user.id)

    assert make_client().get(f"/api/v1/auth/password-resets/{token}").json() == {
        "email": "worker@a.test"
    }
    used = make_client().post(
        f"/api/v1/auth/password-resets/{token}", json={"password": NEW_PASSWORD}
    )

    assert used.status_code == 204
    assert worker_session.get("/api/v1/auth/me").status_code == 401  # signed out everywhere
    again = make_client().post(
        f"/api/v1/auth/password-resets/{token}", json={"password": NEW_PASSWORD}
    )
    assert again.status_code == 410 and again.json()["error"]["details"] == {"reason": "used"}
    old = make_client().post(
        "/api/v1/auth/login", json={"email": worker.email, "password": worker.password}
    )
    assert old.status_code == 401
    sign_in(make_client(), worker.email, NEW_PASSWORD)


def test_reset_link_expires_after_one_hour(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    org = make_org(db)
    worker = add_member(db, org, "worker@a.test", "org_member")
    admin = sign_in(make_client(), "admin@a.test")
    token = _create_link(admin, org.id, worker.user.id)
    reset = db.scalar(select(PasswordReset))
    assert reset is not None
    assert reset.expires_at - reset.created_at <= timedelta(hours=1)
    reset.expires_at = utc_now() - timedelta(seconds=1)
    db.commit()

    response = make_client().post(
        f"/api/v1/auth/password-resets/{token}", json={"password": NEW_PASSWORD}
    )

    assert response.status_code == 410
    assert response.json()["error"]["details"] == {"reason": "expired"}


def test_only_the_newest_reset_link_works(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    org = make_org(db)
    worker = add_member(db, org, "worker@a.test", "org_member")
    admin = sign_in(make_client(), "admin@a.test")
    first = _create_link(admin, org.id, worker.user.id)
    second = _create_link(admin, org.id, worker.user.id)

    assert make_client().get(f"/api/v1/auth/password-resets/{first}").status_code == 410
    assert make_client().get(f"/api/v1/auth/password-resets/{second}").status_code == 200


def test_cannot_create_reset_link_for_someone_in_another_organization(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    org_a = make_org(db, "City A", "admin@a.test")
    org_b = make_org(db, "City B", "admin@b.test")
    outsider = add_member(db, org_b, "worker@b.test", "org_member")
    admin_a = sign_in(make_client(), "admin@a.test")

    response = admin_a.post(
        f"/api/v1/organizations/{org_a.id}/members/{outsider.user.id}/password-reset"
    )

    assert response.status_code == 404


def test_new_password_must_meet_length_rule(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    org = make_org(db)
    worker = add_member(db, org, "worker@a.test", "org_member")
    admin = sign_in(make_client(), "admin@a.test")
    token = _create_link(admin, org.id, worker.user.id)

    response = make_client().post(
        f"/api/v1/auth/password-resets/{token}", json={"password": "short"}
    )

    assert response.status_code == 422
