"""Team lead plan, item 9: shareable photo links (managers only, 1-30 days, can be cancelled)."""

from collections.abc import Callable
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, ImageShareLink
from tests.analysis_fixtures import Setup


def test_a_manager_shares_a_photo_and_can_cancel_the_link(
    s: Setup, db: Session, make_client: Callable[[], TestClient]
) -> None:
    image_id = s.upload(s.admin)
    url = f"/api/v1/images/{image_id}/share-links"
    made = s.admin.post(url, json={"days": 7})
    assert made.status_code == 201, made.text
    link = made.json()
    assert link["state"] == "active" and link["url"].startswith("/api/v1/shared/")
    token = link["url"].rsplit("/", 1)[1]
    # only a fingerprint of the secret is stored
    assert db.scalar(select(ImageShareLink.token_hash)) != token

    stranger = make_client()  # not signed in
    shown = stranger.get(link["url"])
    assert shown.status_code == 200 and shown.headers["content-type"] == "image/jpeg"
    assert "no-store" in shown.headers["cache-control"]
    assert shown.headers["x-robots-tag"] == "noindex"
    assert s.admin.get(url).json()[0]["url"] is None  # the secret is shown once only

    assert s.admin.post(f"{url}/{link['id']}/revoke").json()["state"] == "cancelled"
    assert stranger.get(link["url"]).status_code == 404
    actions = set(db.scalars(select(AuditEvent.action)))
    assert {"image.shared", "image.share_revoked"} <= actions


def test_links_end_and_only_managers_make_them(
    s: Setup, db: Session, make_client: Callable[[], TestClient]
) -> None:
    image_id = s.upload(s.admin)
    url = f"/api/v1/images/{image_id}/share-links"
    assert s.ann_client.post(url, json={}).status_code == 403  # field collector
    assert s.viewer.post(url, json={}).status_code in {403, 404}
    assert s.admin.post(url, json={"days": 31}).status_code == 422
    link = s.admin.post(url, json={}).json()
    row = db.scalar(select(ImageShareLink))
    assert row is not None
    row.expires_at = row.created_at - timedelta(seconds=1)
    db.commit()
    assert make_client().get(link["url"]).status_code == 404
    assert make_client().get("/api/v1/shared/not-a-real-link").status_code == 404
