"""Team lead plan, item 5: analysed photos on the map, with their defects and boxes."""

from typing import Any

from tests.analysis_fixtures import Setup, two_candidates


def test_analysed_photos_with_location_are_on_the_map(
    s: Setup, worker: list[str], use_detector: Any
) -> None:
    use_detector(two_candidates)
    located = s.upload(s.admin, seed=1)
    s.upload(s.admin, seed=2, gps=False)  # no location: not on the map
    waiting = s.upload(s.admin, seed=3)  # not checked by the AI yet: not on the map
    s.start(s.admin, [located])
    url = f"/api/v1/projects/{s.project_id}/photos.geojson"
    data = s.admin.get(url).json()
    assert [f["id"] for f in data["features"]] == [located] and waiting not in str(data)
    photo = data["features"][0]["properties"]
    assert photo["width_px"] > 0 and photo["taken_at"]
    assert (
        photo["defect_count"] == len(photo["defects"]) == 2 and photo["worst"] == 2
    )  # two AI suggestions
    for defect in photo["defects"]:
        assert defect["review_status"] != "rejected" and (
            defect["bbox"] is None or len(defect["bbox"]) == 4
        )
    # viewers may see photos (permission matrix), but only verified problems, never AI suggestions
    seen = s.viewer.get(url).json()["features"]
    assert all(f["properties"]["defects"] == [] for f in seen)


def test_a_photo_located_by_hand_puts_its_findings_on_the_map(
    s: Setup, worker: list[str], use_detector: Any
) -> None:
    use_detector(two_candidates)
    photo = s.upload(s.admin, seed=4, gps=False)
    s.start(s.admin, [photo])
    findings = f"/api/v1/projects/{s.project_id}/findings.geojson"
    assert s.admin.get(findings).json()["features"] == []  # no location yet: not on the map

    point = {"latitude": 37.775, "longitude": -122.42}
    assert s.admin.patch(f"/api/v1/images/{photo}/location", json=point).status_code == 200
    shown = s.admin.get(findings).json()["features"]
    assert len(shown) == 2
    assert all(f["geometry"]["coordinates"] == [-122.42, 37.775] for f in shown)
    history = s.admin.get(f"/api/v1/findings/{shown[0]['id']}/history").json()
    assert any(e["action"] == "edit" and "corrected_location" in e["changes"] for e in history)
