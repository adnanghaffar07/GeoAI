# ruff: noqa: E501
"""Team lead plan, Phase 2: encrypted files and bring your own storage."""

import uuid
from typing import Any, ClassVar

import pytest
from cryptography.exceptions import InvalidTag
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.analysis_fixtures import Setup

from app import storage
from app.models import AuditEvent, Image, OrganizationStorage


def _org(client: TestClient) -> str:
    return client.get("/api/v1/auth/me").json()["memberships"][0]["organization_id"]


def test_photos_are_encrypted_on_disk_and_shown_decrypted(s: Setup, db: Session) -> None:
    image_id = s.upload(s.admin)
    image = db.get(Image, uuid.UUID(image_id))
    assert image is not None
    on_disk = storage.path_for(image.storage_key).read_bytes()
    assert on_disk.startswith(storage.MAGIC)  # nobody can open the file without the key
    shown = s.admin.get(f"/api/v1/images/{image_id}/file")
    assert shown.status_code == 200 and shown.content[:2] == b"\xff\xd8"  # a real JPEG again
    assert s.admin.get(f"/api/v1/images/{image_id}/preview").status_code == 200


def test_files_saved_before_encryption_still_open() -> None:
    key = f"org/{uuid.uuid4()}/legacy/old.txt"
    storage.path_for(key).parent.mkdir(parents=True, exist_ok=True)
    storage.path_for(key).write_bytes(b"plain old file")
    assert storage.read_bytes(key) == b"plain old file"
    assert storage.decrypt(key, storage.encrypt(key, b"secret")) == b"secret"
    with pytest.raises(InvalidTag):  # an encrypted file cannot be moved to another key
        storage.decrypt(key + "x", storage.encrypt(key, b"secret"))


class FakeS3:
    """Stands in for the organization's own storage."""

    files: ClassVar[dict[str, bytes]] = {}

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.bucket, self.region, self.access_key, self.prefix = (
            "city-photos",
            "us-east-1",
            "AKEY",
            "",
        )

    def put(self, key: str, data: bytes) -> None:
        self.files[key] = data

    def get(self, key: str) -> bytes | None:
        return self.files.get(key)

    def exists(self, key: str) -> bool:
        return key in self.files

    def delete(self, key: str) -> None:
        self.files.pop(key, None)


def test_bring_your_own_storage(s: Setup, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    org = _org(s.admin)
    url = f"/api/v1/organizations/{org}/data-storage"
    shown = s.admin.get(url).json()
    assert shown["kind"] == "app" and shown["can_edit"] is True and "AES-256" in shown["encryption"]
    member_view = s.ann_client.get(url)
    assert (
        member_view.status_code == 200 and member_view.json()["can_edit"] is False
    )  # everyone sees where
    body = {"kind": "s3", "endpoint": "https://s3.example.com", "bucket": "city-photos", "access_key_id": "AKEY",
            "secret_key": "very-secret", "location_note": "City IT, own server"}  # fmt: skip
    assert s.ann_client.put(url, json=body).status_code == 403  # only admins change it

    def refuse(_backend: Any) -> None:
        raise storage.StorageUnavailableError("did not answer")

    monkeypatch.setattr(storage, "check_backend", refuse)
    failed = s.admin.put(url, json=body)
    assert failed.status_code == 422 and "did not answer" in failed.text
    assert db.get(OrganizationStorage, uuid.UUID(org)) is None  # nothing saved

    FakeS3.files = {}
    monkeypatch.setattr(storage, "check_backend", lambda _backend: None)
    monkeypatch.setattr(storage, "S3Backend", FakeS3)
    saved = s.admin.put(url, json=body)
    assert saved.status_code == 200, saved.text
    out = saved.json()
    assert out["kind"] == "s3" and out["has_secret"] is True and "secret_key" not in out
    assert "very-secret" not in saved.text
    row = db.get(OrganizationStorage, uuid.UUID(org))
    assert row is not None and row.secret_encrypted and b"very-secret" not in row.secret_encrypted
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "storage.changed")) is not None

    image_id = s.upload(s.admin)  # a new photo goes to the organization's own storage, encrypted
    image = db.get(Image, uuid.UUID(image_id))
    assert image is not None and FakeS3.files[image.storage_key].startswith(storage.MAGIC)
    assert not storage.path_for(image.storage_key).exists()  # no copy kept by the app
    assert s.admin.get(f"/api/v1/images/{image_id}/file").content[:2] == b"\xff\xd8"

    back = s.admin.put(url, json={"kind": "app"})
    assert back.status_code == 200 and back.json()["kind"] == "app"
    storage.forget_settings()


def test_s3_paths_and_signature_shape() -> None:
    backend = storage.S3Backend(
        "https://s3.example.com/", "photos", "", "AKEY", "SECRET", "geoinfra"
    )
    assert backend._url("org/1/a b.jpg") == "https://s3.example.com/photos/geoinfra/org/1/a%20b.jpg"
    assert backend.region == "us-east-1"
