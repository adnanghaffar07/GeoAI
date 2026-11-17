"""Turning a searched road, address or area into a survey area."""

from typing import Any

import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import ServiceUnavailableError
from app.models import ForecastSection
from app.schemas.projects import GeoJsonArea
from app.services.projects import validate_area
from tests.factories import make_org, sign_in

URL = "/api/v1/geo/area-from-place"
# About 1 km of road running north (0.009 degrees of latitude).
ROAD = {"type": "LineString", "coordinates": [[-88.15, 41.77], [-88.15, 41.779]]}
CROSS_ROAD = {
    "type": "LineString",
    "coordinates": [[-88.156, 41.7745], [-88.144, 41.7745]],
}


def _admin(db: Session, client: TestClient) -> TestClient:
    make_org(db)
    return sign_in(client, "admin@a.test")


def test_a_road_becomes_a_strip_of_the_chosen_width(
    db: Session, client: TestClient
) -> None:
    admin = _admin(db, client)

    response = admin.post(URL, json={"shape": ROAD, "road_width_m": 30})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["area"]["type"] == "Polygon"
    # 1,000 m x 30 m plus two rounded ends (about 700 m2)
    assert 29_000 < body["area_square_meters"] < 32_500
    validate_area(
        db, GeoJsonArea.model_validate(body["area"])
    )  # saving a project accepts it


def test_a_wider_strip_covers_more(db: Session, client: TestClient) -> None:
    admin = _admin(db, client)

    narrow = admin.post(URL, json={"shape": ROAD, "road_width_m": 20}).json()
    wide = admin.post(URL, json={"shape": ROAD, "road_width_m": 60}).json()

    assert wide["area_square_meters"] > 2.5 * narrow["area_square_meters"]


def test_an_address_point_covers_the_block_around_it(
    db: Session, client: TestClient
) -> None:
    admin = _admin(db, client)

    body = admin.post(
        URL, json={"shape": {"type": "Point", "coordinates": [-88.15, 41.77]}}
    ).json()

    assert 65_000 < body["area_square_meters"] < 72_000  # circle of 150 m radius


def test_an_area_keeps_its_outline(db: Session, client: TestClient) -> None:
    admin = _admin(db, client)
    square = {
        "type": "Polygon",
        "coordinates": [
            [
                [-88.16, 41.77],
                [-88.15, 41.77],
                [-88.15, 41.78],
                [-88.16, 41.78],
                [-88.16, 41.77],
            ]
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


def test_separate_roads_become_one_area_with_several_parts(
    db: Session, client: TestClient
) -> None:
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


WHOLE_ROAD = "/api/v1/geo/whole-road"
PIECE_A = {
    "type": "way",
    "id": 1,
    "geometry": [{"lat": 41.77, "lon": -88.15}, {"lat": 41.775, "lon": -88.15}],
}
PIECE_B = {
    "type": "way",
    "id": 2,
    "geometry": [{"lat": 41.775, "lon": -88.15}, {"lat": 41.779, "lon": -88.15}],
}
SEARCH = {"name": 'Diehl "Road"', "latitude": 41.775, "longitude": -88.15}


def _fake_overpass(
    monkeypatch: pytest.MonkeyPatch, answer: Any, asked: list[str]
) -> None:
    from app.services import whole_road

    def fake(query: str, *_: object) -> dict[str, Any]:
        asked.append(query)
        if isinstance(answer, Exception):
            raise answer
        return answer(query) if callable(answer) else answer

    monkeypatch.setattr(whole_road, "_overpass", fake)


def test_the_whole_road_collects_every_piece_with_that_name(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def answer(query: str) -> dict[str, Any]:
        if "out tags" in query:
            tags = {"name": "Illinois Route 59", "ref": "IL 59;US 30"}
            return {"elements": [{"type": "way", "id": 77, "tags": tags}]}
        if '"Nowhere Road"' in query:
            return {"elements": []}
        return {
            "elements": [
                PIECE_A,
                PIECE_A,  # the same piece twice counts once
                {"type": "way", "geometry": PIECE_B["geometry"]},
                {
                    "type": "way",
                    "geometry": [{"lat": 41.78, "lon": -88.15}],
                },  # one point
            ]
        }

    asked: list[str] = []
    _fake_overpass(monkeypatch, answer, asked)
    admin = _admin(db, client)
    found = admin.post(WHOLE_ROAD, json={**SEARCH, "sources": ["overpass"]})
    assert found.status_code == 200, found.text
    road = found.json()
    assert road["pieces"] == 2 and road["shape"]["type"] == "MultiLineString"
    assert road["source"] == "overpass"
    assert 0.9 < road["length_km"] < 1.1
    # Tag first, then a box (south, west, north, east) about 10 km wide: no slow "around" search.
    assert 'way["highway"]["name"="Diehl \\"Road\\""](41.730' in asked[0]
    assert "around" not in asked[0] and "[timeout:20]" in asked[0]

    strip = admin.post(URL, json={"shape": road["shape"], "road_width_m": 30})
    assert strip.status_code == 200 and strip.json()["area"]["type"] == "Polygon"

    by_ref = admin.post(WHOLE_ROAD, json={**SEARCH, "name": "IL 59", "by_ref": True})
    assert by_ref.status_code == 200 and '["ref"="IL 59"]' in asked[-1]
    # The piece found is known: its own name and every route number are matched too.
    asked.clear()
    route = admin.post(
        WHOLE_ROAD, json={**SEARCH, "name": "Route 59", "osm_way_id": 77}
    )
    assert route.status_code == 200 and route.json()["pieces"] == 2
    assert "way(77);out tags;" in asked[0]
    for wanted in (
        '"Route 59"]',
        '"Illinois Route 59"]',
        '["ref"="IL 59"]',
        '["ref"="US 30"]',
    ):
        assert wanted in asked[1]
    missing = admin.post(
        WHOLE_ROAD, json={**SEARCH, "name": "Nowhere Road", "sources": ["overpass"]}
    )
    assert missing.status_code == 404


def test_the_search_can_use_the_map_view_or_the_town_limits(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []
    _fake_overpass(monkeypatch, {"elements": [PIECE_A]}, asked)
    admin = _admin(db, client)
    body = {**SEARCH, "name": "Washington Street", "sources": ["overpass"]}

    view = admin.post(
        WHOLE_ROAD, json={**body, "extent": "box", "box": [-88.2, 41.7, -88.1, 41.8]}
    )
    assert view.status_code == 200, view.text
    assert (
        '["name"="Washington Street"](41.700000,-88.200000,41.800000,-88.100000)'
        in asked[-1]
    )

    wide = admin.post(WHOLE_ROAD, json={**body, "radius_m": 20_000})
    assert wide.status_code == 200
    assert "(41.595" in asked[-1]  # 20 km each way

    town = admin.post(WHOLE_ROAD, json={**body, "extent": "town", "town": "Naperville"})
    assert town.status_code == 200, town.text
    assert (
        'is_in(41.775000,-88.150000)->.p;area.p["boundary"="administrative"]'
        in asked[-1]
    )
    assert '["name"="Naperville"]->.a;' in asked[-1]
    assert '["name"="Washington Street"](area.a);' in asked[-1]

    # Wrong requests are refused with a plain reason.
    assert admin.post(WHOLE_ROAD, json={**body, "extent": "town"}).status_code == 422
    assert admin.post(WHOLE_ROAD, json={**body, "extent": "box"}).status_code == 422
    too_big = {**body, "extent": "box", "box": [-89.0, 41.0, -88.0, 42.0]}
    assert admin.post(WHOLE_ROAD, json=too_big).status_code == 422


def _server_answers(
    monkeypatch: pytest.MonkeyPatch, answers: dict[str, Any]
) -> list[str]:
    """Stand-in for the three Overpass servers: answers by host name (an Exception is raised)."""
    from app.services import whole_road

    asked: list[str] = []

    class Answer:
        def __init__(self, status: int, data: Any) -> None:
            self.status_code = status
            self._data = data

        def json(self) -> Any:
            if isinstance(self._data, ValueError):
                raise self._data
            return self._data

    def fake_post(url: str, **_: object) -> Answer:
        host = url.split("/")[2]
        asked.append(host)
        result = answers.get(host, requests.ConnectionError())  # not named
        if isinstance(result, Exception):
            raise result
        return Answer(*result)

    monkeypatch.setattr(whole_road.requests, "post", fake_post)
    return asked


def test_the_first_good_server_wins_and_bad_ones_are_skipped(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = _server_answers(
        monkeypatch,
        {
            "overpass-api.de": requests.ReadTimeout(),
            "overpass.private.coffee": (
                200,
                {"elements": [], "remark": "runtime error: timed out"},
            ),
            "maps.mail.ru": (200, {"elements": [PIECE_A, PIECE_B]}),
        },
    )
    admin = _admin(db, client)

    found = admin.post(WHOLE_ROAD, json={**SEARCH, "sources": ["overpass"]})

    assert found.status_code == 200, found.text
    assert found.json()["pieces"] == 2
    assert (
        "maps.mail.ru" in asked
    )  # the servers are asked together, not one after the other


def test_when_every_server_fails_the_error_names_each_one(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _server_answers(
        monkeypatch,
        {
            "overpass-api.de": requests.ReadTimeout(),
            "overpass.private.coffee": (504, {}),
            "maps.mail.ru": (200, ValueError("bad")),
        },
    )
    admin = _admin(db, client)

    failed = admin.post(WHOLE_ROAD, json={**SEARCH, "sources": ["overpass"]})

    assert failed.status_code == 503
    message = failed.json()["error"]["message"]
    for part in (
        "overpass-api.de: ReadTimeout",
        "overpass.private.coffee: answer 504",
        "not JSON",
    ):
        assert part in message


def _section(
    db: Session, key: str, name: str | None, ref: str | None, line: str
) -> None:
    db.add(
        ForecastSection(
            area_key="naperville",
            section_key=key,
            name=name,
            road_ref=ref,
            road_type="residential",
            length_m=100.0,
            line=line,
        )
    )


def test_our_own_database_finds_the_road_when_the_map_servers_are_down(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_overpass(monkeypatch, ServiceUnavailableError("down"), [])
    admin = _admin(db, client)
    _section(
        db,
        "1",
        "Washington Street",
        "IL 59",
        "SRID=4326;LINESTRING(-88.15 41.77, -88.15 41.775)",
    )
    _section(
        db,
        "2",
        "N Washington St",
        None,
        "SRID=4326;LINESTRING(-88.15 41.775, -88.15 41.779)",
    )
    _section(
        db,
        "3",
        "Other Road",
        "IL 59;US 30",
        "SRID=4326;LINESTRING(-88.14 41.77, -88.14 41.775)",
    )
    _section(
        db,
        "4",
        "Washington Street",
        None,
        "SRID=4326;LINESTRING(-87.0 41.0, -87.0 41.01)",
    )
    db.commit()
    body = {**SEARCH, "name": "Washington Street", "sources": ["overpass", "database"]}

    by_name = admin.post(WHOLE_ROAD, json=body)
    assert by_name.status_code == 200, by_name.text
    road = by_name.json()
    # Both spellings of the name, but not another road, and not the same name far away.
    assert road["source"] == "database" and road["pieces"] == 2
    assert road["shape"]["type"] == "MultiLineString" and 0.9 < road["length_km"] < 1.1

    by_ref = admin.post(WHOLE_ROAD, json={**body, "name": "US 30", "by_ref": True})
    assert by_ref.status_code == 200 and by_ref.json()["pieces"] == 1

    only_database = admin.post(
        WHOLE_ROAD, json={**body, "sources": ["database"], "name": "Nope Rd"}
    )
    assert (
        only_database.status_code == 404
    )  # asked and found nothing: not "unavailable"
    # With the map servers down and nothing in our database the person is told the service is down.
    assert admin.post(WHOLE_ROAD, json={**body, "name": "Nope Rd"}).status_code == 503


def test_a_very_long_road_is_thinned_to_fit_the_shape_limit(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    bends = [
        {"lat": 41.0 + i * 1e-6, "lon": -88.0 + (i % 2) * 1e-6} for i in range(30_000)
    ]
    _fake_overpass(
        monkeypatch, {"elements": [{"type": "way", "id": 9, "geometry": bends}]}, []
    )
    admin = _admin(db, client)

    road = admin.post(WHOLE_ROAD, json={**SEARCH, "sources": ["overpass"]}).json()

    points = road["shape"]["coordinates"][0]
    assert len(points) < 19_500 and points[-1] == pytest.approx([-87.999999, 41.029999])
