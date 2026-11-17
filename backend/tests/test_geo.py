"""Turning a searched road, address or area into a survey area."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.schemas.projects import GeoJsonArea
from app.services.projects import validate_area
from tests.factories import make_org, sign_in

URL = "/api/v1/geo/area-from-place"
# About 1 km of road running north (0.009 degrees of latitude).
ROAD = {"type": "LineString", "coordinates": [[-88.15, 41.77], [-88.15, 41.779]]}
CROSS_ROAD = {"type": "LineString", "coordinates": [[-88.156, 41.7745], [-88.144, 41.7745]]}


def _admin(db: Session, client: TestClient) -> TestClient:
    make_org(db)
    return sign_in(client, "admin@a.test")


def test_a_road_becomes_a_strip_of_the_chosen_width(db: Session, client: TestClient) -> None:
    admin = _admin(db, client)

    response = admin.post(URL, json={"shape": ROAD, "road_width_m": 30})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["area"]["type"] == "Polygon"
    # 1,000 m x 30 m plus two rounded ends (about 700 m2)
    assert 29_000 < body["area_square_meters"] < 32_500
    validate_area(db, GeoJsonArea.model_validate(body["area"]))  # saving a project accepts it


def test_a_wider_strip_covers_more(db: Session, client: TestClient) -> None:
    admin = _admin(db, client)

    narrow = admin.post(URL, json={"shape": ROAD, "road_width_m": 20}).json()
    wide = admin.post(URL, json={"shape": ROAD, "road_width_m": 60}).json()

    assert wide["area_square_meters"] > 2.5 * narrow["area_square_meters"]


def test_an_address_point_covers_the_block_around_it(db: Session, client: TestClient) -> None:
    admin = _admin(db, client)

    body = admin.post(URL, json={"shape": {"type": "Point", "coordinates": [-88.15, 41.77]}}).json()

    assert 65_000 < body["area_square_meters"] < 72_000  # circle of 150 m radius


def test_an_area_keeps_its_outline(db: Session, client: TestClient) -> None:
    admin = _admin(db, client)
    square = {
        "type": "Polygon",
        "coordinates": [
            [[-88.16, 41.77], [-88.15, 41.77], [-88.15, 41.78], [-88.16, 41.78], [-88.16, 41.77]]
        ],
    }

    body = admin.post(URL, json={"shape": square}).json()

    assert body["area"]["type"] == "Polygon"
    assert len(body["area"]["coordinates"][0]) == 5


def test_adding_a_crossing_road_joins_them_into_one_valid_shape(
    db: Session, client: TestClient
) -> None:
    admin = _admin(db, client)
    first = admin.post(URL, json={"shape": ROAD, "road_width_m": 30}).json()

    joined = admin.post(
        URL, json={"shape": CROSS_ROAD, "road_width_m": 30, "add_to": first["area"]}
    ).json()

    assert joined["area"]["type"] == "Polygon"  # the two strips overlap, so they merge
    alone = admin.post(URL, json={"shape": CROSS_ROAD, "road_width_m": 30}).json()
    total = first["area_square_meters"] + alone["area_square_meters"]
    assert first["area_square_meters"] < joined["area_square_meters"] < total
    validate_area(db, GeoJsonArea.model_validate(joined["area"]))


def test_separate_roads_become_one_area_with_several_parts(db: Session, client: TestClient) -> None:
    admin = _admin(db, client)
    first = admin.post(URL, json={"shape": ROAD}).json()
    far = {"type": "LineString", "coordinates": [[-88.10, 41.77], [-88.10, 41.775]]}

    joined = admin.post(URL, json={"shape": far, "add_to": first["area"]}).json()

    assert joined["area"]["type"] == "MultiPolygon"
    assert len(joined["area"]["coordinates"]) == 2


def test_needs_sign_in_and_checks_input(db: Session, client: TestClient) -> None:
    assert client.post(URL, json={"shape": ROAD}).status_code == 401
    admin = _admin(db, client)
    bad = {"type": "LineString", "coordinates": [[-200, 41.77], [-88.15, 41.779]]}
    assert admin.post(URL, json={"shape": bad}).status_code == 422
    assert admin.post(URL, json={"shape": ROAD, "road_width_m": 5}).status_code == 422


def test_a_road_with_two_carriageways_becomes_one_solid_strip(
    db: Session, client: TestClient
) -> None:
    """Route 59 case (2026-11-11): the gap between the two directions left a hole the map
    could not edit; the strip is now solid, so it always shows on the map."""
    admin = _admin(db, client)
    loop = {
        "type": "MultiLineString",
        "coordinates": [
            [[-88.15, 41.77], [-88.15, 41.779]],  # northbound
            [[-88.1492, 41.779], [-88.1492, 41.77]],  # southbound, about 65 m east
            [[-88.15, 41.77], [-88.1492, 41.77]],  # joined at both ends
            [[-88.15, 41.779], [-88.1492, 41.779]],
        ],
    }
    body = admin.post(URL, json={"shape": loop, "road_width_m": 20}).json()
    polygons = (
        [body["area"]["coordinates"]]
        if body["area"]["type"] == "Polygon"
        else body["area"]["coordinates"]
    )
    assert all(len(rings) == 1 for rings in polygons)  # no holes
    validate_area(db, GeoJsonArea.model_validate(body["area"]))


def test_the_whole_road_collects_every_piece_with_that_name(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import whole_road

    asked: list[str] = []

    def fake_overpass(query: str) -> dict[str, Any]:
        asked.append(query)
        if "out tags" in query:
            tags = {"name": "Illinois Route 59", "ref": "IL 59;US 30"}
            return {"elements": [{"type": "way", "id": 77, "tags": tags}]}
        if '"Nowhere Road"' in query:
            return {"elements": []}
        return {
            "elements": [
                {
                    "type": "way",
                    "id": 1,
                    "geometry": [{"lat": 41.77, "lon": -88.15}, {"lat": 41.775, "lon": -88.15}],
                },
                {
                    "type": "way",
                    "id": 1,  # the same piece twice counts once
                    "geometry": [{"lat": 41.77, "lon": -88.15}, {"lat": 41.775, "lon": -88.15}],
                },
                {
                    "type": "way",
                    "geometry": [{"lat": 41.775, "lon": -88.15}, {"lat": 41.779, "lon": -88.15}],
                },
                {
                    "type": "way",
                    "geometry": [{"lat": 41.78, "lon": -88.15}],
                },  # one point: not a line
            ]
        }

    monkeypatch.setattr(whole_road, "_overpass", fake_overpass)
    admin = _admin(db, client)
    body = {"name": 'Diehl "Road"', "latitude": 41.775, "longitude": -88.15}
    found = admin.post("/api/v1/geo/whole-road", json=body)
    assert found.status_code == 200, found.text
    road = found.json()
    assert road["pieces"] == 2 and road["shape"]["type"] == "MultiLineString"
    assert 0.9 < road["length_km"] < 1.1
    assert 'way(around:5000,41.775000,-88.150000)["highway"]["name"="Diehl \\"Road\\""]' in asked[0]

    strip = admin.post(URL, json={"shape": road["shape"], "road_width_m": 30})
    assert (
        strip.status_code == 200 and strip.json()["area"]["type"] == "Polygon"
    )  # pieces join into one strip

    by_ref = admin.post("/api/v1/geo/whole-road", json={**body, "name": "IL 59", "by_ref": True})
    assert by_ref.status_code == 200 and '["ref"="IL 59"]' in asked[-1]
    # The piece found is known: its own name and every route number are matched too.
    asked.clear()
    route = admin.post(
        "/api/v1/geo/whole-road", json={**body, "name": "Route 59", "osm_way_id": 77}
    )
    assert route.status_code == 200 and route.json()["pieces"] == 2
    assert "way(77);out tags;" in asked[0]
    for wanted in ('"Route 59"]', '"Illinois Route 59"]', '["ref"="IL 59"]', '["ref"="US 30"]'):
        assert wanted in asked[1]
    missing = admin.post("/api/v1/geo/whole-road", json={**body, "name": "Nowhere Road"})
    assert missing.status_code == 404
