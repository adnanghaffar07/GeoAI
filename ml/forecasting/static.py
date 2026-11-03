"""F1b: static facts about each road section (F0 section 4: allowed inputs; their dates are recorded).

One row per section in `section_static`: slope and low spot (USGS elevation), flood zone (FEMA), soil drainage (USDA),
traffic and heavy vehicles (state counts, e.g. IDOT), bus routes (city data, e.g. CTA). Each layer is optional: when
its raw file is missing the columns stay empty (missing, never guessed) and the report says so.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

from forecasting.download import parse_number, point_key
from forecasting.sections import CHICAGO_CRS, Section, sample_points

SCHEMA = """
CREATE TABLE IF NOT EXISTS section_static (
    section_id text PRIMARY KEY REFERENCES road_sections (section_id) ON DELETE CASCADE,
    elev_start_m real,
    elev_mid_m real,
    elev_end_m real,
    slope_pct real,                 -- height difference start-end / length * 100
    low_spot_m real,                -- middle height minus average middle height of sections within 200 m (negative = dip)
    flood_1pct boolean,             -- touches a FEMA 1% annual-chance flood zone (SFHA)
    flood_02pct boolean,            -- touches a FEMA 0.2% annual-chance zone
    soil_drainage text,             -- drainage class of the main soil under the section middle
    soil_drainage_rank smallint,    -- 1 excessively drained ... 7 very poorly drained
    soil_urban_land boolean,        -- soil mapped as "Urban land"
    aadt integer,                   -- vehicles per day (IDOT count on the same road, within 15 m, same direction)
    aadt_year integer,
    hcv_aadt integer,               -- heavy commercial vehicles per day
    hcv_year integer,
    bus_routes smallint             -- number of bus routes on the section (NULL = no bus data for the area)
);

CREATE TABLE IF NOT EXISTS flood_zones (
    id bigserial PRIMARY KEY,
    fld_zone text,
    zone_subty text,
    sfha_tf text,
    geom geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS flood_zones_geom_idx ON flood_zones USING gist (geom);

CREATE TABLE IF NOT EXISTS soil_units (
    id bigserial PRIMARY KEY,
    mukey text NOT NULL,
    muname text,
    compname text,
    drainagecl text,
    geom geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS soil_units_geom_idx ON soil_units USING gist (geom);

CREATE TABLE IF NOT EXISTS traffic_counts (
    id bigserial PRIMARY KEY,
    road_name text,
    aadt integer,
    aadt_year integer,
    hcv_aadt integer,
    hcv_year integer,
    geom geometry(LineString, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS traffic_counts_geog_idx ON traffic_counts USING gist ((geom::geography));

CREATE TABLE IF NOT EXISTS bus_routes (
    id bigserial PRIMARY KEY,
    route text NOT NULL,
    name text,
    geom geometry(LineString, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS bus_routes_geog_idx ON bus_routes USING gist ((geom::geography));
"""

TABLES = ["section_static", "flood_zones", "soil_units", "traffic_counts", "bus_routes"]

DRAINAGE_RANK = {
    "excessively drained": 1,
    "somewhat excessively drained": 2,
    "well drained": 3,
    "moderately well drained": 4,
    "somewhat poorly drained": 5,
    "poorly drained": 6,
    "very poorly drained": 7,
}

# Lines (traffic counts, bus routes) that belong to a section: within DIST m of its middle, running the same way (ANGLE°).
MATCH_SQL = """
SELECT m.section_id, {columns}, ST_Distance(l.geom::geography, m.mid::geography) AS distance_m
FROM sec_mid m
JOIN {table} l ON ST_DWithin(l.geom::geography, m.mid::geography, %(dist)s)
CROSS JOIN LATERAL (
    SELECT ST_LineLocatePoint(l.geom, m.mid) AS f,
           least(10 / nullif(ST_Length(l.geom::geography), 0), 0.5) AS half
) p
CROSS JOIN LATERAL (
    SELECT degrees(ST_Azimuth(ST_LineInterpolatePoint(l.geom, greatest(p.f - p.half, 0)),
                              ST_LineInterpolatePoint(l.geom, least(p.f + p.half, 1)))) AS az
) a
WHERE m.az IS NOT NULL AND a.az IS NOT NULL
  AND least(mod(abs(m.az - a.az)::numeric, 180), 180 - mod(abs(m.az - a.az)::numeric, 180)) <= %(angle)s
"""


def elevation_values(path: Path) -> dict[str, float]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["key"]: value for row in csv.DictReader(handle) if (value := parse_number(row["elevation_m"])) is not None}


def elevation_rows(sections: list[Section], heights: dict[str, float], kept: set[str], crs: str = CHICAGO_CRS) -> list[tuple]:
    rows = []
    for section in sections:
        if section.section_id not in kept:
            continue
        start, mid, end = (heights.get(point_key(*p)) for p in sample_points(section, crs))
        slope = abs(end - start) / section.length_m * 100 if start is not None and end is not None else None
        rows.append((section.section_id, start, mid, end, slope))
    return rows


def drainage_rank(drainage: str | None) -> int | None:
    return DRAINAGE_RANK.get((drainage or "").strip().lower())


def soil_rows(data: dict[str, Any]) -> list[tuple]:
    units = data.get("units", {})
    rows = []
    for polygon in data.get("polygons", {}).values():
        unit = units.get(polygon["mukey"], {})
        rows.append((polygon["mukey"], unit.get("muname"), unit.get("compname"), unit.get("drainagecl"), polygon["wkt"]))
    return rows


def first_value(props: dict[str, Any], names: list[str]) -> Any:
    return next((props[n] for n in names if props.get(n) not in (None, "")), None)


def load_static(conn: psycopg.Connection, raw_dir: Path, src: dict[str, Any], sections: list[Section], stats: Counter) -> dict[str, Any]:
    conn.execute(SCHEMA)
    conn.execute("INSERT INTO section_static (section_id) SELECT section_id FROM road_sections")
    kept = {row[0] for row in conn.execute("SELECT section_id FROM road_sections")}
    match = src.get("matching", {"distance_m": 15, "max_angle_deg": 20})
    used: dict[str, Any] = {}

    # Elevation, slope and low spot
    path = raw_dir / "elevation_samples.csv"
    if path.exists():
        rows = elevation_rows(sections, elevation_values(path), kept, src.get("projected_crs", CHICAGO_CRS))
        conn.execute("CREATE TEMP TABLE tmp_elev (section_id text, s real, m real, e real, slope real) ON COMMIT DROP")
        with conn.cursor().copy("COPY tmp_elev FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)
        conn.execute(
            "UPDATE section_static t SET elev_start_m = e.s, elev_mid_m = e.m, elev_end_m = e.e, slope_pct = e.slope "
            "FROM tmp_elev e WHERE e.section_id = t.section_id"
        )
        conn.execute(
            "CREATE TEMP TABLE tmp_mid ON COMMIT DROP AS SELECT s.section_id, t.elev_mid_m AS h, "
            "ST_LineInterpolatePoint(s.geom, 0.5)::geography AS g FROM road_sections s JOIN section_static t USING (section_id) "
            "WHERE t.elev_mid_m IS NOT NULL"
        )
        conn.execute("CREATE INDEX ON tmp_mid USING gist (g)")
        conn.execute(
            "UPDATE section_static t SET low_spot_m = n.low FROM ("
            " SELECT a.section_id, a.h - avg(b.h) AS low FROM tmp_mid a JOIN tmp_mid b"
            " ON ST_DWithin(a.g, b.g, 200) AND a.section_id <> b.section_id GROUP BY a.section_id, a.h) n "
            "WHERE n.section_id = t.section_id"
        )
        used["elevation"] = True

    # Flood zones (FEMA)
    path = raw_dir / "flood_zones.geojson"
    if path.exists():
        features = json.loads(path.read_text(encoding="utf-8")).get("features", [])
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO flood_zones (fld_zone, zone_subty, sfha_tf, geom) VALUES (%s, %s, %s, "
                "ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), 3)))",
                [
                    (
                        f["properties"].get("FLD_ZONE"),
                        f["properties"].get("ZONE_SUBTY"),
                        f["properties"].get("SFHA_TF"),
                        json.dumps(f["geometry"]),
                    )
                    for f in features
                    if f.get("geometry")
                ],
            )
        conn.execute("DELETE FROM flood_zones WHERE ST_IsEmpty(geom)")
        stats["flood_zones.polygons"] = len(features)
        conn.execute(
            "UPDATE section_static t SET "
            "flood_1pct = EXISTS (SELECT 1 FROM flood_zones z WHERE z.sfha_tf = 'T' AND ST_Intersects(z.geom, s.geom)), "
            "flood_02pct = EXISTS (SELECT 1 FROM flood_zones z WHERE z.zone_subty ILIKE '%0.2 PCT%' AND ST_Intersects(z.geom, s.geom)) "
            "FROM road_sections s WHERE s.section_id = t.section_id"
        )
        used["flood"] = True

    # Soil (USDA), kept only if enough sections get a drainage class
    path = raw_dir / "soils.json"
    if path.exists():
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO soil_units (mukey, muname, compname, drainagecl, geom) VALUES (%s, %s, %s, %s, "
                "ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_GeomFromText(%s, 4326)), 3)))",
                soil_rows(json.loads(path.read_text(encoding="utf-8"))),
            )
        conn.execute("DELETE FROM soil_units WHERE ST_IsEmpty(geom)")
        conn.execute(
            "UPDATE section_static t SET soil_drainage = u.drainagecl, soil_urban_land = (u.muname ILIKE '%urban land%') "
            "FROM road_sections s, soil_units u "
            "WHERE s.section_id = t.section_id AND ST_Intersects(u.geom, ST_LineInterpolatePoint(s.geom, 0.5))"
        )
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE section_static SET soil_drainage_rank = %s WHERE lower(soil_drainage) = %s",
                [(rank, name) for name, rank in DRAINAGE_RANK.items()],
            )
        share_missing = conn.execute("SELECT coalesce(avg((soil_drainage_rank IS NULL)::int), 1) FROM section_static").fetchone()[0]
        limit = float(src["soils"]["drop_if_missing_share_above"])
        used["soil"] = {
            "missing_share": round(float(share_missing), 3),
            "kept": float(share_missing) <= limit,
            "rule": f"drop if > {limit}",
        }
        if not used["soil"]["kept"]:
            conn.execute("UPDATE section_static SET soil_drainage = NULL, soil_drainage_rank = NULL")

    conn.execute(
        "CREATE TEMP TABLE sec_mid ON COMMIT DROP AS SELECT section_id, ST_LineInterpolatePoint(geom, 0.5) AS mid, "
        "degrees(ST_Azimuth(ST_StartPoint(geom), ST_EndPoint(geom))) AS az FROM road_sections"
    )
    conn.execute("CREATE INDEX ON sec_mid USING gist ((mid::geography))")
    params = {"dist": match["distance_m"], "angle": match["max_angle_deg"]}

    # Traffic (IDOT): the nearest matching count line
    path = raw_dir / "traffic_counts.geojson"
    if path.exists() and "traffic_counts" in src:
        fields = src["traffic_counts"]
        rows = []
        for feature in json.loads(path.read_text(encoding="utf-8")).get("features", []):
            props = feature.get("properties") or {}
            if feature.get("geometry"):
                values = (props.get("ROAD_NAME"), props.get("AADT"), props.get("AADT_YR"), props.get("HCV_AADT"), props.get("HCV_AADTYR"))
                rows.append((*values, json.dumps(feature["geometry"])))
        insert_lines(conn, "traffic_counts", ["road_name", "aadt", "aadt_year", "hcv_aadt", "hcv_year"], rows)
        stats["traffic_counts.lines"] = len(rows)
        sql = MATCH_SQL.format(table="traffic_counts", columns="l.aadt, l.aadt_year, l.hcv_aadt, l.hcv_year")
        conn.execute(
            "UPDATE section_static t SET aadt = x.aadt, aadt_year = x.aadt_year, hcv_aadt = x.hcv_aadt, hcv_year = x.hcv_year "  # noqa: S608
            f"FROM (SELECT DISTINCT ON (section_id) * FROM ({sql}) q ORDER BY section_id, distance_m) x "
            "WHERE x.section_id = t.section_id",
            params,
        )
        used["traffic"] = {"max_count_year_for_training": fields.get("max_count_year"), "busy_bands": fields.get("busy_bands")}

    # Bus routes (Chicago: CTA): how many different routes run along the section
    path = raw_dir / "bus_routes.geojson"
    if path.exists() and "bus_routes" in src:
        cfg = src["bus_routes"]
        rows = []
        for feature in json.loads(path.read_text(encoding="utf-8")).get("features", []):
            props = feature.get("properties") or {}
            route = first_value(props, cfg["route_fields"])
            if feature.get("geometry") and route is not None:
                rows.append((str(route), first_value(props, cfg["name_fields"]), json.dumps(feature["geometry"])))
        insert_lines(conn, "bus_routes", ["route", "name"], rows)
        sql = MATCH_SQL.format(table="bus_routes", columns="l.route")
        conn.execute("UPDATE section_static SET bus_routes = 0")
        conn.execute(
            f"UPDATE section_static t SET bus_routes = x.n FROM (SELECT section_id, count(DISTINCT route) AS n FROM ({sql}) q "  # noqa: S608
            "GROUP BY section_id) x WHERE x.section_id = t.section_id",
            params,
        )
        stats["bus_routes.routes"] = len({r[0] for r in rows})
        used["bus_routes"] = True
    return used


def insert_lines(conn: psycopg.Connection, table: str, columns: list[str], rows: list[tuple]) -> None:
    """Insert lines given as GeoJSON (last item of each row; LineString or MultiLineString), one table row per simple line."""
    statement = sql.SQL(
        "INSERT INTO {table} ({columns}, geom) SELECT {values}, g.geom FROM "
        "(SELECT (ST_Dump(ST_Force2D(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))).geom AS geom) g "
        "WHERE GeometryType(g.geom) = 'LINESTRING'"
    ).format(
        table=sql.Identifier(table),
        columns=sql.SQL(", ").join(map(sql.Identifier, columns)),
        values=sql.SQL(", ").join(sql.Placeholder() * len(columns)),
    )
    with conn.cursor() as cur:
        cur.executemany(statement, rows)
