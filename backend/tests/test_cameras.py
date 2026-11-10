"""Team lead items 8 and 10: IDOT cameras in the project area; a snapshot becomes a photo."""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.services import cameras
from tests.analysis_fixtures import Setup
from tests.photos import make_photo

IDOT = "https://cctv.travelmidwest.com/snapshots"


def _attributes(object_id: int, lat: float, lon: float, url: str) -> dict[str, Any]:
    return {
        "attributes": {
            "OBJECTID": object_id,
            "CameraLocation": "Mill / Diehl",
            "CameraDirection": "N",
            "y": lat,
            "x": lon,
            "SnapShot": url,
            "ImgPath": "https://travelmidwest.com/showCamera?id=1",
            "AgeInMinutes": "3",
            "TooOld": "false",
        }
    }


@pytest.fixture
def idot(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    fetched: list[str] = []
    rows = [
        _attributes(1, 37.78, -122.42, f"{IDOT}/inside.jpg"),
        _attributes(2, 40.71, -74.0, f"{IDOT}/outside.jpg"),  # not in the project area
        _attributes(3, 37.78, -122.42, "https://example.com/elsewhere.jpg"),  # not IDOT's server
    ]

    def fake_json(params: dict[str, Any]) -> dict[str, Any]:
        where = params["where"]
        if where.startswith("OBJECTID="):
            wanted = int(where.split("=")[1])
            return {"features": [r for r in rows if r["attributes"]["OBJECTID"] == wanted]}
        return {"features": rows}

    def fake_image(url: str) -> bytes:
        fetched.append(url)
        return make_photo(gps=None, taken=None, seed=7)

    cameras._cache.clear()
    monkeypatch.setattr(cameras, "_get_json", fake_json)
    monkeypatch.setattr(cameras, "_get_image", fake_image)
    return fetched


def test_cameras_in_the_area_and_a_snapshot_becomes_a_photo(
    s: Setup, db: Session, idot: list[str]
) -> None:
    url = f"/api/v1/projects/{s.project_id}/cameras"
    listed = s.viewer.get(url).json()
    assert [c["id"] for c in listed["cameras"]] == [1]
    assert listed["licence"] == "CC BY-SA 2.0" and "Illinois Department" in listed["source"]

    assert s.viewer.post(f"{url}/1/snapshot").status_code == 403  # viewers cannot add photos
    made = s.admin.post(f"{url}/1/snapshot")
    assert made.status_code == 201, made.text
    photo = made.json()["image"]
    assert photo["original_filename"].startswith("IDOT-camera-Mill---Diehl-N-")
    assert photo["location"] == {"latitude": 37.78, "longitude": -122.42}
    assert idot == [f"{IDOT}/inside.jpg"]  # the address always comes from IDOT's list
    photos = s.admin.get(f"/api/v1/projects/{s.project_id}/images").json()["items"]
    assert [p["id"] for p in photos] == [photo["id"]]  # same as an uploaded photo
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "image.camera_snapshot"))
    assert event is not None and event.details["licence"] == "CC BY-SA 2.0"

    assert s.admin.post(f"{url}/1/snapshot").status_code == 200  # same picture again: kept once
    assert s.admin.post(f"{url}/2/snapshot").status_code == 404  # outside the project area
    assert s.admin.post(f"{url}/3/snapshot").status_code == 404  # not on IDOT's server
