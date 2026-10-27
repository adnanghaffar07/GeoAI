"""Health endpoint tests (no database needed)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.api import health
from app.core import database, queue


def test_liveness_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


def test_readiness_ok_when_dependencies_are_up(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, "check_database", lambda: True)
    monkeypatch.setattr(health, "check_queue", lambda: True)

    response = client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "queue": "ok"}}


def test_readiness_reports_unreachable_dependencies(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, "check_database", lambda: False)
    monkeypatch.setattr(health, "check_queue", lambda: False)

    response = client.get("/api/health/ready")

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "service_unavailable"
    assert error["details"] == {"checks": {"database": "unavailable", "queue": "unavailable"}}
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_check_database_returns_false_when_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    unreachable = create_engine(
        "postgresql+psycopg://x:x@127.0.0.1:1/x", connect_args={"connect_timeout": 1}
    )
    monkeypatch.setattr(database, "get_engine", lambda: unreachable)

    assert database.check_database() is False


def test_check_queue_returns_false_when_unreachable() -> None:
    # conftest points REDIS_URL at a closed port.
    assert queue.check_queue() is False
