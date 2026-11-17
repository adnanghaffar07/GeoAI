"""Select the whole road (owner, 2026-11-16).

OpenStreetMap stores one road as many short pieces (a new piece wherever the speed limit, lanes,
a bridge or a crossing changes), and the place search returns only one of them. This collects
every piece with the same name (or route number) within a few kilometres of the piece found,
from OpenStreetMap's free Overpass service, as one line shape. Nothing is saved here.
"""

import itertools
import logging
import math
from typing import Any

import requests

from app.core.errors import NotFoundError, ServiceUnavailableError
from app.schemas.geo import WholeRoadRequest

log = logging.getLogger(__name__)

# Free public Overpass servers, tried in turn: the main one is often busy (answers 429 or 504).
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
MAX_PIECES = 400


def _quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _query(body: WholeRoadRequest, found_tags: dict[str, str]) -> str:
    """Pieces named like the search result, plus every piece sharing the found piece's own
    OpenStreetMap name or route number: the search may call Route 59 "Route 59" while the road
    itself is "Illinois Route 59" with route number "IL 59"."""
    key = "ref" if body.by_ref else "name"
    around = f"(around:{body.radius_m},{body.latitude:.6f},{body.longitude:.6f})"
    wanted = {(key, body.name.strip())}
    for tag in ("name", "ref"):
        value = (found_tags.get(tag) or "").strip()
        if value:
            # A way can carry several route numbers ("IL 59;US 30"): match each.
            for one in value.split(";") if tag == "ref" else [value]:
                if one.strip():
                    wanted.add((tag, one.strip()))
    parts = "".join(
        f'way{around}["highway"][{_quoted(tag)}={_quoted(value)}];' for tag, value in sorted(wanted)
    )
    return f"[out:json][timeout:25];({parts});out geom;"


def _found_tags(way_id: int | None) -> dict[str, str]:
    """The name and route number of the piece the search found (empty if unknown)."""
    if not way_id:
        return {}
    data = _overpass(f"[out:json][timeout:15];way({way_id});out tags;")
    for element in data.get("elements", []):
        tags = element.get("tags") or {}
        return {k: str(v) for k, v in tags.items() if k in ("name", "ref")}
    return {}


def _overpass(query: str) -> dict[str, Any]:
    problems: list[str] = []
    for url in OVERPASS_URLS:
        host = url.split("/")[2]
        try:
            answer = requests.post(
                url,
                data={"data": query},
                headers={
                    "User-Agent": "GeoInfraLens AI (road condition app)",
                    "Accept": "application/json",
                },
                timeout=35,
            )
            if answer.status_code != 200:
                problems.append(f"{host}: answer {answer.status_code}")
                continue
            return answer.json()
        except (requests.RequestException, ValueError) as error:
            problems.append(f"{host}: {type(error).__name__}")
    details = "; ".join(problems)
    log.warning("Overpass whole-road search failed: %s", details)
    raise ServiceUnavailableError(
        "The map service could not find the rest of the road right now. "
        f"Try again in a minute, or add the parts one by one. (Details: {details})"
    )


def whole_road(body: WholeRoadRequest) -> dict[str, Any]:
    """All pieces of the named road near the point, as a MultiLineString."""
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
    if not lines:
        raise NotFoundError(
            f"No road called “{body.name}” was found near this place on OpenStreetMap."
        )
    length_m = sum(_length_m(line) for line in lines)
    return {
        "shape": {"type": "MultiLineString", "coordinates": lines},
        "pieces": len(lines),
        "length_km": round(length_m / 1000, 1),
    }


def _length_m(line: list[list[float]]) -> float:
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in itertools.pairwise(line):
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        h = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        )
        total += 2 * 6_371_000 * math.asin(math.sqrt(h))
    return total
