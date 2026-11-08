"""Areas: one small file per place (config/areas/<area>.yaml), so the same code runs for any US area.

An area file holds everything about one place: its boundary, its 311 pothole data (only areas with history, "Level 2"),
its districts, weather stations, bus routes, and which regional sources (e.g. Illinois traffic counts) apply. National
sources (NOAA, USGS, FEMA, USDA, OpenStreetMap) are in config/sources.yaml. `sources_for(area)` merges the two into the
one dictionary the download, load and static steps read.

Each area has its own folders (data/<area>/raw, data/<area>/f2, models/<area>, reports/<area>) and its own database
schema inside the `forecast` database (owner decision D1, 2026-10-29).
Plan: documentation/04-design/forecasting-any-area-plan.md.
"""

from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from forecasting import settings

AREAS_DIR = settings.CONFIG_DIR / "areas"
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,40}$")  # also a safe database schema name
NATIONAL_KEYS = ["weather", "station_choice", "osm", "elevation", "flood_zones", "soils", "matching", "hpms"]


@dataclass(frozen=True)
class Area:
    key: str  # file name without .yaml, e.g. "chicago"
    name: str  # e.g. "City of Chicago"
    level: int  # 2 = has pothole history (tested forecast possible); 1 = risk factors only
    schema: str
    src: dict[str, Any]  # merged sources (national + this area)
    data_dir: Path
    models_dir: Path
    reports_dir: Path

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def f2_dir(self) -> Path:
        return self.data_dir / "f2"

    @property
    def crs(self) -> str:
        return self.src["projected_crs"]

    @property
    def has_potholes(self) -> bool:
        return "potholes_historical" in self.src or "potholes_current" in self.src


def check_name(key: str) -> str:
    if not NAME_PATTERN.match(key):
        raise SystemExit(f"Area names use small letters, digits and _ only (got '{key}').")
    return key


def available() -> list[str]:
    return sorted(path.stem for path in AREAS_DIR.glob("*.yaml"))


def read_area_file(key: str, areas_dir: Path | None = None) -> dict[str, Any]:
    path = (areas_dir or AREAS_DIR) / f"{check_name(key)}.yaml"
    if not path.exists():
        raise SystemExit(f"No area file {path}. Areas: {', '.join(available()) or '(none)'}")
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def utm_crs(lon: float, lat: float) -> str:
    """NAD83 / UTM zone of a point in the US (EPSG 26901-26923); Chicago is zone 16 = EPSG:26916."""
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError(f"Not a longitude/latitude: {lon}, {lat}")
    zone = int(math.floor((lon + 180) / 6)) + 1
    if not 1 <= zone <= 23 or lat < 0:
        raise SystemExit(f"Point {lon}, {lat} is outside the NAD83 UTM zones used for US areas.")
    return f"EPSG:{26900 + zone}"


def sources_for(key: str, national: dict[str, Any] | None = None, areas_dir: Path | None = None) -> dict[str, Any]:
    """National sources plus this area's file, in the shape the download, load and static steps read."""
    national = copy.deepcopy(national if national is not None else settings.sources())
    area = read_area_file(key, areas_dir)
    src: dict[str, Any] = {k: national[k] for k in NATIONAL_KEYS if k in national}
    src["area_key"] = key
    src["area_name"] = area.get("name", key)
    src["schema"] = check_name(area.get("schema", key))
    src["level"] = int(area.get("level", 1))
    boundary = area.get("boundary") or {}
    if not boundary:
        raise SystemExit(f"Area {key}: the area file needs a `boundary` (OpenStreetMap filter or a GeoJSON file).")
    src["boundary"] = boundary
    src["osm"] = dict(src["osm"], **{k: v for k, v in boundary.items() if k.startswith("osm_")})
    for name in ("bbox", "portal", "potholes_historical", "potholes_current", "system_switch_date", "districts",
                 "bus_routes", "cook_county_pci", "snow_station", "city_potholes"):  # fmt: skip
        if name in area:
            src[name] = area[name]
    if "projected_crs" in area:
        src["projected_crs"] = area["projected_crs"]
    elif "bbox" in area:
        b = area["bbox"]
        src["projected_crs"] = utm_crs((b["min_lon"] + b["max_lon"]) / 2, (b["min_lat"] + b["max_lat"]) / 2)
    # else: worked out from the boundary after it is downloaded (see `resolve_after_boundary`)
    stations = area.get("weather_stations", "auto")
    src["weather"] = dict(src["weather"], stations=stations if isinstance(stations, list) else "auto")
    for name in ("traffic_counts",):
        value = area.get(name)
        if isinstance(value, str):
            regional = national.get("regional", {})
            if value not in regional:
                raise SystemExit(f"Area {key}: {name} names '{value}', which is not under `regional` in config/sources.yaml.")
            src[name] = regional[value]
        elif isinstance(value, dict):
            src[name] = value
    if src["level"] == 2 and not ("potholes_historical" in src or "potholes_current" in src):
        raise SystemExit(f"Area {key} says level 2 but has no pothole history in its area file.")
    if any(k in src for k in ("potholes_historical", "potholes_current", "districts", "bus_routes")) and "portal" not in src:
        raise SystemExit(f"Area {key}: city datasets need a `portal` (the city's open data site) in the area file.")
    if "districts" not in src and not any(k in boundary for k in ("osm_relation_filter", "geojson_file")):
        raise SystemExit(
            f"Area {key}: without a districts dataset the boundary must be `osm_relation_filter` (+ `osm_within_filter`) "
            "or `geojson_file`, so roads outside the area can be left out."
        )
    return src


BOUNDARY_FILE = "boundary.geojson"  # written by the download for areas without a districts dataset
CHOICE_FILE = "weather_choice.json"  # written by the area check for areas with `weather_stations: auto`


def ready_sources(area: Area, need_box: bool = True) -> dict[str, Any]:
    """The area's sources with chosen weather stations, box and map zone filled in from the area check and boundary."""
    src = dict(area.src)
    choice_path = area.raw_dir / CHOICE_FILE
    if src["weather"]["stations"] == "auto" and choice_path.exists():
        choice = json.loads(choice_path.read_text(encoding="utf-8"))
        src["weather"] = dict(src["weather"], stations=choice["stations"])
        if choice.get("snow_station") and "snow_station" not in src:
            src["snow_station"] = choice["snow_station"]
    if "bbox" in src and "projected_crs" in src:
        return src
    path = area.raw_dir / BOUNDARY_FILE
    if path.exists():
        from shapely.geometry import shape

        return resolve_after_boundary(src, shape(json.loads(path.read_text(encoding="utf-8"))["features"][0]["geometry"]).bounds)
    if need_box:
        raise SystemExit(f"Area {area.key}: the boundary is not downloaded yet. Run `forecasting.run --area {area.key} area-check`.")
    return src


def load_area(key: str, forecast_dir: Path | None = None, areas_dir: Path | None = None) -> Area:
    """The area and its folders. forecast_dir defaults to ml/forecasting (tests pass a temporary folder)."""
    base = forecast_dir or settings.FORECAST_DIR
    src = sources_for(key, areas_dir=areas_dir)
    return Area(
        key=key,
        name=src["area_name"],
        level=src["level"],
        schema=src["schema"],
        src=src,
        data_dir=base / "data" / key,
        models_dir=base / "models" / key,
        reports_dir=base / "reports" / key,
    )


def resolve_after_boundary(src: dict[str, Any], bounds: tuple[float, float, float, float]) -> dict[str, Any]:
    """Fill in the box and map zone of an area that only has a boundary (lon/lat bounds of the boundary shape)."""
    out = dict(src)
    min_lon, min_lat, max_lon, max_lat = bounds
    margin = 0.005  # about 500 m, so roads along the edge are inside the box
    if "bbox" not in out:
        out["bbox"] = {
            "min_lon": round(min_lon - margin, 4),
            "min_lat": round(min_lat - margin, 4),
            "max_lon": round(max_lon + margin, 4),
            "max_lat": round(max_lat + margin, 4),
        }
    if "projected_crs" not in out:
        out["projected_crs"] = utm_crs((min_lon + max_lon) / 2, (min_lat + max_lat) / 2)
    return out
