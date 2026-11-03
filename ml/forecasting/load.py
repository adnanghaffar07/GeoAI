"""F1 step 3: load one area's raw downloads into its schema of the separate `forecast` PostGIS database.

The whole load runs in one transaction and replaces the previous load of that area (these tables only hold data
derived from the raw files, which stay untouched in data/<area>/raw/). Nothing here reads or writes the app database.
Each area has its own schema (owner decision D1); the table names are the same in every schema.
Missing or unusable values are kept as missing and counted; no location or weather value is ever guessed.
"""

from __future__ import annotations

import csv
import json
import random
from collections import Counter
from collections.abc import Iterable, Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

from forecasting import static
from forecasting.sections import CHICAGO_CRS, Section, sections_from_file

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS postgis SCHEMA public;

-- Chicago: the 77 community areas. An area without districts: one row, its whole boundary (number 0).
CREATE TABLE IF NOT EXISTS community_areas (
    area_number integer PRIMARY KEY,
    name text NOT NULL,
    held_out boolean NOT NULL DEFAULT false,          -- F0 section 5 place check: never used in training
    geom geometry(MultiPolygon, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS road_sections (
    section_id text PRIMARY KEY,                      -- "<osm way>-<piece>-<cut>", stable for one OSM extract
    osm_way_id bigint NOT NULL,
    highway text NOT NULL,
    name text,
    lanes text,
    surface text,
    length_m double precision NOT NULL CHECK (length_m > 0),
    community_area integer REFERENCES community_areas (area_number),
    geom geometry(LineString, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS road_sections_geog_idx ON road_sections USING gist ((geom::geography));
CREATE INDEX IF NOT EXISTS road_sections_area_idx ON road_sections (community_area);

CREATE TABLE IF NOT EXISTS pothole_reports (
    source text NOT NULL,                             -- potholes_historical (old 311) or potholes_current (new 311)
    request_id text NOT NULL,
    created_at timestamp NOT NULL,                    -- Chicago local time, as published
    is_duplicate boolean NOT NULL,
    status text,
    latitude double precision,
    longitude double precision,
    location_issue text,                              -- NULL = usable; 'missing' or 'outside_<area>' otherwise
    community_area integer,
    geom geometry(Point, 4326),
    PRIMARY KEY (source, request_id)
);
CREATE INDEX IF NOT EXISTS pothole_reports_geog_idx ON pothole_reports USING gist ((geom::geography));
CREATE INDEX IF NOT EXISTS pothole_reports_created_idx ON pothole_reports (created_at);

CREATE TABLE IF NOT EXISTS weather_stations (
    station_id text PRIMARY KEY,
    name text NOT NULL,
    geom geometry(Point, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS weather_daily (
    station_id text NOT NULL REFERENCES weather_stations (station_id),
    date date NOT NULL,
    tmax_c real,
    tmin_c real,
    prcp_mm real,
    snow_mm real,
    snwd_mm real,
    PRIMARY KEY (station_id, date)
);

-- Cook County DOTH pavement condition, 2025 survey, six suburban townships. CHECKING ONLY (no licence stated yet).
CREATE TABLE IF NOT EXISTS pavement_condition_cook (
    township text NOT NULL,
    object_id bigint NOT NULL,
    street text,
    city_left text,
    city_right text,
    line_miles double precision,
    pci double precision CHECK (pci BETWEEN 0 AND 100),   -- NULL when missing or outside 0-100 (counted)
    survey_year integer NOT NULL,
    geom geometry(MultiLineString, 4326) NOT NULL,
    PRIMARY KEY (township, object_id)
);
CREATE INDEX IF NOT EXISTS pavement_condition_cook_geog_idx ON pavement_condition_cook USING gist ((geom::geography));

CREATE TABLE IF NOT EXISTS load_log (
    id bigserial PRIMARY KEY,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    osm_extract_date text,
    details jsonb NOT NULL
);
"""

TABLES_IN_LOAD_ORDER = [
    "community_areas",
    "road_sections",
    "pothole_reports",
    "weather_stations",
    "weather_daily",
    "pavement_condition_cook",
    *static.TABLES,
]


# ---------- database ----------


def ensure_schema(conn: psycopg.Connection, schema: str) -> None:
    """Create the area's schema (its own set of tables) if it does not exist yet."""
    conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))


def ensure_database(url: str) -> None:
    """Create the forecast database (and PostGIS in it) if it does not exist yet."""
    params = psycopg.conninfo.conninfo_to_dict(url)
    name = params.get("dbname")
    if not name:
        raise SystemExit("FORECAST_DATABASE_URL must end with a database name, e.g. .../forecast")
    admin = psycopg.conninfo.make_conninfo(url, dbname="postgres")
    from forecasting.settings import connect

    with connect(admin, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            print(f"Created database '{name}'.")


def create_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA)
    conn.execute(static.SCHEMA)


def copy_rows(conn: psycopg.Connection, table: str, columns: list[str], rows: Iterable[tuple]) -> None:
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, columns)))
    with conn.cursor().copy(statement) as copy:
        for row in rows:
            copy.write_row(row)


# ---------- parsing (pure functions, tested without a database) ----------


def parse_portal_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None


def parse_float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def location_issue(lat: float | None, lon: float | None, bbox: dict[str, float], outside: str = "outside_chicago") -> str | None:
    if lat is None or lon is None:
        return "missing"
    if not (bbox["min_lat"] <= lat <= bbox["max_lat"] and bbox["min_lon"] <= lon <= bbox["max_lon"]):
        return outside
    return None


def parse_pothole_csv(
    path: Path, source: str, cfg: dict[str, Any], bbox: dict[str, float], stats: Counter, outside: str = "outside_chicago"
) -> Iterator[tuple]:
    """Yield pothole_reports rows. Historical rows mark duplicates in STATUS; current rows have a DUPLICATE flag."""
    historical = source == "potholes_historical"
    id_field, date_field = ("service_request_number", "creation_date") if historical else ("sr_number", "created_date")
    seen: set[str] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            stats[f"{source}.rows"] += 1
            request_id = (record.get(id_field) or "").strip()
            created = parse_portal_time(record.get(date_field) or "")
            if not request_id or created is None:
                stats[f"{source}.skipped_no_id_or_date"] += 1
                continue
            if request_id in seen:
                stats[f"{source}.skipped_repeated_id"] += 1
                continue
            seen.add(request_id)
            status = (record.get("status") or "").strip() or None
            if historical:
                is_duplicate = status in cfg["duplicate_statuses"]
            else:
                is_duplicate = (record.get("duplicate") or "").strip().lower() == "true"
                if (record.get("legacy_record") or "").strip().lower() == "true":
                    stats[f"{source}.legacy_records"] += 1
            lat, lon = parse_float(record.get("latitude")), parse_float(record.get("longitude"))
            issue = location_issue(lat, lon, bbox, outside)
            if issue:
                stats[f"{source}.location_{issue}"] += 1
            if is_duplicate:
                stats[f"{source}.duplicates"] += 1
            stats[f"{source}.loaded"] += 1
            yield (source, request_id, created, is_duplicate, status, lat, lon, issue)


def ghcn_value(value: str | None, attributes: str | None, scale: float) -> tuple[float | None, bool]:
    """Return (value in normal units, rejected_by_quality_flag). GHCN 'access' files store tenths of °C and of mm."""
    if value is None or value.strip() == "":
        return None, False
    parts = (attributes or "").split(",")
    if len(parts) > 1 and parts[1].strip():
        return None, True
    return float(value) * scale, False


GHCN_ELEMENTS = {"TMAX": 0.1, "TMIN": 0.1, "PRCP": 0.1, "SNOW": 1.0, "SNWD": 1.0}


def parse_ghcn_csv(path: Path, station_id: str, start: date, stats: Counter) -> Iterator[tuple]:
    with path.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            day = date.fromisoformat(record["DATE"].strip())
            if day < start:
                continue
            values = []
            for element, scale in GHCN_ELEMENTS.items():
                value, rejected = ghcn_value(record.get(element), record.get(f"{element}_ATTRIBUTES"), scale)
                if rejected:
                    stats[f"{station_id}.{element}.rejected_quality_flag"] += 1
                elif value is None:
                    stats[f"{station_id}.{element}.missing"] += 1
                values.append(value)
            stats[f"{station_id}.days"] += 1
            yield (station_id, day, *values)


def check_temperature_units(rows: list[tuple]) -> None:
    """Stop if temperatures do not look like °C (protects against a change of units in the NOAA files)."""
    tmax = sorted(row[2] for row in rows if row[2] is not None)
    if len(tmax) < 100:
        return
    low, high = tmax[len(tmax) // 100], tmax[-len(tmax) // 100 - 1]
    if not (-35 <= low <= 45 and -35 <= high <= 45):
        raise ValueError(f"Daily max temperatures run from {low} to {high}: not degrees C. Check the NOAA file units.")


def community_area_rows(geojson: dict[str, Any], cfg: dict[str, Any]) -> list[tuple[int, str, str]]:
    rows = []
    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        number = next((props[k] for k in cfg["number_fields"] if props.get(k) not in (None, "")), None)
        name = next((props[k] for k in cfg["name_fields"] if props.get(k)), None)
        if number is None or name is None or not feature.get("geometry"):
            raise ValueError(f"Community area without number, name or shape: {sorted(props)}. Update config/sources.yaml.")
        rows.append((int(float(number)), str(name).title(), json.dumps(feature["geometry"])))
    expected = cfg.get("expected_count")
    if expected is not None and len(rows) != int(expected):
        raise ValueError(f"Expected {expected} districts (Chicago: community areas), got {len(rows)}.")
    return rows


def boundary_row(raw_dir: Path, name: str) -> tuple[int, str, str]:
    """An area without districts: one row (number 0) holding its whole boundary from boundary.geojson."""
    data = json.loads(require(raw_dir, "boundary.geojson").read_text(encoding="utf-8"))
    return (0, name, json.dumps(data["features"][0]["geometry"]))


def pci_rows(geojson: dict[str, Any], survey_year: int, stats: Counter) -> list[tuple]:
    """Rows for pavement_condition_cook. A PCI outside 0-100 is kept as missing (never corrected); pieces without a shape are skipped."""
    rows = []
    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        stats["cook_pci.rows"] += 1
        if not feature.get("geometry") or props.get("OBJECTID") is None:
            stats["cook_pci.skipped_no_shape_or_id"] += 1
            continue
        pci = props.get("PCIsegment")
        if pci is None:
            stats["cook_pci.pci_missing"] += 1
        elif not 0 <= pci <= 100:
            stats["cook_pci.pci_out_of_range"] += 1
            pci = None
        rows.append(
            (
                props["township"],
                int(props["OBJECTID"]),
                props.get("FULLSTNA"),
                props.get("LCITY"),
                props.get("RCITY"),
                props.get("LineMiles"),
                pci,
                survey_year,
                json.dumps(feature["geometry"]),
            )
        )
        stats["cook_pci.loaded"] += 1
    return rows


def choose_held_out_areas(area_numbers: Iterable[int], count: int, seed: int) -> list[int]:
    """F0 section 5: a fixed random choice, the same on every computer and every run."""
    return sorted(random.Random(seed).sample(sorted(area_numbers), count))  # noqa: S311 (not for security)


# ---------- loading ----------


def say(part: str) -> None:
    """A progress line with the time, so a long load never looks frozen."""
    print(f"    {datetime.now().strftime('%H:%M')} loading: {part}", flush=True)


def require(raw_dir: Path, name: str) -> Path:
    path = raw_dir / name
    if not path.exists():
        raise SystemExit(f"Missing {path}. Run `python -m forecasting.run download` first.")
    return path


def load_all(conn: psycopg.Connection, raw_dir: Path, src: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    stats: Counter = Counter()
    create_schema(conn)
    conn.execute(sql.SQL("TRUNCATE {} CASCADE").format(sql.SQL(", ").join(map(sql.Identifier, TABLES_IN_LOAD_ORDER))))

    say("districts / boundary")
    # Districts (Chicago: community areas) and the held-out place check; else the area's boundary as one row
    districts = src.get("districts")
    if districts:
        areas = community_area_rows(json.loads(require(raw_dir, "community_areas.geojson").read_text(encoding="utf-8")), districts)
    else:
        areas = [boundary_row(raw_dir, src.get("area_name", "area"))]
    if districts and districts.get("held_out") == "f0":
        held = rules["periods"]["held_out_community_areas"]
        held_out = choose_held_out_areas([a[0] for a in areas], held["count"], held["seed"])
    else:
        held_out = []  # held-out places only matter for a tested forecast (Level 2); new cities get their own rule (D4)
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO community_areas (area_number, name, held_out, geom) "
            "VALUES (%s, %s, %s, ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), 3)))",
            [(number, name, number in held_out, geometry) for number, name, geometry in areas],
        )

    say("road sections")
    # Road sections, kept only when their middle point is inside a district (the city) or the boundary
    sec = rules["sections"]
    crs = src.get("projected_crs", CHICAGO_CRS)
    sections, section_stats, extract_date = sections_from_file(
        require(raw_dir, "osm_roads.json"), sec["length_m"], sec["min_end_piece_m"], crs
    )
    copy_rows(
        conn,
        "road_sections",
        ["section_id", "osm_way_id", "highway", "name", "lanes", "surface", "length_m", "geom"],
        section_rows(sections),
    )
    conn.execute(
        "UPDATE road_sections s SET community_area = a.area_number FROM community_areas a "
        "WHERE ST_Intersects(a.geom, ST_LineInterpolatePoint(s.geom, 0.5))"
    )
    removed = conn.execute("DELETE FROM road_sections WHERE community_area IS NULL").rowcount

    say("311 pothole reports (the biggest part)")
    # 311 pothole reports (only areas with history)
    outside = f"outside_{src.get('area_key', 'chicago')}"
    for source in ("potholes_historical", "potholes_current"):
        if source not in src:
            continue
        rows = parse_pothole_csv(require(raw_dir, f"{source}.csv"), source, src[source], src["bbox"], stats, outside)
        copy_rows(
            conn,
            "pothole_reports",
            ["source", "request_id", "created_at", "is_duplicate", "status", "latitude", "longitude", "location_issue"],
            rows,
        )
    conn.execute("UPDATE pothole_reports SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) WHERE location_issue IS NULL")
    conn.execute(
        "UPDATE pothole_reports p SET community_area = a.area_number FROM community_areas a "
        "WHERE p.geom IS NOT NULL AND ST_Intersects(a.geom, p.geom)"
    )

    say("weather")
    # Weather
    weather = src["weather"]
    if not isinstance(weather["stations"], list):
        raise SystemExit("Weather stations are not chosen yet: run `forecasting.run --area <area> area-check` first.")
    start = date.fromisoformat(str(weather["start_date"]))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO weather_stations (station_id, name, geom) VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))",
            [(s["id"], s["name"], s["lon"], s["lat"]) for s in weather["stations"]],
        )
    for station in weather["stations"]:
        rows = list(parse_ghcn_csv(require(raw_dir, f"weather_{station['id']}.csv"), station["id"], start, stats))
        check_temperature_units(rows)
        copy_rows(conn, "weather_daily", ["station_id", "date", "tmax_c", "tmin_c", "prcp_mm", "snow_mm", "snwd_mm"], rows)

    # Cook County pavement condition (checking only; optional so older raw folders still load)
    pci_cfg = src.get("cook_county_pci")
    pci_path = raw_dir / "cook_county_pci.geojson"
    if pci_cfg and pci_path.exists():
        rows = pci_rows(json.loads(pci_path.read_text(encoding="utf-8")), int(pci_cfg["survey_year"]), stats)
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO pavement_condition_cook "
                "(township, object_id, street, city_left, city_right, line_miles, pci, survey_year, geom) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, ST_Multi(ST_Force2D(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))) "
                "ON CONFLICT (township, object_id) DO NOTHING",
                rows,
            )
    elif pci_cfg:
        print("Note: cook_county_pci.geojson not downloaded yet; run the download again to add it.")

    say("static layers: elevation, low spots, flood, soil, traffic, bus routes (a few minutes)")
    # F1b static layers (slope, flood, soil, traffic, bus routes); each optional
    static_used = static.load_static(conn, raw_dir, src, sections, stats)

    details = {
        "static_layers": static_used,
        "sections": {
            "osm_ways": section_stats.ways,
            "ways_missing_nodes": section_stats.ways_missing_nodes,
            "pieces_between_intersections": section_stats.pieces_between_intersections,
            "pieces_shorter_than_min": section_stats.pieces_too_short,
            "pieces_shorter_than_min_km": round(section_stats.too_short_length_m / 1000, 1),
            "sections_built": section_stats.sections,
            "sections_outside_city_removed": removed,
        },
        "held_out_community_areas": held_out,
        "counts": dict(sorted(stats.items())),
    }
    conn.execute("INSERT INTO load_log (osm_extract_date, details) VALUES (%s, %s)", (extract_date, json.dumps(details)))
    return details


def section_rows(sections: list[Section]) -> Iterator[tuple]:
    for s in sections:
        yield (s.section_id, s.osm_way_id, s.highway, s.name, s.lanes, s.surface, s.length_m, s.ewkt())


def run_load(url: str, raw_dir: Path, src: dict[str, Any], rules: dict[str, Any], schema: str | None = None) -> dict[str, Any]:
    """Load into the area's schema (src["schema"] unless given). One transaction: all tables load, or none change."""
    from forecasting.settings import connect

    ensure_database(url)
    schema = schema or src.get("schema")
    with connect(url, schema) as conn:
        if schema:
            ensure_schema(conn, schema)
        details = load_all(conn, raw_dir, src, rules)
    return details
