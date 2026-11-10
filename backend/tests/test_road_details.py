"""Team lead plan, item 12: road details (speed limit, lanes, surface) from OpenStreetMap."""

import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.services import road_details
from tests.analysis_fixtures import Setup
from tests.test_road_risk import _url, seed


@pytest.mark.parametrize(
    ("value", "mph"),
    [
        ("40 mph", 40),
        ("25", 25),
        ("50 km/h", 31),
        ("25 mph;35 mph", 35),
        ("signals", None),
        (None, None),
    ],
)
def test_speed_limits_are_read_in_mph(value: str | None, mph: int | None) -> None:
    assert road_details.parse_speed(value) == mph


def test_section_shows_its_road_details(s: Setup, db: Session, tmp_path: Path) -> None:
    data = seed(db, s.project_id)
    a, b = data["sections"]["a"], data["sections"]["b"]
    a.section_key = "123-0-0"  # OpenStreetMap way 123
    db.commit()
    tags = {
        "maxspeed": "35 mph",
        "lanes": "2;4",
        "surface": "asphalt",
        "oneway": "yes",
        "ref": "IL 59",
    }
    (tmp_path / "osm_roads.json").write_text(
        json.dumps({"elements": [{"type": "way", "id": 123, "tags": tags}]}), encoding="utf-8"
    )
    assert road_details.fill_missing(db, lambda _key: tmp_path) == {a.area_key: 1}
    assert road_details.fill_missing(db, lambda _key: tmp_path) == {}  # nothing left to fill

    road = s.reviewer.get(_url(s, f"road-sections/{a.id}/risk")).json()["road"]
    assert road == {
        "speed_limit_mph": 35,
        "lanes": 4,
        "surface": "Asphalt",
        "oneway": True,
        "road_ref": "IL 59",
        "source": "OpenStreetMap contributors",
    }
    other = s.reviewer.get(_url(s, f"road-sections/{b.id}/risk")).json()["road"]
    assert other["speed_limit_mph"] is None  # not on the map: shown as unknown, never guessed
