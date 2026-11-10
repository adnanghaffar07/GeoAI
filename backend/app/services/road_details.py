# ruff: noqa: E501
"""Road details for each section (team lead plan, item 12): speed limit, lanes, surface, one-way, route number.

Read from the OpenStreetMap roads file the area already downloaded (osm_roads.json), so no new download. A section
id starts with its OpenStreetMap way number ("<way>-<piece>-<cut>"). The hourly check fills areas not done yet.
"""

import gzip
import json
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import ForecastSection

logger = logging.getLogger(__name__)

SURFACES = {
    "asphalt": "Asphalt",
    "concrete": "Concrete",
    "concrete:plates": "Concrete",
    "paved": "Paved",
    "paving_stones": "Paving stones",
    "sett": "Stone blocks",
    "cobblestone": "Cobblestone",
    "brick": "Brick",
    "chipseal": "Chip seal",
    "gravel": "Gravel",
    "unpaved": "Unpaved",
    "compacted": "Compacted gravel",
    "dirt": "Dirt",
    "ground": "Dirt",
}


def parse_speed(value: str | None) -> int | None:
    """'40 mph' -> 40; '50 km/h' or '50' outside the US unit -> mph. Several values ('25;35'): the highest."""
    if not value:
        return None
    best = None
    for part in value.split(";"):
        match = re.match(r"\s*(\d+(?:\.\d+)?)\s*(mph|km/h|kmh|kph)?\s*$", part.strip().lower())
        if not match:
            continue
        number = float(match.group(1))
        mph = number if match.group(2) in (None, "mph") else number / 1.609344
        if 5 <= mph <= 90:
            best = max(best or 0, round(mph))
    return best


def parse_lanes(value: str | None) -> int | None:
    numbers = [int(n) for n in re.findall(r"\d+", value or "") if 0 < int(n) <= 12]
    return max(numbers) if numbers else None


def parse_oneway(value: str | None) -> bool | None:
    if value in ("yes", "true", "1", "-1"):
        return True
    if value in ("no", "false", "0"):
        return False
    return None


def surface_label(value: str | None) -> str | None:
    if not value:
        return None
    return SURFACES.get(value, value.replace("_", " ").capitalize())[:40]


def way_details(raw_dir: Path) -> dict[int, dict[str, Any]]:
    path = raw_dir / "osm_roads.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    elif (raw_dir / "osm_roads.json.gz").exists():
        with gzip.open(raw_dir / "osm_roads.json.gz", "rt", encoding="utf-8") as handle:
            data = json.load(handle)
    else:
        return {}
    out: dict[int, dict[str, Any]] = {}
    for element in data.get("elements", []):
        if element.get("type") != "way":
            continue
        tags = element.get("tags") or {}
        out[int(element["id"])] = {
            "speed_limit_mph": parse_speed(tags.get("maxspeed")),
            "lanes": parse_lanes(tags.get("lanes")),
            "surface": surface_label(tags.get("surface")),
            "oneway": parse_oneway(tags.get("oneway")),
            "road_ref": (tags.get("ref") or None) and tags["ref"][:60],
        }
    return out


def fill_area(db: Session, area_key: str, raw_dir: Path) -> int:
    """Fill every section of one area that is not filled yet. Returns how many got at least one detail."""
    details = way_details(raw_dir)
    rows = db.execute(
        select(ForecastSection.id, ForecastSection.section_key).where(
            ForecastSection.area_key == area_key, ForecastSection.details_filled.is_(False)
        )
    ).all()
    empty = dict.fromkeys(("speed_limit_mph", "lanes", "surface", "oneway", "road_ref"))
    changes, found = [], 0
    for section_id, key in rows:
        way = key.split("-", 1)[0]
        values = details.get(int(way), empty) if way.isdigit() else empty
        found += any(v is not None for v in values.values())
        changes.append({"id": section_id, **values, "details_filled": True})
    for start in range(0, len(changes), 5000):
        db.execute(update(ForecastSection), changes[start : start + 5000])
    db.commit()
    return found


def fill_missing(db: Session, raw_dir_for: Callable[[str], Path]) -> dict[str, Any]:
    """Every area with sections not filled yet (new set-ups and areas set up before item 12)."""
    keys = db.scalars(
        select(ForecastSection.area_key).where(ForecastSection.details_filled.is_(False)).distinct()
    ).all()
    out: dict[str, Any] = {}
    for key in keys:
        try:
            out[key] = fill_area(db, key, raw_dir_for(key))
        except Exception as error:  # noqa: BLE001 (one area never stops the others)
            db.rollback()
            out[key] = f"failed: {str(error)[:200]}"
            logger.warning("Road details for %s failed: %s", key, error)
    return out
