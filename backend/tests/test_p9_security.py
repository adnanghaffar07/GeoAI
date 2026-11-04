# ruff: noqa: E501
"""P9.2 security (p9-system-testing-plan.md).

- Every API route needs sign-in, except a short list of public ones. The list of routes is read from
  the app itself, so a new route without protection makes this test fail.
- Another organization's IDs never reveal anything (AC-01, AC-02), now also for road risk, alerts,
  the assistant and road inspections.
- Security headers on every answer; the session cookie cannot be read by scripts.
- No private keys or access tokens in the code.
"""

import re
import uuid
from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import create_app
from tests.analysis_fixtures import Setup
from tests.factories import DEFAULT_PASSWORD, make_org, sign_in
from tests.test_road_risk import _url, seed

PUBLIC = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),
    ("GET", "/api/v1/auth/invitations/{token}"),
    ("POST", "/api/v1/auth/invitations/{token}/accept"),
    ("GET", "/api/v1/auth/password-resets/{token}"),
    ("POST", "/api/v1/auth/password-resets/{token}"),
    ("POST", "/api/v1/organization-requests"),
}


def _fill(path: str) -> str:
    return re.sub(
        r"\{(\w+)\}", lambda m: "sometoken" if m.group(1) == "token" else str(uuid.uuid4()), path
    )


def test_every_route_needs_sign_in(database_ready: None) -> None:
    app = create_app()
    client = TestClient(app)
    checked = 0
    # The app's own API description lists every route and method (whatever way routers are kept).
    for path, methods in app.openapi()["paths"].items():
        if not path.startswith("/api/v1/"):
            continue
        for method in methods:
            method = method.upper()
            if method in {"HEAD", "OPTIONS"} or (method, path) in PUBLIC:
                continue
            status = client.request(method, _fill(path), json={}).status_code
            assert status == 401, f"{method} {path} answered {status} without sign-in"
            checked += 1
    assert checked > 60  # sanity: the routes were really found


def _body(url: str, s: Setup) -> dict[str, object]:
    """A valid body, so the answer is about permission, not about a malformed request."""
    if url.endswith("/assistant"):
        return {"question": "Which roads first?"}
    if url.endswith("/reopen"):
        return {
            "reason": "check",
            "owner_user_id": str(s.ann.user.id),
            "planned_date": "2026-11-07",
        }
    if "/inspections/" in url and not url.endswith("/inspections"):
        return {"status": "inspected"}
    if url.endswith("/inspections"):
        return {"owner_user_id": str(s.ann.user.id), "planned_date": "2026-11-07"}
    return {"enabled": True}


def test_another_organization_sees_nothing(
    s: Setup, db: Session, make_client: Callable[[], TestClient]
) -> None:
    data = seed(db, s.project_id)
    s.admin.put(_url(s, "forecast-settings"), json={"assistant_enabled": True})
    road = data["sections"]["a"]
    planned = s.admin.post(
        _url(s, f"road-sections/{road.id}/inspections"),
        json={"owner_user_id": str(s.ann.user.id), "planned_date": "2026-11-06"},
    ).json()
    alert = data["alerts"][0]

    make_org(db, name="City B", admin_email="admin@b.test")
    other = sign_in(make_client(), "admin@b.test")
    p = f"/api/v1/projects/{s.project_id}"
    for method, url in [
        ("GET", p),
        ("GET", f"{p}/forecast-settings"),
        ("PUT", f"{p}/forecast-settings"),
        ("GET", f"{p}/risk"),
        ("GET", f"{p}/risk/map"),
        ("GET", f"{p}/risk/export?format=csv"),
        ("GET", f"{p}/weather"),
        ("GET", f"{p}/alerts"),
        ("GET", f"{p}/road-sections/{road.id}/risk"),
        ("GET", f"{p}/road-sections/{road.id}/inspections"),
        ("POST", f"{p}/road-sections/{road.id}/inspections"),
        ("POST", f"{p}/assistant"),
        ("POST", f"{p}/risk-runs"),
        ("GET", f"/api/v1/notifications/{alert.id}"),
        ("POST", f"/api/v1/notifications/{alert.id}/read"),
        ("PATCH", f"/api/v1/inspections/{planned['id']}"),
        ("POST", f"/api/v1/inspections/{planned['id']}/reopen"),
    ]:
        status = other.request(method, url, json=_body(url, s)).status_code
        assert status == 404, f"{method} {url} answered {status} to another organization"
    assert other.get("/api/v1/notifications").json()["items"] == []


def test_security_headers_and_cookie(client: TestClient, db: Session) -> None:
    answer = client.get("/api/health")
    for name, value in {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Cache-Control": "no-store",
    }.items():
        assert answer.headers.get(name) == value, name
    refused = client.get("/api/v1/auth/me")
    assert refused.status_code == 401 and refused.headers.get("X-Frame-Options") == "DENY"

    make_org(db)
    login = client.post(
        "/api/v1/auth/login", json={"email": "admin@a.test", "password": DEFAULT_PASSWORD}
    )
    assert login.status_code == 200, login.text
    cookie = login.headers.get("set-cookie", "").lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


SECRET = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{32,}"
)
SKIP_DIRS = {".venv", "node_modules", "data", "models", "__pycache__", ".git", "runs"}


def test_no_secrets_in_the_code() -> None:
    roots = [Path(__file__).resolve().parents[1], Path("/ml")]
    found = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if any(part in SKIP_DIRS for part in path.parts) or not path.is_file():
                continue
            if path.suffix not in {
                ".py",
                ".ts",
                ".tsx",
                ".yml",
                ".yaml",
                ".json",
                ".toml",
                ".md",
                ".ini",
                ".cfg",
                ".txt",
            }:
                continue
            if path.stat().st_size > 1_000_000:
                continue
            if SECRET.search(path.read_text(encoding="utf-8", errors="ignore")):
                found.append(str(path))
    assert found == []
