"""Select the whole road (owner, 2026-11-16; made to always work, 2026-11-17).

OpenStreetMap stores one road as many short pieces (a new piece wherever the speed limit, lanes,
a bridge or a crossing changes), and the place search returns only one of them. This collects
every piece with the same name (or route number) in a chosen place, as one line shape.
Nothing is saved here.

The pieces come from a chain of sources, each tried only if the one before fails:

1. "overpass": OpenStreetMap's free Overpass servers. The search is tag first, inside a box (or
   inside the town limits), because the old "within 5 km" search made the servers check
   thousands of roads and time out. All servers are asked at the same time; the first good
   answer wins.
2. (The browser's Nominatim search and the OSRM route are steps 2 and 4 of the chain; they run in
   the browser: `frontend/src/lib/whole-road.ts`.)
3. "database": the road sections already loaded for road-risk forecasting (Chicago, Naperville).

The caller picks the sources with `sources`; the answer says which one was used.
"""

import itertools
import json
import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ServiceUnavailableError
from app.schemas.geo import MAX_PLACE_POINTS, WholeRoadRequest

log = logging.getLogger(__name__)

# Free public Overpass servers. All are asked at the same time (the main one is often busy).
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
)
# The web host in front of the app gives up after about 30 seconds: stay well inside it.
OVERPASS_TIMEOUT_S = 20
TAG_LOOKUP_TIMEOUT_S = 5
MAX_PIECES = 1000
METERS_PER_DEGREE = 111_320.0
# Leave room in the shape limit for the strip-making step.
MAX_POINTS = MAX_PLACE_POINTS - 1_000


class _BadAnswer(Exception):
    """One Overpass server gave no usable answer (the text says why)."""


def _quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _box(body: WholeRoadRequest) -> tuple[float, float, float, float]:
    """South, west, north, east of the place to search."""
    if body.extent == "box" and body.box:
        west, south, east, north = body.box
        return south, west, north, east
    dlat = body.radius_m / METERS_PER_DEGREE
    dlon = body.radius_m / (
        METERS_PER_DEGREE * max(math.cos(math.radians(body.latitude)), 0.05)
    )
    return (
        body.latitude - dlat,
        body.longitude - dlon,
        body.latitude + dlat,
        body.longitude + dlon,
    )


def _wanted(body: WholeRoadRequest, found_tags: dict[str, str]) -> set[tuple[str, str]]:
    """The tag/value pairs that make a piece part of the road: the name or route number typed,
    plus the found piece's own OpenStreetMap name and route numbers (the search may call Route 59
    "Route 59" while the road itself is "Illinois Route 59" with route number "IL 59")."""
    key = "ref" if body.by_ref else "name"
    wanted = {(key, body.name.strip())}
    for tag in ("name", "ref"):
        value = (found_tags.get(tag) or "").strip()
        if value:
            # A way can carry several route numbers ("IL 59;US 30"): match each.
            for one in value.split(";") if tag == "ref" else [value]:
                if one.strip():
                    wanted.add((tag, one.strip()))
    return wanted


def _query(body: WholeRoadRequest, found_tags: dict[str, str]) -> str:
    """Tag first, then the place: way["highway"]["name"="X"](south,west,north,east);"""
    prelude = ""
    if body.extent == "town":
        # The town (administrative boundary) that contains the point: several towns share a name.
        prelude = (
            f"is_in({body.latitude:.6f},{body.longitude:.6f})->.p;"
            f'area.p["boundary"="administrative"]["name"={_quoted(body.town or "")}]->.a;'
        )
        where = "(area.a)"
    else:
        south, west, north, east = _box(body)
        where = f"({south:.6f},{west:.6f},{north:.6f},{east:.6f})"
    parts = "".join(
        f'way["highway"][{_quoted(tag)}={_quoted(value)}]{where};'
        for tag, value in sorted(_wanted(body, found_tags))
    )
    return f"[out:json][timeout:{OVERPASS_TIMEOUT_S}];{prelude}({parts});out geom;"


def _found_tags(way_id: int | None) -> dict[str, str]:
    """The name and route number of the piece the search found (empty if unknown or the map
    servers are slow: the road is then looked up by the name that was typed)."""
    if not way_id:
        return {}
    try:
        data = _overpass(
            f"[out:json][timeout:4];way({way_id});out tags;", TAG_LOOKUP_TIMEOUT_S
        )
    except ServiceUnavailableError:
        return {}
    for element in data.get("elements", []):
        tags = element.get("tags") or {}
        return {k: str(v) for k, v in tags.items() if k in ("name", "ref")}
    return {}


def _ask_one(url: str, query: str, timeout: int) -> dict[str, Any]:
    try:
        answer = requests.post(
            url,
            data={"data": query},
            headers={
                # No contact details: nothing about the person or the organization is sent out.
                "User-Agent": "GeoInfraLens AI (road condition app)",
                "Accept": "application/json",
            },
            timeout=timeout,
        )
    except requests.RequestException as error:
        raise _BadAnswer(type(error).__name__) from error
    if answer.status_code != 200:
        raise _BadAnswer(f"answer {answer.status_code}")
    try:
        data = answer.json()
    except ValueError as error:
        raise _BadAnswer("not JSON") from error
    if not isinstance(data, dict) or "elements" not in data:
        raise _BadAnswer("no answer")
    # A busy server can answer 200 with a note that the search ran out of time.
    if "runtime error" in str(data.get("remark", "")):
        raise _BadAnswer("search ran out of time")
    return data


def _overpass(query: str, timeout: int = OVERPASS_TIMEOUT_S) -> dict[str, Any]:
    """Ask every server at the same time and return the first good answer."""
    problems: list[str] = []
    pool = ThreadPoolExecutor(max_workers=len(OVERPASS_URLS))
    try:
        futures = {
            pool.submit(_ask_one, url, query, timeout): url for url in OVERPASS_URLS
        }
        try:
            for future in as_completed(futures, timeout=timeout + 1):
                host = futures[future].split("/")[2]
                try:
                    return future.result()
                except _BadAnswer as error:
                    problems.append(f"{host}: {error}")
        except TimeoutError:
            problems.append("no answer in time")
    finally:
        pool.shutdown(
            wait=False, cancel_futures=True
        )  # slow servers are not waited for
    details = "; ".join(problems)
    log.warning("Overpass whole-road search failed: %s", details)
    raise ServiceUnavailableError(
        f"The fast map search did not answer in time. (Details: {details})",
    )


def _lines_from_overpass(body: WholeRoadRequest) -> list[list[list[float]]]:
    data = _overpass(_query(body, _found_tags(body.osm_way_id)))
    lines: list[list[list[float]]] = []
    seen: set[object] = set()
    for element in data.get("elements", [])[:MAX_PIECES]:
        if element.get("id") is not None:
            if element["id"] in seen:
                continue
            seen.add(element["id"])
        points = element.get("geometry") or []
        line = [
            [round(float(p["lon"]), 7), round(float(p["lat"]), 7)]
            for p in points
            if "lon" in p and "lat" in p
        ]
        if len(line) >= 2:
            lines.append(line)
    return lines


# --- our own database (road sections loaded for forecasting) ------------------------------------

_ABBREVIATIONS = {
    "st": "street",
    "rd": "road",
    "ave": "avenue",
    "av": "avenue",
    "blvd": "boulevard",
    "dr": "drive",
    "ln": "lane",
    "ct": "court",
    "hwy": "highway",
    "pkwy": "parkway",
    "pl": "place",
    "cir": "circle",
    "trl": "trail",
    "n": "north",
    "s": "south",
    "e": "east",
    "w": "west",
}


_DIRECTIONS = {"north", "south", "east", "west"}


def _normal(name: str) -> str:
    """ "N. Washington St", "North Washington Street" and "Washington Street" are one road.
    A direction is dropped only when another word besides the street type is left ("North
    Avenue" keeps its name)."""
    words = [
        _ABBREVIATIONS.get(word, word)
        for word in re.findall(r"[a-z0-9]+", name.lower())
    ]
    rest = [word for word in words if word not in _DIRECTIONS]
    return " ".join(rest if len(rest) >= 2 else words)


def _lines_from_database(
    db: Session, body: WholeRoadRequest
) -> list[list[list[float]]]:
    wanted = _wanted(body, {})
    names = {_normal(value) for tag, value in wanted if tag == "name"}
    refs = {_normal(value) for tag, value in wanted if tag == "ref"}
    if body.by_ref:
        refs.add(_normal(body.name))
    south, west, north, east = _box(body)
    # Cheap pre-filter in the database on each wanted word; the exact test is made below.
    words = {max(_normal(v).split() or [""], key=len) for _, v in wanted}
    words.discard("")
    if not words:
        return []
    likes = " OR ".join(
        f"lower(coalesce(s.name, '') || ' ' || coalesce(s.road_ref, '')) LIKE :w{i}"
        for i in range(len(words))
    )
    params: dict[str, Any] = {
        "west": west,
        "south": south,
        "east": east,
        "north": north,
    }
    params.update({f"w{i}": f"%{word}%" for i, word in enumerate(sorted(words))})
    rows = db.execute(
        text(
            "SELECT s.name, s.road_ref, ST_AsGeoJSON(s.line) FROM forecast_sections s "
            "WHERE ST_Intersects(s.line, ST_MakeEnvelope(:west, :south, :east, :north, 4326)) "
            f"AND ({likes}) LIMIT :limit"
        ),
        {**params, "limit": MAX_PIECES * 5},
    ).all()
    lines: list[list[list[float]]] = []
    for name, road_ref, geojson in rows:
        pieces_refs = {
            _normal(part) for part in (road_ref or "").split(";") if part.strip()
        }
        if not ((name and _normal(name) in names) or pieces_refs & refs):
            continue
        coordinates = json.loads(geojson).get("coordinates") or []
        line = [[round(float(x), 7), round(float(y), 7)] for x, y, *_ in coordinates]
        if len(line) >= 2:
            lines.append(line)
        if len(lines) >= MAX_PIECES:
            break
    return lines


# --- joining the answer -------------------------------------------------------------------------


def _thin(lines: list[list[list[float]]]) -> list[list[list[float]]]:
    """Keep the shape within the point limit: drop evenly spaced bends of very long roads."""
    total = sum(len(line) for line in lines)
    if total <= MAX_POINTS:
        return lines
    step = math.ceil(total / MAX_POINTS)
    return [[*line[:-1:step], line[-1]] for line in lines]


def whole_road(db: Session, body: WholeRoadRequest) -> dict[str, Any]:
    """The parts of the named road in the chosen place, as a MultiLineString plus the source used."""
    problems: list[str] = []
    for source in body.sources:
        try:
            if source == "overpass":
                lines = _lines_from_overpass(body)
            else:
                lines = _lines_from_database(db, body)
        except ServiceUnavailableError as error:
            problems.append(error.message)
            continue
        if lines:
            lines = _thin(lines)
            length_m = sum(_length_m(line) for line in lines)
            return {
                "shape": {"type": "MultiLineString", "coordinates": lines},
                "pieces": len(lines),
                "length_km": round(length_m / 1000, 1),
                "source": source,
            }
    if problems:
        raise ServiceUnavailableError(
            "The map service could not find the rest of the road right now. "
            + " ".join(problems)
        )
    raise NotFoundError(f"No road called “{body.name}” was found in this place.")


def _length_m(line: list[list[float]]) -> float:
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in itertools.pairwise(line):
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        h = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        total += 2 * 6_371_000 * math.asin(math.sqrt(h))
    return total
