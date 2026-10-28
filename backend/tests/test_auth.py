"""Sign-in, sign-out, sessions, password storage, and the Origin check."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.models import AuditEvent, User, UserSession
from tests.factories import DEFAULT_PASSWORD, make_org, sign_in

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


def test_sign_in_sets_secure_cookie_and_returns_memberships(
    db: Session, client: TestClient
) -> None:
    org = make_org(db)

    response = client.post(LOGIN, json={"email": "ADMIN@a.test", "password": DEFAULT_PASSWORD})

    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    body = response.json()
    assert body["user"]["email"] == "admin@a.test"
    assert body["user"]["is_platform_admin"] is False
    membership = body["memberships"][0]
    assert membership["organization_id"] == str(org.id)
    assert membership["org_role"] == "org_admin"
    assert "org.members.invite" in membership["permissions"]
    assert client.get(ME).status_code == 200


def test_me_says_when_the_account_is_a_platform_admin(db: Session, client: TestClient) -> None:
    make_org(db)
    user = db.scalar(select(User).where(User.email == "admin@a.test"))
    assert user is not None
    user.is_platform_admin = True
    db.commit()

    client.post(LOGIN, json={"email": "admin@a.test", "password": DEFAULT_PASSWORD})

    assert client.get(ME).json()["user"]["is_platform_admin"] is True


def test_wrong_password_and_unknown_email_give_the_same_answer(
    db: Session, client: TestClient
) -> None:
    make_org(db)

    wrong_password = client.post(LOGIN, json={"email": "admin@a.test", "password": "nope"})
    unknown_email = client.post(LOGIN, json={"email": "nobody@a.test", "password": "nope"})

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["error"]["message"] == unknown_email.json()["error"]["message"]


def test_too_many_failures_lock_sign_in_even_with_correct_password(
    db: Session, client: TestClient
) -> None:
    make_org(db)
    for _ in range(5):
        assert (
            client.post(LOGIN, json={"email": "admin@a.test", "password": "bad"}).status_code == 401
        )

    response = client.post(LOGIN, json={"email": "admin@a.test", "password": DEFAULT_PASSWORD})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "too_many_requests"


def test_failed_sign_in_is_recorded(db: Session, client: TestClient) -> None:
    make_org(db)
    client.post(LOGIN, json={"email": "admin@a.test", "password": "bad"})

    events = db.scalars(select(AuditEvent).where(AuditEvent.action == "auth.sign_in_failed")).all()

    assert len(events) == 1
    assert events[0].details["email"] == "admin@a.test"


def test_sign_out_ends_the_session(db: Session, client: TestClient) -> None:
    make_org(db)
    sign_in(client, "admin@a.test")

    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get(ME).status_code == 401


def test_requests_without_session_are_refused(client: TestClient, db: Session) -> None:
    response = client.get(ME)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_deactivated_user_cannot_sign_in(db: Session, client: TestClient) -> None:
    make_org(db)
    user = db.scalar(select(User).where(User.email == "admin@a.test"))
    assert user is not None
    user.is_active = False
    db.commit()

    response = client.post(LOGIN, json={"email": "admin@a.test", "password": DEFAULT_PASSWORD})

    assert response.status_code == 401


def test_passwords_and_session_tokens_are_never_stored_readable(
    db: Session, client: TestClient
) -> None:
    """AC-07: only hashes are stored."""
    make_org(db)
    response = client.post(LOGIN, json={"email": "admin@a.test", "password": DEFAULT_PASSWORD})
    cookie_token = response.cookies.get("geoinfralens_session")
    assert cookie_token

    user = db.scalar(select(User).where(User.email == "admin@a.test"))
    session_row = db.scalar(select(UserSession))
    assert user is not None and session_row is not None
    assert user.password_hash is not None and user.password_hash.startswith("$argon2")
    assert DEFAULT_PASSWORD not in user.password_hash
    assert session_row.token_hash == hash_token(cookie_token)
    assert session_row.token_hash != cookie_token


def test_data_changing_request_from_another_website_is_refused(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    make_org(db)
    client = make_client()

    evil = client.post(
        LOGIN,
        json={"email": "admin@a.test", "password": DEFAULT_PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    cross_site = client.post(
        LOGIN,
        json={"email": "admin@a.test", "password": DEFAULT_PASSWORD},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    own_site = client.post(
        LOGIN,
        json={"email": "admin@a.test", "password": DEFAULT_PASSWORD},
        headers={"Origin": "http://testserver"},
    )

    assert evil.status_code == 403
    assert cross_site.status_code == 403
    assert own_site.status_code == 200


def test_reading_requests_are_not_blocked_by_origin(db: Session, client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": "https://elsewhere.example"})

    assert response.status_code == 200
