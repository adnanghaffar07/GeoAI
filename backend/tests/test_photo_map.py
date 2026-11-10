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
