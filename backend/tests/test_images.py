"""Photo upload and access.

Covers AC-08 (files only through the app), AC-13 (bad files get a reason), AC-14 (no
duplicates), AC-15 (GPS read, missing GPS flagged, never invented), AC-16 (quality
flags), AC-17 (location source shown).
"""

import hashlib
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Image
from tests.factories import add_member, add_to_project, create_project, make_org, sign_in
from tests.photos import INSIDE, OUTSIDE, make_photo


def _setup(db: Session, make_client: Callable[[], TestClient]) -> tuple[TestClient, str]:
    make_org(db)
    admin = sign_in(make_client(), "admin@a.test")
    project = create_project(admin)
    return admin, str(project["id"])


def _upload(client: TestClient, project_id: str, data: bytes, name: str = "photo.jpg", **form: str):  # type: ignore[no-untyped-def]
    return client.post(
        f"/api/v1/projects/{project_id}/images",
        files={"file": (name, data, "image/jpeg")},
        data=form,
    )


def test_photo_with_gps_inside_area(db: Session, make_client: Callable[[], TestClient]) -> None:
    admin, project_id = _setup(db, make_client)

    response = _upload(admin, project_id, make_photo(gps=INSIDE, offset="+00:00"))

    assert response.status_code == 201
    image = response.json()["image"]
    assert response.json()["duplicate"] is False
    assert image["location"]["latitude"] == pytest.approx(INSIDE[0], abs=1e-4)
    assert image["location"]["longitude"] == pytest.approx(INSIDE[1], abs=1e-4)
    assert image["location_source"] == "photo_gps"
    assert image["location_quality"] == "approximate"
    assert image["captured_at"].startswith("2026-10-01T10:00:00")
    assert image["quality_flags"] == []
    assert image["width_px"] == 400 and image["height_px"] == 300


def test_same_photo_twice_is_not_duplicated(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    """AC-14."""
    admin, project_id = _setup(db, make_client)
    data = make_photo(gps=INSIDE)

    first = _upload(admin, project_id, data)
    second = _upload(admin, project_id, data, name="renamed.jpg")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["image"]["id"] == first.json()["image"]["id"]
    assert db.scalar(select(func.count()).select_from(Image)) == 1


def test_photo_without_gps_is_flagged_and_gets_no_location(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    """AC-15 and AC-17: no location is invented; a picked point is marked 'manual'."""
    admin, project_id = _setup(db, make_client)

    image = _upload(admin, project_id, make_photo(gps=None)).json()["image"]

    assert image["location"] is None
    assert image["location_source"] == "none"
    assert image["location_quality"] == "missing"
    assert "missing_gps" in image["quality_flags"]
    listed = admin.get(f"/api/v1/projects/{project_id}/images?missing_location=true").json()
    assert listed["total"] == 1

    picked = admin.patch(
        f"/api/v1/images/{image['id']}/location",
        json={"latitude": INSIDE[0], "longitude": INSIDE[1]},
    )
    assert picked.status_code == 200
    assert picked.json()["location_source"] == "manual"
    assert "missing_gps" not in picked.json()["quality_flags"]

    again = admin.patch(
        f"/api/v1/images/{image['id']}/location", json={"latitude": 1, "longitude": 1}
    )
    assert again.status_code == 409  # the original location is never overwritten


def test_device_location_is_used_when_the_photo_has_none(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    admin, project_id = _setup(db, make_client)

    image = _upload(
        admin,
        project_id,
        make_photo(gps=None),
        device_latitude=str(INSIDE[0]),
        device_longitude=str(INSIDE[1]),
    ).json()["image"]

    assert image["location_source"] == "device_gps"
    assert "missing_gps" not in image["quality_flags"]


def test_photo_gps_wins_over_device_location(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    admin, project_id = _setup(db, make_client)

    image = _upload(
        admin, project_id, make_photo(gps=INSIDE), device_latitude="10", device_longitude="10"
    ).json()["image"]

    assert image["location_source"] == "photo_gps"


def test_photo_outside_the_survey_area_is_flagged(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    admin, project_id = _setup(db, make_client)

    image = _upload(admin, project_id, make_photo(gps=OUTSIDE)).json()["image"]

    assert "outside_project_area" in image["quality_flags"]


@pytest.mark.parametrize(("kind", "flag"), [("blurry", "blurry"), ("dark", "too_dark")])
def test_quality_problems_are_flagged(
    db: Session, make_client: Callable[[], TestClient], kind: str, flag: str
) -> None:
    """AC-16."""
    admin, project_id = _setup(db, make_client)

    image = _upload(admin, project_id, make_photo(gps=INSIDE, kind=kind)).json()["image"]

    assert flag in image["quality_flags"]


@pytest.mark.parametrize(
    ("data", "status", "code"),
    [
        (b"hello, I am a text file", 415, "unsupported_media_type"),
        (b"\xff\xd8\xff\xe0 broken jpeg", 415, "unsupported_media_type"),
        (b"", 415, "unsupported_media_type"),
    ],
)
def test_bad_files_get_a_clear_reason(
    db: Session, make_client: Callable[[], TestClient], data: bytes, status: int, code: str
) -> None:
    """AC-13."""
    admin, project_id = _setup(db, make_client)

    response = _upload(admin, project_id, data, name="notes.txt")

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["message"]
    assert db.scalar(select(func.count()).select_from(Image)) == 0


def test_too_large_file_is_refused(
    db: Session, make_client: Callable[[], TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    admin, project_id = _setup(db, make_client)
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)

    response = _upload(admin, project_id, make_photo(size=(1600, 1200)))

    assert response.status_code == 413
    assert "larger than 1 MB" in response.json()["error"]["message"]


def test_original_is_returned_unchanged_and_preview_is_small(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    admin, project_id = _setup(db, make_client)
    data = make_photo(gps=INSIDE, size=(2000, 1500))
    image_id = _upload(admin, project_id, data).json()["image"]["id"]

    original = admin.get(f"/api/v1/images/{image_id}/file")
    preview = admin.get(f"/api/v1/images/{image_id}/preview")

    assert original.status_code == 200
    assert hashlib.sha256(original.content).hexdigest() == hashlib.sha256(data).hexdigest()
    assert original.headers["content-type"] == "image/jpeg"
    assert original.headers["cache-control"].startswith("private")
    assert preview.status_code == 200
    assert len(preview.content) < len(data)


def test_photo_files_need_a_signed_in_person_with_access(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    """AC-08: there is no public address for a photo."""
    admin, project_id = _setup(db, make_client)
    image_id = _upload(admin, project_id, make_photo(gps=INSIDE)).json()["image"]["id"]

    anonymous = make_client()

    assert anonymous.get(f"/api/v1/images/{image_id}/file").status_code == 401
    assert anonymous.get(f"/api/v1/images/{image_id}/preview").status_code == 401


def test_collectors_see_and_open_only_their_own_photos(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    """Permission condition 'own uploads' for field collectors."""
    org = make_org(db)
    ann = add_member(db, org, "ann@a.test", "org_member")
    bob = add_member(db, org, "bob@a.test", "org_member")
    admin = sign_in(make_client(), "admin@a.test")
    project_id = str(create_project(admin)["id"])
    for person in (ann, bob):
        add_to_project(admin, project_id, person.user.id, "field_collector")
    ann_client = sign_in(make_client(), ann.email)
    bob_client = sign_in(make_client(), bob.email)
    ann_image = _upload(ann_client, project_id, make_photo(seed=1)).json()["image"]["id"]
    _upload(bob_client, project_id, make_photo(seed=2))

    listed = ann_client.get(f"/api/v1/projects/{project_id}/images").json()

    assert listed["total"] == 1 and listed["items"][0]["id"] == ann_image
    assert ann_client.get(f"/api/v1/images/{ann_image}/file").status_code == 200
    assert bob_client.get(f"/api/v1/images/{ann_image}/file").status_code == 403
    assert bob_client.get(f"/api/v1/images/{ann_image}").status_code == 403
    assert admin.get(f"/api/v1/projects/{project_id}/images").json()["total"] == 2


def test_viewers_cannot_open_photos_until_findings_are_verified(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    """Decision Q4: viewers only see photos of verified findings (none exist yet)."""
    org = make_org(db)
    viewer = add_member(db, org, "viewer@a.test", "org_member")
    admin = sign_in(make_client(), "admin@a.test")
    project_id = str(create_project(admin)["id"])
    add_to_project(admin, project_id, viewer.user.id, "viewer")
    image_id = _upload(admin, project_id, make_photo()).json()["image"]["id"]

    viewer_client = sign_in(make_client(), viewer.email)

    assert viewer_client.get(f"/api/v1/images/{image_id}/file").status_code == 403


def test_withdrawn_photos_are_kept_but_hidden(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    """Decision Q6: withdraw marks the photo; nothing is deleted."""
    org = make_org(db)
    ann = add_member(db, org, "ann@a.test", "org_member")
    bob = add_member(db, org, "bob@a.test", "org_member")
    admin = sign_in(make_client(), "admin@a.test")
    project_id = str(create_project(admin)["id"])
    for person in (ann, bob):
        add_to_project(admin, project_id, person.user.id, "field_collector")
    ann_client = sign_in(make_client(), ann.email)
    image_id = _upload(ann_client, project_id, make_photo()).json()["image"]["id"]

    assert (
        sign_in(make_client(), bob.email).post(f"/api/v1/images/{image_id}/withdraw").status_code
        == 403
    )
    response = ann_client.post(f"/api/v1/images/{image_id}/withdraw")

    assert response.status_code == 200 and response.json()["status"] == "withdrawn"
    assert admin.get(f"/api/v1/projects/{project_id}/images").json()["total"] == 0
    assert (
        admin.get(f"/api/v1/projects/{project_id}/images?include_withdrawn=true").json()["total"]
        == 1
    )
    assert admin.get(f"/api/v1/projects/{project_id}").json()["counts"]["images"] == 0
    assert db.scalar(select(func.count()).select_from(Image)) == 1


def test_project_counts(db: Session, make_client: Callable[[], TestClient]) -> None:
    admin, project_id = _setup(db, make_client)
    _upload(admin, project_id, make_photo(gps=INSIDE, offset="+00:00", seed=1))
    _upload(admin, project_id, make_photo(gps=None, seed=2))
    _upload(admin, project_id, make_photo(gps=INSIDE, kind="blurry", seed=3))

    counts = admin.get(f"/api/v1/projects/{project_id}").json()["counts"]

    assert counts == {
        "images": 3,
        "images_missing_location": 1,
        "images_with_quality_flags": 2,
        "images_analysed": 0,
        "images_waiting_for_ai": 3,  # none sent to the AI yet
        "findings_to_review": 0,
        "findings_needs_field_check": 0,
        "findings_verified": 0,
        "verified_location_unconfirmed": 0,
        "verified_by_type": {},
        "inspections_open": 0,
    }
