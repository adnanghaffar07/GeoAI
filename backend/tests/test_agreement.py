"""Team lead plan, Phase 1: the terms must be accepted after sign-in (tl-phase1-design.md, 1)."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.agreement import AGREEMENT_VERSION
from app.models import AuditEvent
from tests.factories import DEFAULT_PASSWORD, make_org

ME, AGREE, LOGIN = "/api/v1/auth/me", "/api/v1/auth/agreement", "/api/v1/auth/login"


def _login(client: TestClient) -> dict:
    answer = client.post(LOGIN, json={"email": "admin@a.test", "password": DEFAULT_PASSWORD})
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_nothing_opens_before_the_terms_are_accepted(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    make_org(db)
    client = make_client()
    assert _login(client)["agreement_required"] is True
    me = client.get(ME).json()
    assert me["agreement_required"] is True and me["agreement_version"] == AGREEMENT_VERSION
    org = me["memberships"][0]["organization_id"]
    refused = client.get(f"/api/v1/organizations/{org}/projects")
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "agreement_required"

    assert client.post(AGREE, json={"version": "old", "remember": True}).status_code == 409
    accepted = client.post(AGREE, json={"version": AGREEMENT_VERSION, "remember": False})
    assert accepted.status_code == 200 and accepted.json()["agreement_required"] is False
    assert client.get(f"/api/v1/organizations/{org}/projects").status_code == 200
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "agreement.accepted"))
    assert event is not None and event.details == {"version": AGREEMENT_VERSION, "remember": False}

    # Not remembered: asked again at the next sign-in
    again = make_client()
    assert _login(again)["agreement_required"] is True
    assert again.post("/api/v1/auth/logout").status_code == 204  # signing out is always possible


def test_remember_my_choice_until_the_terms_change(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    make_org(db)
    first = make_client()
    _login(first)
    first.post(AGREE, json={"version": AGREEMENT_VERSION, "remember": True})
    second = make_client()
    assert _login(second)["agreement_required"] is False
    assert second.get(ME).json()["agreement_required"] is False
