"""Console messages: one line per request and per saved action, never secrets."""

import logging
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import DEFAULT_PASSWORD, make_org, sign_in


def _app_messages(caplog: pytest.LogCaptureFixture, level: int = logging.INFO) -> list[str]:
    """Messages from the app itself (the test's own web client logs its requests too)."""
    return [
        r.getMessage()
        for r in caplog.records
        if r.name.startswith(("geoinfralens", "app.")) and r.levelno >= level
    ]


def test_sign_in_prints_the_request_and_the_saved_action(
    db: Session, make_client: Callable[[], TestClient], caplog: pytest.LogCaptureFixture
) -> None:
    make_org(db)
    caplog.set_level(logging.INFO)

    sign_in(make_client(), "admin@a.test")

    messages = _app_messages(caplog)
    assert any(m.startswith("POST /api/v1/auth/login -> 200 (") for m in messages)
    assert any(m.startswith("Activity: auth.signed_in by user=") for m in messages)
    assert not any(DEFAULT_PASSWORD in m for m in messages)


def test_failed_sign_in_is_a_warning(
    db: Session, make_client: Callable[[], TestClient], caplog: pytest.LogCaptureFixture
) -> None:
    make_org(db)
    caplog.set_level(logging.INFO)

    make_client().post("/api/v1/auth/login", json={"email": "admin@a.test", "password": "wrong!"})

    warnings = _app_messages(caplog, logging.WARNING)
    assert any(m.startswith("Activity: auth.sign_in_failed") for m in warnings)
    assert any(m.startswith("POST /api/v1/auth/login -> 401") for m in _app_messages(caplog))


def test_secret_link_codes_are_never_printed(
    make_client: Callable[[], TestClient], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    make_client().get("/api/v1/auth/invitations/SECRET-CODE-123456")

    messages = " ".join(_app_messages(caplog))
    assert "SECRET-CODE-123456" not in messages
    assert "/api/v1/auth/invitations/***" in messages


def test_actions_that_were_not_saved_are_not_printed(
    db: Session, caplog: pytest.LogCaptureFixture
) -> None:
    from app.services.audit import record_event

    caplog.set_level(logging.INFO)
    record_event(db, action="project.created", organization_id=None, actor_user_id=None)
    db.rollback()
    db.commit()

    assert not any("project.created" in r.getMessage() for r in caplog.records)
