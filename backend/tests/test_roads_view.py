"""Team lead plan, item 11: roads-only view, for the whole project or a chosen box."""

from sqlalchemy.orm import Session

from tests.analysis_fixtures import Setup
from tests.test_road_risk import _url, seed


def test_roads_with_names_details_and_colour_levels(s: Setup, db: Session) -> None:
    data = seed(db, s.project_id)
    a = data["sections"]["a"]
    a.speed_limit_mph, a.details_filled = 30, True
    db.commit()
    body = s.viewer.get(_url(s, "roads.geojson")).json()
    assert len(body["features"]) == 3 and body["box"] is None
    road = next(f["properties"] for f in body["features"] if f["properties"]["name"] == "Road A")
    assert road["level"] == "high" and road["speed_limit_mph"] == 30
    assert {"climate_level", "traffic_level", "roughness_level"} <= road.keys()

    # only the roads inside the chosen box (section a is at -87.700, b at -87.690, c at -87.680)
    boxed = s.viewer.get(
        _url(s, "roads.geojson"), params={"box": "-87.705,41.79,-87.695,41.81"}
    ).json()
    assert [f["properties"]["name"] for f in boxed["features"]] == ["Road A"]
    assert s.viewer.get(_url(s, "roads.geojson"), params={"box": "1,2,3"}).status_code == 422
    assert s.viewer.get(_url(s, "roads.geojson"), params={"box": "5,0,1,1"}).status_code == 422
