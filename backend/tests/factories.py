"""Helpers that create test organizations and people."""

from dataclasses import dataclass

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.cli import create_organization
from app.core.security import hash_password
from app.models import Organization, OrganizationMembership, User

DEFAULT_PASSWORD = "correct-horse-battery"


@dataclass
class Person:
    user: User
    email: str
    password: str


def make_org(db: Session, name: str = "City A", admin_email: str = "admin@a.test") -> Organization:
    return create_organization(
        db,
        name=name,
        admin_email=admin_email,
        admin_name="Admin",
        admin_password=DEFAULT_PASSWORD,
    )


def add_member(db: Session, org: Organization, email: str, org_role: str) -> Person:
    user = User(
        email=email, full_name=email.split("@")[0], password_hash=hash_password(DEFAULT_PASSWORD)
    )
    db.add(user)
    db.flush()
    db.add(OrganizationMembership(organization_id=org.id, user_id=user.id, org_role=org_role))
    db.commit()
    return Person(user=user, email=email, password=DEFAULT_PASSWORD)


def sign_in(client: TestClient, email: str, password: str = DEFAULT_PASSWORD) -> TestClient:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return client


def org_id_of(client: TestClient) -> str:
    """The organization of the signed-in person (first membership)."""
    org_id: str = client.get("/api/v1/auth/me").json()["memberships"][0]["organization_id"]
    return org_id


def user_id_of(client: TestClient) -> str:
    user_id: str = client.get("/api/v1/auth/me").json()["user"]["id"]
    return user_id


def create_project(
    client: TestClient,
    *,
    name: str = "Main Street survey",
    reviewer_ids: list[str] | None = None,
    area: dict[str, object] | None = None,
) -> dict[str, object]:
    """Create a project through the API as the signed-in person (who becomes its manager)."""
    from tests.photos import AREA

    response = client.post(
        f"/api/v1/organizations/{org_id_of(client)}/projects",
        json={
            "name": name,
            "boundary": area or AREA,
            "finding_type_keys": ["pothole", "surface_cracking"],
            "reviewer_user_ids": reviewer_ids or [user_id_of(client)],
        },
    )
    assert response.status_code == 201, response.text
    project: dict[str, object] = response.json()
    return project


def add_to_project(client: TestClient, project_id: object, user_id: object, role: str) -> None:
    response = client.post(
        f"/api/v1/projects/{project_id}/members", json={"user_id": str(user_id), "role": role}
    )
    assert response.status_code == 201, response.text
