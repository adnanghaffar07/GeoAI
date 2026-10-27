"""Tests for the standard error format and request IDs."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import NotFoundError
from app.main import create_app


def _client_with_test_routes() -> TestClient:
    app: FastAPI = create_app()

    @app.get("/test/not-found")
    def raise_not_found() -> None:
        raise NotFoundError("Project not found.")

    @app.get("/test/crash")
    def crash() -> None:
        raise RuntimeError("secret internal detail")

    @app.get("/test/validated")
    def validated(limit: int) -> dict[str, int]:
        return {"limit": limit}

    return TestClient(app, raise_server_exceptions=False)


def test_app_error_uses_standard_format() -> None:
    response = _client_with_test_routes().get("/test/not-found")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["message"] == "Project not found."
    assert error["request_id"]


def test_unexpected_error_hides_internal_details() -> None:
    response = _client_with_test_routes().get("/test/crash")

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert "secret internal detail" not in response.text


def test_validation_error_lists_fields() -> None:
    response = _client_with_test_routes().get("/test/validated", params={"limit": "abc"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"]["fields"][0]["field"] == "query.limit"


def test_unknown_route_returns_standard_404(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_valid_incoming_request_id_is_kept(client: TestClient) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "abc12345-test"})

    assert response.headers["X-Request-ID"] == "abc12345-test"


def test_unsafe_incoming_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "bad id\nwith newline"})

    assert response.headers["X-Request-ID"] != "bad id\nwith newline"
    assert len(response.headers["X-Request-ID"]) == 32
