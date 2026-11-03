"""Choosing weather stations for an area (owner decision D3, 2026-10-29; settings in config/sources.yaml `station_choice`).

Rule: NOAA GHCN-Daily stations within 30 km of the area's box that report max/min temperature and rain, measured over
the last 10 full years; a station passes when at least 90% of days have both temperatures and at least 90% have rain.
The nearest passing stations are used (at most 3; each road section uses its nearest one). Snow comes from the chosen
station with the most complete snow record (the rule that picked O'Hare over Midway for Chicago).

The choice and every candidate's numbers are saved in data/<area>/raw/weather_choice.json and shown in the area report.
"""

from __future__ import annotations

import csv
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

from forecasting.download import download_file, sha256_file
from forecasting.load import ghcn_value

EARTH_KM = 6371.0
NEEDED = ("TMAX", "TMIN", "PRCP")


def parse_station_list(text: str) -> dict[str, dict[str, Any]]:
    """ghcnd-stations.txt (fixed columns): ID 1-11, LATITUDE 13-20, LONGITUDE 22-30, STATE 39-40, NAME 42-71."""
    out: dict[str, dict[str, Any]] = {}
    for line in text.splitlines():
        if len(line) < 41 or not line[:11].strip():
            continue
        try:
            lat, lon = float(line[12:20]), float(line[21:30])
        except ValueError:
            continue
        out[line[:11]] = {"id": line[:11], "lat": lat, "lon": lon, "state": line[38:40].strip(), "name": line[41:71].strip()}
    return out


def parse_inventory(text: str) -> dict[str, dict[str, tuple[int, int]]]:
    """ghcnd-inventory.txt: ID 1-11, ELEMENT 32-35, FIRSTYEAR 37-40, LASTYEAR 42-45."""
    out: dict[str, dict[str, tuple[int, int]]] = {}
    for line in text.splitlines():
        if len(line) < 45:
            continue
        try:
            out.setdefault(line[:11], {})[line[31:35]] = (int(line[36:40]), int(line[41:45]))
        except ValueError:
            continue
    return out


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(min(1.0, a)))


def distance_to_box_km(lat: float, lon: float, bbox: dict[str, float]) -> float:
    """0 inside the box; otherwise the distance to the nearest point of the box."""
    near_lat = min(max(lat, bbox["min_lat"]), bbox["max_lat"])
    near_lon = min(max(lon, bbox["min_lon"]), bbox["max_lon"])
    return haversine_km(lat, lon, near_lat, near_lon)


def candidates(
    stations: dict[str, dict[str, Any]],
    inventory: dict[str, dict[str, tuple[int, int]]],
    bbox: dict[str, float],
    cfg: dict[str, Any],
    year: int,
) -> list[dict[str, Any]]:
    """Stations near enough whose inventory covers temperature and rain for the whole measuring window, nearest first."""
    first_needed, last_needed = year - int(cfg["years"]), year - 1
    found = []
    for station_id, station in stations.items():
        elements = inventory.get(station_id, {})
        if not all(e in elements and elements[e][0] <= first_needed and elements[e][1] >= last_needed for e in NEEDED):
            continue
        distance = distance_to_box_km(station["lat"], station["lon"], bbox)
        if distance <= float(cfg["max_distance_km"]):
            found.append(dict(station, distance_km=round(distance, 1), has_snow="SNOW" in elements))
    return sorted(found, key=lambda s: (s["distance_km"], s["id"]))


def completeness(path: Path, first: date, last: date) -> dict[str, float]:
    """Share of days first..last with both temperatures, with rain, and with snow (quality-flagged values count as missing)."""
    total = (last - first).days + 1
    temp = prcp = snow = 0
    with path.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            try:
                day = date.fromisoformat(record["DATE"].strip())
            except (KeyError, ValueError):
                continue
            if not first <= day <= last:
                continue

            def ok(element: str, record: dict[str, str] = record) -> bool:
                value, rejected = ghcn_value(record.get(element), record.get(f"{element}_ATTRIBUTES"), 1.0)
                return value is not None and not rejected

            temp += ok("TMAX") and ok("TMIN")
            prcp += ok("PRCP")
            snow += ok("SNOW")
    return {"temperature": round(temp / total, 3), "rain": round(prcp / total, 3), "snow": round(snow / total, 3)}


def choose(measured: list[dict[str, Any]], cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """The nearest stations that pass (at most max_stations) and the chosen station with the most complete snow record."""
    limit = float(cfg["min_complete_share"])
    passing = [s for s in measured if s["share"]["temperature"] >= limit and s["share"]["rain"] >= limit]
    chosen = sorted(passing, key=lambda s: (s["distance_km"], s["id"]))[: int(cfg["max_stations"])]
    with_snow = [s for s in chosen if s["share"]["snow"] > 0]
    snow = max(with_snow, key=lambda s: (s["share"]["snow"], -s["distance_km"]))["id"] if with_snow else None
    return chosen, snow


def run_station_choice(
    raw_dir: Path, national_dir: Path, src: dict[str, Any], session, today: date | None = None, sleep=None
) -> dict[str, Any]:
    """Download the NOAA station lists (kept in data/_national/), measure the nearest candidates, save the choice."""
    today = today or date.today()
    cfg, weather = src["station_choice"], src["weather"]
    national_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    kwargs = {"sleep": sleep} if sleep else {}
    texts = {}
    for name, url in (("ghcnd-stations.txt", weather["station_list_url"]), ("ghcnd-inventory.txt", weather["inventory_url"])):
        path = national_dir / name
        if not path.exists():
            print(f"  downloading the NOAA {name}", flush=True)
            download_file(session, url, path, **kwargs)
        texts[name] = path.read_text(encoding="utf-8", errors="replace")
    near = candidates(
        parse_station_list(texts["ghcnd-stations.txt"]), parse_inventory(texts["ghcnd-inventory.txt"]), src["bbox"], cfg, today.year
    )
    first, last = date(today.year - int(cfg["years"]), 1, 1), date(today.year - 1, 12, 31)
    measured = []
    for station in near[: int(cfg["max_candidates"])]:
        path = raw_dir / f"weather_{station['id']}.csv"
        print(f"  measuring {station['id']} {station['name']} ({station['distance_km']} km)", flush=True)
        if not path.exists():
            download_file(session, weather["url_template"].format(station=station["id"]), path, **kwargs)
        measured.append(dict(station, share=completeness(path, first, last), file_sha256=sha256_file(path)))
    chosen, snow = choose(measured, cfg)
    choice = {
        "rule": cfg,
        "measured_from": str(first),
        "measured_to": str(last),
        "candidates_found": len(near),
        "measured": measured,
        "stations": [{"id": s["id"], "name": s["name"].title(), "lat": s["lat"], "lon": s["lon"]} for s in chosen],
        "snow_station": snow,
        "chosen_at": today.isoformat(),
    }
    (raw_dir / "weather_choice.json").write_text(json.dumps(choice, indent=2), encoding="utf-8")
    return choice
