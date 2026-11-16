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

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
MAX_PIECES = 400


def _quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _query(body: WholeRoadRequest) -> str:
    key = "ref" if body.by_ref else "name"
    return (
        "[out:json][timeout:25];"
        f"way(around:{body.radius_m},{body.latitude:.6f},{body.longitude:.6f})"
        f'["highway"][{_quoted(key)}={_quoted(body.name.strip())}];'
        "out geom;"
    )


def _overpass(query: str) -> dict[str, Any]:
    try:
        answer = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"User-Agent": "GeoInfraLens AI (road condition app)"},
            timeout=40,
        )
        answer.raise_for_status()
        return answer.json()
    except (requests.RequestException, ValueError) as error:
        log.warning("Overpass whole-road search failed: %s", error)
        raise ServiceUnavailableError(
            "The map service could not find the rest of the road right now. "
            "Try again in a minute, or add the parts one by one."
        ) from error


def whole_road(body: WholeRoadRequest) -> dict[str, Any]:
    """All pieces of the named road near the point, as a MultiLineString."""
    data = _overpass(_query(body))
    lines: list[list[list[float]]] = []
    for element in data.get("elements", [])[:MAX_PIECES]:
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
