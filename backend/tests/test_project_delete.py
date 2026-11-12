"""Owner, 2026-11-12: only an organization admin can delete a project; it disappears for
everyone, its share links stop, and nothing is erased."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Project
from tests.analysis_fixtures import Setup


def test_only_an_admin_deletes_and_the_project_disappears(s: Setup, db: Session) -> None:
    url = f"/api/v1/projects/{s.project_id}"
    name = s.admin.get(url).json()["name"]
    image_id = s.upload(s.admin)
    link = s.admin.post(f"/api/v1/images/{image_id}/share-links", json={}).json()

    # field collectors (and everyone who is not an organization admin) cannot delete
    assert s.ann_client.request("DELETE", url, json={"confirm_name": name}).status_code == 403
    # the name must be typed exactly
    assert s.admin.request("DELETE", url, json={"confirm_name": "wrong"}).status_code == 422

    assert s.admin.request("DELETE", url, json={"confirm_name": name}).status_code == 204
    assert s.admin.get(url).status_code == 404  # gone for everyone
    assert s.ann_client.get(url).status_code == 404
    org = s.admin.get("/api/v1/auth/me").json()["memberships"][0]["organization_id"]
    listed = s.admin.get(f"/api/v1/organizations/{org}/projects").json()["items"]
    assert s.project_id not in [p["id"] for p in listed]
    assert s.admin.get(link["url"]).status_code == 404  # its share links stop working

    # nothing is erased, and the deletion is in the history
    row = db.scalar(select(Project).where(Project.name == name))
    assert row is not None and row.deleted_at is not None
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "project.deleted")) is not None
