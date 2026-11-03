"""F1 step 1: download one area's raw data into ml/forecasting/data/<area>/raw/ and record each file in manifest.json.

Every file gets its source URL, download time, size, SHA-256 fingerprint, row count and licence, which the dataset
card and the F1 report read. Re-running skips files that are already downloaded unless --force is given.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

TIMEOUT_S = 120
PARTIAL_DOWNLOAD_EXIT_CODE = 3  # some items failed, the rest are saved; the load can still run
RETRIES = 3
UTC_TZ = timezone.utc  # noqa: UP017 (datetime.UTC needs Python 3.11; this also runs on 3.10)


class SourceChangedError(RuntimeError):
    """The portal returned something other than what sources.yaml expects (renamed column, removed dataset)."""


def user_agent() -> str:
    contact = os.environ.get("FORECAST_CONTACT_EMAIL", "").strip()
    return "GeoInfraLens-forecast-research/0.1" + (f" ({contact})" if contact else "")


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = user_agent()
    return session


def request_with_retries(session: requests.Session, method: str, url: str, sleep: Callable[[float], None] = time.sleep, **kwargs: Any):
    """Retry network errors, rate limits and server errors; stop at once on other client errors (they will not fix themselves)."""
    timeout = kwargs.pop("timeout", TIMEOUT_S)
    for attempt in range(1, RETRIES + 1):
        try:
            response = session.request(method, url, timeout=timeout, **kwargs)
        except requests.RequestException as error:
            if attempt == RETRIES:
                raise RuntimeError(f"Could not reach {url}: {error}") from error
        else:
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == RETRIES:
                    raise RuntimeError(f"{url} answered HTTP {response.status_code} after {RETRIES} tries: {response.text[:300]}")
            elif response.status_code >= 400:
                raise SourceChangedError(f"{url} answered HTTP {response.status_code}: {response.text[:500]}")
            else:
                return response
        sleep(10 * attempt)
    raise AssertionError("unreachable")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download_socrata_csv(
    session: requests.Session,
    *,
    base_url: str,
    dataset_id: str,
    select: list[str],
    where: str,
    page_size: int,
    out_path: Path,
    app_token: str | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Download only the selected columns of a portal dataset, page by page, into one CSV. Returns the number of rows."""
    url = f"{base_url.rstrip('/')}/resource/{dataset_id}.csv"
    headers = {"X-App-Token": app_token} if app_token else {}
    rows = 0
    offset = 0
    tmp_path = out_path.with_suffix(".part")
    with tmp_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(select)
        while True:
            params = {"$select": ",".join(select), "$where": where, "$order": ":id", "$limit": page_size, "$offset": offset}
            response = request_with_retries(session, "GET", url, params=params, headers=headers, sleep=sleep)
            reader = csv.reader(io.StringIO(response.content.decode("utf-8")))
            header = next(reader, None)
            if header != select:
                raise SourceChangedError(f"{dataset_id}: expected columns {select}, got {header}. Update config/sources.yaml.")
            page = list(reader)
            writer.writerows(page)
            rows += len(page)
            print(f"  {dataset_id}: {rows:,} rows", flush=True)
            if len(page) < page_size:
                break
            offset += page_size
    tmp_path.replace(out_path)
    return rows


def download_file(session: requests.Session, url: str, out_path: Path, *, method: str = "GET", sleep=time.sleep, **kwargs: Any) -> None:
    response = request_with_retries(session, method, url, sleep=sleep, stream=True, **kwargs)
    tmp_path = out_path.with_suffix(".part")
    with tmp_path.open("wb") as handle:
        for block in response.iter_content(1 << 20):
            handle.write(block)
    tmp_path.replace(out_path)


def download_arcgis_layers(
    session: requests.Session,
    *,
    base_url: str,
    layers: dict[int, str],
    out_fields: list[str],
    page_size: int,
    out_path: Path,
    tag_field: str = "township",
    extra_params: dict[str, Any] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Download several layers of an ArcGIS map service as one GeoJSON file; each feature gets its layer name in tag_field."""
    features: list[dict[str, Any]] = []
    for layer_id, layer_name in layers.items():
        offset = 0
        while True:
            params = {
                "where": "1=1",
                "outFields": ",".join(out_fields),
                "outSR": 4326,
                "orderByFields": "OBJECTID",
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "f": "geojson",
                **(extra_params or {}),
            }
            response = request_with_retries(session, "GET", f"{base_url.rstrip('/')}/{layer_id}/query", params=params, sleep=sleep)
            data = json.loads(response.content.decode("utf-8"))
            if "error" in data or "features" not in data:
                raise SourceChangedError(f"Layer {layer_id} ({layer_name}) answered: {str(data)[:300]}. Update config/sources.yaml.")
            for feature in data["features"]:
                feature.setdefault("properties", {}).update({tag_field: layer_name, "layer_id": layer_id})
            features.extend(data["features"])
            print(f"  layer {layer_id} {layer_name}: {offset + len(data['features']):,} features", flush=True)
            if len(data["features"]) < page_size:
                break
            offset += page_size
    tmp_path = out_path.with_suffix(".part")
    tmp_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    tmp_path.replace(out_path)
    return len(features)


def bbox_envelope(bbox: dict[str, float]) -> dict[str, Any]:
    """ArcGIS query parameters that limit a statewide or national layer to the area's box."""
    return {
        "geometry": f"{bbox['min_lon']},{bbox['min_lat']},{bbox['max_lon']},{bbox['max_lat']}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
    }


def envelope_params(x1: float, y1: float, x2: float, y2: float) -> dict[str, Any]:
    return {
        "geometry": ",".join(str(round(v, 6)) for v in (x1, y1, x2, y2)),  # rounded: no 87.67500000000001
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
    }


def download_arcgis_tiled(
    session: requests.Session,
    *,
    layer_url: str,
    where: str,
    out_fields: list[str],
    bbox: dict[str, float],
    tile_deg: float,
    max_offset_deg: float,
    out_path: Path,
    max_splits: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Ask a busy ArcGIS layer for one small square at a time (no paging), with simplified shapes.

    A square whose answer is cut short (exceededTransferLimit) is split into four and asked again, up to max_splits times.
    Features found in two squares are kept once (by OBJECTID).
    """
    features: dict[Any, dict[str, Any]] = {}

    def ask(x1: float, y1: float, x2: float, y2: float, depth: int) -> None:
        params = {
            "where": where,
            "outFields": ",".join(out_fields),
            "outSR": 4326,
            "returnGeometry": "true",
            "maxAllowableOffset": max_offset_deg,
            "geometryPrecision": 6,
            "f": "geojson",
            **envelope_params(x1, y1, x2, y2),
        }
        response = request_with_retries(session, "GET", f"{layer_url.rstrip('/')}/query", params=params, sleep=sleep)
        data = json.loads(response.content.decode("utf-8"))
        if "error" in data or "features" not in data:
            raise SourceChangedError(f"{layer_url} answered: {str(data)[:300]}")
        cut_short = data.get("exceededTransferLimit") or (data.get("properties") or {}).get("exceededTransferLimit")
        if cut_short and depth < max_splits:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            for box in ((x1, y1, mx, my), (mx, y1, x2, my), (x1, my, mx, y2), (mx, my, x2, y2)):
                ask(*box, depth + 1)
            return
        if cut_short:
            raise SourceChangedError(f"{layer_url}: a {x2 - x1:.4f}° square is still too big after {max_splits} splits")
        for feature in data["features"]:
            key = (feature.get("properties") or {}).get("OBJECTID", feature.get("id"))
            features[key if key is not None else len(features)] = feature

    columns = max(1, math.ceil(round((bbox["max_lon"] - bbox["min_lon"]) / tile_deg, 9)))
    rows = max(1, math.ceil(round((bbox["max_lat"] - bbox["min_lat"]) / tile_deg, 9)))
    for row in range(rows):
        for column in range(columns):
            x1, y1 = bbox["min_lon"] + column * tile_deg, bbox["min_lat"] + row * tile_deg
            ask(x1, y1, min(x1 + tile_deg, bbox["max_lon"]), min(y1 + tile_deg, bbox["max_lat"]), 0)
        print(f"  flood zones: row {row + 1}/{rows}, {len(features):,} areas", flush=True)
    tmp_path = out_path.with_suffix(".part")
    tmp_path.write_text(json.dumps({"type": "FeatureCollection", "features": list(features.values())}), encoding="utf-8")
    tmp_path.replace(out_path)
    return len(features)


def point_key(lon: float, lat: float) -> str:
    return f"{lon:.6f},{lat:.6f}"


def download_elevation_samples(
    session: requests.Session,
    *,
    url: str,
    points: list[tuple[float, float]],
    batch_size: int,
    out_path: Path,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Ground height (meters) at each point from the USGS 3DEP service. Resumable: points already in the .part file are skipped.

    CSV columns: key ("lon,lat" with 6 decimals), elevation_m (empty when the service has no value).
    """
    tmp_path = out_path.with_suffix(".part")
    done: set[str] = set()
    if tmp_path.exists():
        with tmp_path.open(encoding="utf-8", newline="") as handle:
            done = {row[0] for row in csv.reader(handle) if row and row[0] != "key"}
    todo = sorted({point_key(lon, lat) for lon, lat in points} - done)
    print(f"  {len(done):,} points already sampled, {len(todo):,} to go", flush=True)
    with tmp_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if not done:
            writer.writerow(["key", "elevation_m"])
        for start in range(0, len(todo), batch_size):
            batch = todo[start : start + batch_size]
            geometry = {"points": [[float(v) for v in key.split(",")] for key in batch], "spatialReference": {"wkid": 4326}}
            form = {"geometry": json.dumps(geometry), "geometryType": "esriGeometryMultipoint", "returnFirstValueOnly": "true", "f": "json"}
            response = request_with_retries(session, "POST", f"{url.rstrip('/')}/getSamples", data=form, sleep=sleep)
            data = json.loads(response.content.decode("utf-8"))
            if "error" in data or "samples" not in data:
                raise SourceChangedError(f"Elevation service answered: {str(data)[:300]}")
            values = {sample.get("locationId"): sample.get("value") for sample in data["samples"]}
            for index, key in enumerate(batch):
                value = parse_number(values.get(index))
                writer.writerow([key, "" if value is None else round(value, 2)])
            handle.flush()
            if (start // batch_size) % 20 == 0:
                print(f"  elevation: {len(done) + start + len(batch):,} points", flush=True)
    tmp_path.replace(out_path)
    return len(done) + len(todo)


def parse_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None  # "NoData" or missing
    return number if number == number else None  # NaN check


def sda_query(session: requests.Session, url: str, query: str, sleep=time.sleep) -> list[list[Any]]:
    """Run one USDA Soil Data Access query; returns data rows (the first row of the answer is the column names)."""
    response = request_with_retries(session, "POST", url, json={"query": query, "format": "JSON+COLUMNNAME"}, timeout=300, sleep=sleep)
    text = response.content.decode("utf-8").strip()
    if not text:
        return []
    data = json.loads(text)
    if not isinstance(data, dict) or "Table" not in data:
        return [] if data == {} else _raise_source(f"Soil Data Access answered: {text[:300]}")
    return data["Table"][1:]


def _raise_source(message: str):
    raise SourceChangedError(message)


def bbox_tiles(bbox: dict[str, float], step: float) -> list[str]:
    """Split the box into squares of `step` degrees (counted with integers, so rounding never adds a sliver tile)."""
    columns = max(1, math.ceil(round((bbox["max_lon"] - bbox["min_lon"]) / step, 9)))
    rows = max(1, math.ceil(round((bbox["max_lat"] - bbox["min_lat"]) / step, 9)))
    tiles = []
    for row in range(rows):
        for column in range(columns):
            x1, y1 = bbox["min_lon"] + column * step, bbox["min_lat"] + row * step
            x2, y2 = min(x1 + step, bbox["max_lon"]), min(y1 + step, bbox["max_lat"])
            tiles.append(f"POLYGON(({x1:.4f} {y1:.4f},{x2:.4f} {y1:.4f},{x2:.4f} {y2:.4f},{x1:.4f} {y2:.4f},{x1:.4f} {y1:.4f}))")
    return tiles


def download_sda_soils(
    session: requests.Session, *, url: str, bbox: dict[str, float], tile_deg: float, out_path: Path, sleep=time.sleep
) -> int:
    """Soil map units over the area's box (tile by tile) and the drainage class of each unit's main soil."""
    polygons: dict[str, dict[str, Any]] = {}
    tiles = bbox_tiles(bbox, tile_deg)
    for number, tile in enumerate(tiles, start=1):
        query = (
            "SELECT mupolygonkey, mukey, mupolygongeo.STAsText() AS wkt FROM mupolygon WHERE mupolygonkey IN "  # noqa: S608 (our own tile box)
            f"(SELECT * FROM SDA_Get_Mupolygonkey_from_intersection_with_WktWgs84('{tile}'))"
        )
        for key, mukey, wkt in sda_query(session, url, query, sleep=sleep):
            polygons[str(key)] = {"mukey": str(mukey), "wkt": wkt}
        print(f"  soils: tile {number}/{len(tiles)}, {len(polygons):,} soil areas", flush=True)
    mukeys = sorted({p["mukey"] for p in polygons.values()})
    units: dict[str, dict[str, Any]] = {}
    for start in range(0, len(mukeys), 300):
        keys = ",".join(f"'{k}'" for k in mukeys[start : start + 300] if k.isdigit())
        if not keys:
            continue
        query = (
            "SELECT M.mukey, M.muname, C.compname, C.comppct_r, C.drainagecl FROM mapunit M "  # noqa: S608 (keys checked: digits only)
            f"LEFT JOIN component C ON C.mukey = M.mukey AND C.majcompflag = 'Yes' WHERE M.mukey IN ({keys})"
        )
        for mukey, muname, compname, pct, drainage in sda_query(session, url, query, sleep=sleep):
            best = units.get(str(mukey))
            pct_value = parse_number(pct) or 0.0
            if best is None or pct_value > best["comppct_r"]:
                units[str(mukey)] = {"muname": muname, "compname": compname, "comppct_r": pct_value, "drainagecl": drainage or None}
    tmp_path = out_path.with_suffix(".part")
    tmp_path.write_text(json.dumps({"polygons": polygons, "units": units}), encoding="utf-8")
    tmp_path.replace(out_path)
    return len(polygons)


def overpass_road_filter(highway_types: list[str]) -> str:
    pattern = "|".join(highway_types)
    return f'["highway"~"^({pattern})$"]["area"!="yes"]["access"!~"^(private|no)$"]'


def overpass_query(osm: dict[str, Any], highway_types: list[str], bbox: dict[str, float] | None = None) -> str:
    """Roads of the included types inside the area, with their node ids (needed to split at intersections).

    The area is an OpenStreetMap area filter (Chicago), a boundary relation inside a larger area (e.g. a city inside a
    state), or, for a boundary given as a GeoJSON file, the box around it (roads outside the shape are removed at load).
    """
    roads = overpass_road_filter(highway_types)
    head = f"[out:json][timeout:{osm['timeout_s']}];\n"
    if osm.get("osm_area_filter"):
        return head + f"area{osm['osm_area_filter']}->.city;\n" + f"way(area.city){roads};\n" + "out body;\n>;\nout skel qt;\n"
    if osm.get("osm_relation_filter"):
        within = f"area{osm['osm_within_filter']}->.within;\nrel(area.within)" if osm.get("osm_within_filter") else "rel"
        return (
            head
            + f"{within}{osm['osm_relation_filter']};\nmap_to_area->.city;\n"
            + f"way(area.city){roads};\n"
            + "out body;\n>;\nout skel qt;\n"
        )
    if bbox is None:
        raise SourceChangedError("The road download needs the area's box; download the boundary first.")
    box = f"{bbox['min_lat']},{bbox['min_lon']},{bbox['max_lat']},{bbox['max_lon']}"
    return head + f"way({box}){roads};\n" + "out body;\n>;\nout skel qt;\n"


def overpass_boundary_query(osm: dict[str, Any]) -> str:
    """The area's boundary relation with the shapes of its member lines (turned into boundary.geojson)."""
    within = f"area{osm['osm_within_filter']}->.within;\nrel(area.within)" if osm.get("osm_within_filter") else "rel"
    return f"[out:json][timeout:{osm['timeout_s']}];\n{within}{osm['osm_relation_filter']};\nout geom;\n"


def boundary_from_overpass(data: dict[str, Any]) -> dict[str, Any]:
    """GeoJSON FeatureCollection with one (Multi)Polygon: the outer rings of the one boundary relation found."""
    from shapely.geometry import LineString, MultiPolygon, mapping
    from shapely.ops import polygonize, unary_union

    relations = [e for e in data.get("elements", []) if e.get("type") == "relation"]
    if len(relations) != 1:
        names = [((r.get("tags") or {}).get("name"), r.get("id")) for r in relations]
        raise SourceChangedError(
            f"Expected one boundary relation, found {len(relations)}: {names}. Make the area's boundary filter stricter."
        )
    relation = relations[0]
    lines = [
        LineString([(p["lon"], p["lat"]) for p in member["geometry"]])
        for member in relation.get("members", [])
        if member.get("type") == "way" and member.get("role", "outer") in ("outer", "") and len(member.get("geometry") or []) >= 2
    ]
    polygons = list(polygonize(unary_union(lines)))
    if not polygons:
        raise SourceChangedError(f"Boundary relation {relation.get('id')} has no closed outer ring.")
    shape = unary_union(polygons)
    if shape.geom_type == "Polygon":
        shape = MultiPolygon([shape])
    tags = relation.get("tags") or {}
    feature = {"type": "Feature", "properties": {"name": tags.get("name"), "osm_relation": relation.get("id")}, "geometry": mapping(shape)}
    return {"type": "FeatureCollection", "features": [feature]}


def boundary_from_geojson(path: Path) -> dict[str, Any]:
    """A boundary given as a GeoJSON file (e.g. a project's survey area): all its polygons as one MultiPolygon."""
    from shapely.geometry import MultiPolygon, mapping, shape
    from shapely.ops import unary_union

    data = json.loads(path.read_text(encoding="utf-8"))
    features = data.get("features", [data] if data.get("type") == "Feature" else [])
    geometries = [shape(f["geometry"]) for f in features if f.get("geometry")]
    if not features and data.get("type") in ("Polygon", "MultiPolygon"):
        geometries = [shape(data)]
    merged = unary_union([g for g in geometries if g.geom_type in ("Polygon", "MultiPolygon")])
    if merged.is_empty:
        raise SourceChangedError(f"{path} has no polygon.")
    if merged.geom_type == "Polygon":
        merged = MultiPolygon([merged])
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"file": path.name}, "geometry": mapping(merged)}]}


def count_csv_rows(path: Path) -> int:
    with path.open(encoding="utf-8", newline="") as handle:
        return max(sum(1 for _ in csv.reader(handle)) - 1, 0)


def plan_downloads(src: dict[str, Any], rules: dict[str, Any]) -> list[dict[str, Any]]:
    """Every raw file the area needs, as a list of jobs (kept as data so the tests can check it without a network).

    `portal: True` marks files from a city's open data site: they are fetched only after the owner confirms its terms.
    """
    portal = src.get("portal")
    jobs: list[dict[str, Any]] = []
    boundary = src.get("boundary", {})
    if "districts" not in src:  # the area's outline, needed to keep only roads inside it and to find its box
        if boundary.get("geojson_file"):
            jobs.append({"name": "boundary", "file": "boundary.geojson", "kind": "geojson_boundary", "portal": False,
                         "url": str(boundary["geojson_file"]), "licence": "given by the owner"})  # fmt: skip
        else:
            jobs.append(
                {
                    "name": "boundary",
                    "file": "osm_boundary.json",
                    "kind": "osm_boundary",
                    "portal": False,
                    "url": src["osm"]["overpass_url"],
                    "query": overpass_boundary_query(src["osm"]),
                    "licence": src["osm"]["licence"],
                }
            )
    for key in ("potholes_historical", "potholes_current"):
        if key not in src:
            continue
        item = src[key]
        jobs.append(
            {
                "name": key,
                "file": f"{key}.csv",
                "kind": "socrata",
                "portal": True,
                "dataset_id": item["dataset_id"],
                "select": item["select"],
                "where": item["where"],
                "url": f"{portal['base_url']}/resource/{item['dataset_id']}.csv",
                "licence": portal["licence"],
            }
        )
    if "districts" in src:
        jobs.append(
            {
                "name": "community_areas",
                "file": "community_areas.geojson",
                "kind": "file",
                "portal": True,
                "url": f"{portal['base_url']}/resource/{src['districts']['dataset_id']}.geojson?$limit=1000",
                "licence": portal["licence"],
            }
        )
    weather = src["weather"]
    stations = weather["stations"] if isinstance(weather["stations"], list) else []
    for station in stations:
        jobs.append(
            {
                "name": f"weather_{station['id']}",
                "file": f"weather_{station['id']}.csv",
                "kind": "file",
                "portal": False,
                "url": weather["url_template"].format(station=station["id"]),
                "licence": weather["licence"],
            }
        )
    osm = src["osm"]
    needs_box = not (osm.get("osm_area_filter") or osm.get("osm_relation_filter"))
    jobs.append(
        {
            "name": "osm_roads",
            "file": "osm_roads.json",
            "kind": "overpass",
            "portal": False,
            "url": osm["overpass_url"],
            "query": None if needs_box else overpass_query(osm, rules["sections"]["include_highway_types"]),
            "licence": osm["licence"],
        }
    )
    # F1b static layers (each optional: a failed layer is reported and left out, the rest still load)
    if "elevation" in src:
        jobs.append(
            {
                "name": "elevation",
                "file": "elevation_samples.csv",
                "kind": "elevation",
                "portal": False,
                "url": src["elevation"]["url"],
                "licence": src["elevation"]["licence"],
            }
        )
    if "flood_zones" in src:
        jobs.append(
            {
                "name": "flood_zones",
                "file": "flood_zones.geojson",
                "kind": "arcgis_tiled",
                "portal": False,
                "url": src["flood_zones"]["layer_url"],
                "licence": src["flood_zones"]["licence"],
            }
        )
    for key in ("traffic_counts",):
        if key in src:
            jobs.append(
                {
                    "name": key,
                    "file": f"{key}.geojson",
                    "kind": "arcgis",
                    "config": key,
                    "portal": False,
                    "url": src[key]["base_url"],
                    "licence": src[key]["licence"],
                }
            )
    if "soils" in src:
        jobs.append(
            {
                "name": "soils",
                "file": "soils.json",
                "kind": "soils",
                "portal": False,
                "url": src["soils"]["url"],
                "licence": src["soils"]["licence"],
            }
        )
    if "bus_routes" in src:
        jobs.append(
            {
                "name": "bus_routes",
                "file": "bus_routes.geojson",
                "kind": "file",
                "portal": True,
                "url": f"{portal['base_url']}/resource/{src['bus_routes']['dataset_id']}.geojson?$limit=5000",
                "licence": portal["licence"],
            }
        )
    pci = src.get("cook_county_pci")
    if pci:
        jobs.append(
            {
                "name": "cook_county_pci",
                "file": "cook_county_pci.geojson",
                "kind": "arcgis",
                "config": "cook_county_pci",
                "portal": False,
                "url": pci["base_url"],
                "licence": pci["licence"],
            }
        )
    return jobs


def read_manifest(raw_dir: Path) -> dict[str, Any]:
    path = raw_dir / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_manifest(raw_dir: Path, manifest: dict[str, Any]) -> None:
    (raw_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


BBOX_KINDS = {"arcgis_tiled", "soils", "elevation"}  # need the area's box (or map zone) before they can run


def with_area_box(src: dict[str, Any], raw_dir: Path) -> dict[str, Any]:
    """Fill in the area's box and map zone from the downloaded boundary when the area file does not give them."""
    if "bbox" in src and "projected_crs" in src:
        return src
    path = raw_dir / "boundary.geojson"
    if not path.exists():
        raise SourceChangedError("This needs the area's boundary first (download item 'boundary').")
    from shapely.geometry import shape

    from forecasting.areas import resolve_after_boundary

    return resolve_after_boundary(src, shape(json.loads(path.read_text(encoding="utf-8"))["features"][0]["geometry"]).bounds)


def run_job(
    session: requests.Session,
    job: dict[str, Any],
    out_path: Path,
    src: dict[str, Any],
    sleep=time.sleep,
    rules: dict[str, Any] | None = None,
) -> int | None:
    if job["kind"] == "socrata":
        portal = src["portal"]
        return download_socrata_csv(
            session,
            base_url=portal["base_url"],
            dataset_id=job["dataset_id"],
            select=job["select"],
            where=job["where"],
            page_size=portal["page_size"],
            out_path=out_path,
            app_token=os.environ.get(portal["app_token_env"]) or None,
            sleep=sleep,
        )
    if job["kind"] == "geojson_boundary":
        given = Path(job["url"])
        if not given.is_absolute():
            from forecasting.areas import AREAS_DIR

            given = AREAS_DIR / given
        if not given.exists():
            raise SourceChangedError(f"Boundary file {given} not found.")
        tmp_path = out_path.with_suffix(".part")
        tmp_path.write_text(json.dumps(boundary_from_geojson(given)), encoding="utf-8")
        tmp_path.replace(out_path)
        return 1
    if job["kind"] == "osm_boundary":
        download_file(session, job["url"], out_path, method="POST", data={"data": job["query"]}, timeout=600, sleep=sleep)
        geojson = boundary_from_overpass(json.loads(out_path.read_text(encoding="utf-8")))
        (out_path.parent / "boundary.geojson").write_text(json.dumps(geojson), encoding="utf-8")
        return 1
    if job["kind"] in BBOX_KINDS or (job["kind"] == "arcgis" and src.get(job["config"], {}).get("limit_to_area_box")):
        src = with_area_box(src, out_path.parent)
    if job["kind"] == "arcgis":
        cfg = src[job["config"]]
        return download_arcgis_layers(
            session,
            base_url=cfg["base_url"],
            layers={int(k): v for k, v in cfg["layers"].items()},
            out_fields=cfg["out_fields"],
            page_size=cfg["page_size"],
            out_path=out_path,
            tag_field=cfg.get("tag_field", "township"),
            extra_params=bbox_envelope(src["bbox"]) if cfg.get("limit_to_area_box") else None,
            sleep=sleep,
        )
    if job["kind"] == "arcgis_tiled":
        cfg = src["flood_zones"]
        return download_arcgis_tiled(
            session,
            layer_url=cfg["layer_url"],
            where=cfg["where"],
            out_fields=cfg["out_fields"],
            bbox=src["bbox"],
            tile_deg=cfg["tile_deg"],
            max_offset_deg=cfg["max_allowable_offset_deg"],
            out_path=out_path,
            sleep=sleep,
        )
    if job["kind"] == "elevation":
        from forecasting.sections import sample_points, sections_from_file  # needs the road download

        osm = out_path.parent / "osm_roads.json"
        if not osm.exists():
            raise SourceChangedError("Elevation needs osm_roads.json first; download it (it comes earlier in the list).")
        sections, _, _ = sections_from_file(osm, crs=src["projected_crs"])
        points = [point for section in sections for point in sample_points(section, src["projected_crs"])]
        cfg = src["elevation"]
        return download_elevation_samples(
            session, url=cfg["url"], points=points, batch_size=cfg["batch_size"], out_path=out_path, sleep=sleep
        )
    if job["kind"] == "soils":
        cfg = src["soils"]
        return download_sda_soils(session, url=cfg["url"], bbox=src["bbox"], tile_deg=cfg["tile_deg"], out_path=out_path, sleep=sleep)
    if job["kind"] == "overpass":
        query = job["query"]
        if query is None:  # a GeoJSON boundary: roads in its box (those outside the shape are removed at load)
            src = with_area_box(src, out_path.parent)
            query = overpass_query(src["osm"], (rules or {})["sections"]["include_highway_types"], src["bbox"])
            job["query"] = query
        download_file(session, job["url"], out_path, method="POST", data={"data": query}, timeout=1200, sleep=sleep)
        return None
    download_file(session, job["url"], out_path, sleep=sleep)
    return count_csv_rows(out_path) if out_path.suffix == ".csv" else None


def download_all(
    raw_dir: Path,
    src: dict[str, Any],
    rules: dict[str, Any],
    *,
    terms_confirmed: bool,
    only: str | None = None,
    force: bool = False,
    session: requests.Session | None = None,
    sleep=time.sleep,
) -> dict[str, Any]:
    """Download every raw file of one area into raw_dir. `terms_confirmed`: the owner read the city portal's terms."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest(raw_dir)
    if src["weather"]["stations"] == "auto":
        raise SystemExit(
            f"Weather stations for {src.get('area_name', 'this area')} are chosen by the area check. "
            f"Run `python -m forecasting.run --area {src.get('area_key', '...')} area-check` first."
        )
    jobs = [job for job in plan_downloads(src, rules) if only in (None, job["name"])]
    if only and not jobs:
        raise SystemExit(f"Unknown download '{only}'. Choose from: {', '.join(j['name'] for j in plan_downloads(src, rules))}")
    if any(job["portal"] for job in jobs) and not terms_confirmed:
        raise SystemExit(
            f"{src.get('area_name', 'City')} data: read the open data portal's Terms of Use first:\n"
            f"  {src['portal']['terms_url']}\n"
            "If you accept them, run again with --terms-confirmed (recorded in the manifest)."
        )
    session = session or new_session()
    failed: list[str] = []
    for job in jobs:
        out_path = raw_dir / job["file"]
        if not force and out_path.exists() and job["name"] in manifest:
            print(f"- {job['name']}: already downloaded, skipped (use --force to download again)")
            continue
        print(f"- {job['name']}: downloading from {job['url']}", flush=True)
        try:
            rows = run_job(session, job, out_path, src, sleep=sleep, rules=rules)
        except (RuntimeError, ValueError, OSError) as error:  # SourceChangedError is a RuntimeError
            print(f"  FAILED: {job['name']}: {error}", flush=True)
            failed.append(job["name"])
            continue
        now = datetime.now(UTC_TZ).isoformat(timespec="seconds")
        manifest[job["name"]] = {
            "file": job["file"],
            "url": job["url"],
            "query": job.get("where") or job.get("query"),
            "columns": job.get("select"),
            "licence": job["licence"],
            "downloaded_at": now,
            "bytes": out_path.stat().st_size,
            "sha256": sha256_file(out_path),
            "rows": rows,
            **({"portal_terms_confirmed_at": now} if job["portal"] else {}),
        }
        write_manifest(raw_dir, manifest)
    if failed:
        print(
            f"These downloads failed: {', '.join(failed)}. Everything else is saved. "
            "Run again later (finished files are skipped), or send the messages above to Claude.",
            flush=True,
        )
        raise SystemExit(PARTIAL_DOWNLOAD_EXIT_CODE)
    return manifest
