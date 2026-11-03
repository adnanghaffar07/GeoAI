"""F4b: the forecasting work the app's background jobs call (design: forecasting-f4b-design.md section 2).

- `refresh_weather`: download each station's NOAA file again and replace its daily rows.
- `download_new_reports`: Chicago only: the 311 pothole reports newer than the newest one we have (same columns, no
  address; owner decision B-D3), added to the forecast database and matched to road sections.
- `weekly_levels`: Chicago only: the B1 model `forecast-chicago-0.2` ranks every section for one Monday; top 1% high,
  next 9% medium (F4-D2), with the main reasons. The raw value is returned only for the monthly check (never shown).
- `setup_project_area`: a project outside Chicago becomes its own Level 1 area (boundary = the project's survey area).
- `sections_in`: the road sections inside a project's boundary.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import psycopg
import yaml
from psycopg import sql

from forecasting import areas, load, settings
from forecasting.download import download_file, download_socrata_csv, sha256_file
from forecasting.f2_store import feature_names

HIGH_SHARE, TOP_SHARE = 0.01, 0.10  # F4-D2: high = top 1% each Monday, medium = the next 9%
MODEL_FILE, MODELS_JSON = "b1_logistic_v0.2.joblib", "f4a-models.json"


# ---------- weather ----------


def reload_weather(conn: psycopg.Connection, raw_dir: Path, src: dict[str, Any]) -> dict[str, str | None]:
    """Replace the daily rows of the area's stations from their raw files. Returns the last day per station."""
    weather = src["weather"]
    start = date.fromisoformat(str(weather["start_date"]))
    last: dict[str, str | None] = {}
    for station in weather["stations"]:
        rows = list(load.parse_ghcn_csv(raw_dir / f"weather_{station['id']}.csv", station["id"], start, Counter()))
        load.check_temperature_units(rows)
        conn.execute("DELETE FROM weather_daily WHERE station_id = %s", (station["id"],))
        load.copy_rows(conn, "weather_daily", ["station_id", "date", "tmax_c", "tmin_c", "prcp_mm", "snow_mm", "snwd_mm"], rows)
        known = [r[1] for r in rows if r[2] is not None and r[3] is not None]
        last[station["id"]] = str(max(known)) if known else None
    return last


def refresh_weather(conn: psycopg.Connection, area: areas.Area, session) -> dict[str, str | None]:
    src = areas.ready_sources(area)
    for station in src["weather"]["stations"]:
        download_file(session, src["weather"]["url_template"].format(station=station["id"]), area.raw_dir / f"weather_{station['id']}.csv")
    return reload_weather(conn, area.raw_dir, src)


# ---------- new Chicago 311 reports ----------


def download_new_reports(conn: psycopg.Connection, area: areas.Area, session, sleep=None) -> int:
    """Add the reports created since the newest one we have (the new 311 system only). Returns how many were added."""
    src = areas.ready_sources(area)
    cfg, portal = src["potholes_current"], src["portal"]
    newest = conn.execute("SELECT max(created_at) FROM pothole_reports WHERE source = 'potholes_current'").fetchone()[0]
    where = cfg["where"] + (f" AND created_date >= '{newest.isoformat(timespec='seconds')}'" if newest else "")
    path = area.raw_dir / "potholes_current_new.csv"
    kwargs = {"sleep": sleep} if sleep else {}
    download_socrata_csv(
        session,
        base_url=portal["base_url"],
        dataset_id=cfg["dataset_id"],
        select=cfg["select"],
        where=where,
        page_size=portal["page_size"],
        out_path=path,
        **kwargs,
    )
    rows = list(load.parse_pothole_csv(path, "potholes_current", cfg, src["bbox"], Counter(), f"outside_{area.key}"))
    conn.execute("CREATE TEMP TABLE new_reports (LIKE pothole_reports INCLUDING DEFAULTS) ON COMMIT DROP")
    columns = ["source", "request_id", "created_at", "is_duplicate", "status", "latitude", "longitude", "location_issue"]
    load.copy_rows(conn, "new_reports", columns, rows)
    column_list = ", ".join(columns)
    added = conn.execute(
        f"INSERT INTO pothole_reports ({column_list}) SELECT {column_list} FROM new_reports ON CONFLICT DO NOTHING"  # noqa: S608 (constant names)
    ).rowcount
    conn.execute(
        "UPDATE pothole_reports SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) "
        "WHERE location_issue IS NULL AND geom IS NULL"
    )
    conn.execute(
        "UPDATE pothole_reports p SET community_area = a.area_number FROM community_areas a "
        "WHERE p.community_area IS NULL AND p.geom IS NOT NULL AND ST_Intersects(a.geom, p.geom)"
    )
    return added


# ---------- weekly Chicago levels ----------


def load_model(models_dir: Path):
    """The app's model, only if its file has the fingerprint recorded when it was made (like the trial photo model)."""
    info = json.loads((models_dir / MODELS_JSON).read_text(encoding="utf-8"))
    path = models_dir / MODEL_FILE
    if sha256_file(path) != info["fingerprints"][MODEL_FILE]:
        raise SystemExit(f"{path.name} changed since it was made (fingerprint mismatch); the app refuses it.")
    return joblib.load(path), info["version"]


def contributions(model, x: np.ndarray) -> np.ndarray:
    """How much each input pushes each section's B1 score up or down (logistic regression: weight x scaled input)."""
    prepare, logistic = model.named_steps["prepare"], model.named_steps["model"]
    transformed = prepare.transform(x)
    if hasattr(transformed, "toarray"):
        transformed = transformed.toarray()
    parts = np.asarray(transformed, dtype=float) * logistic.coef_[0]
    out = np.zeros((x.shape[0], x.shape[1]))
    for column, name in enumerate(prepare.get_feature_names_out()):
        match = re.search(r"x(\d+)", name.split("__", 1)[-1])
        if match:
            out[:, int(match.group(1))] += parts[:, column]
    return out


def level_counts(n: int) -> tuple[int, int]:
    """How many sections are high and medium (F4-D2): the top 1%, then the rest of the top 10%."""
    high = math.ceil(HIGH_SHARE * n) if n else 0
    return high, max(math.ceil(TOP_SHARE * n) - high, 0)


def weekly_levels(
    conn: psycopg.Connection, monday: date, cfg: dict[str, Any], crs: str, model, top_reasons: int = 3
) -> list[dict[str, Any]]:
    """Rank, level, reasons and missing inputs for every section on one Monday (inputs use only days before it)."""
    from forecasting import weekly

    store = weekly.monday_store(conn, monday, cfg, crs)
    x = store.matrix(0)
    score = model.predict_proba(x)[:, 1]
    order = np.argsort(-score, kind="stable")
    rank = np.empty(len(order), dtype=int)
    rank[order] = np.arange(1, len(order) + 1)
    n_high, n_medium = level_counts(len(order))
    push = contributions(model, x)
    names = feature_names()
    out = []
    for i, section_id in enumerate(store.meta["section_ids"]):
        best = [j for j in np.argsort(-push[i]) if push[i, j] > 0][:top_reasons]
        out.append(
            {
                "section_id": section_id,
                "rank": int(rank[i]),
                "level": "high" if rank[i] <= n_high else "medium" if rank[i] <= n_high + n_medium else "low",
                "reasons": [
                    {
                        "input": names[j],
                        "value": None if np.isnan(x[i, j]) else round(float(x[i, j]), 2),
                        "push": round(float(push[i, j]), 3),
                    }
                    for j in best
                ],
                "missing_inputs": [names[j] for j in np.flatnonzero(np.isnan(x[i]))],
                "monitor_value": round(float(score[i]), 5),
            }
        )
    return out


# ---------- project areas ----------


def project_area_key(project_id: str) -> str:
    return "p_" + project_id.replace("-", "")[:12]


def write_project_area(project_id: str, project_name: str, boundary_geojson: dict[str, Any], base: Path | None = None) -> Path:
    """The area file for a project outside Chicago (Level 1): its survey area is the boundary. Returns the area folder."""
    base = base or settings.FORECAST_DIR / "data" / "_project_areas"
    key = project_area_key(project_id)
    base.mkdir(parents=True, exist_ok=True)
    boundary = base / f"{key}.geojson"
    boundary.write_text(
        json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": boundary_geojson}]}),
        encoding="utf-8",
    )
    area = {
        "name": project_name,
        "schema": key,
        "level": 1,
        "boundary": {"geojson_file": str(boundary.resolve())},
        "weather_stations": "auto",
        "traffic_counts": "idot",  # Illinois counts; outside Illinois the box finds none, so traffic shows as missing
    }
    (base / f"{key}.yaml").write_text(
        "# Written by the app for one project (F4b). Do not edit by hand.\n" + yaml.safe_dump(area, sort_keys=False), encoding="utf-8"
    )
    return base


def setup_project_area(url: str, key: str, areas_dir: Path, rules: dict[str, Any], session=None) -> areas.Area:
    """Area check, downloads and load for one project area (the same steps as scripts/forecast-area.bat)."""
    from forecasting import area_check
    from forecasting.download import download_all

    area = areas.load_area(key, areas_dir=areas_dir)
    area_check.run(area, rules, terms_confirmed=False, session=session)
    download_all(area.raw_dir, areas.ready_sources(area, need_box=False), rules, terms_confirmed=False, session=session)
    load.run_load(url, area.raw_dir, areas.ready_sources(area), rules, schema=area.schema)
    return area


def in_chicago(conn: psycopg.Connection, boundary_ewkt: str) -> bool:
    """True when the project's centre lies inside the City of Chicago (the Chicago area's districts)."""
    row = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM chicago.community_areas a WHERE ST_Intersects(a.geom, ST_PointOnSurface(ST_GeomFromEWKT(%s))))",
        (boundary_ewkt,),
    ).fetchone()
    return bool(row[0])


def sections_in(conn: psycopg.Connection, schema: str, boundary_ewkt: str) -> list[tuple]:
    """(section_id, name, highway, length_m, EWKT line) of the area's sections that touch the project boundary."""
    query = sql.SQL(
        "SELECT section_id, name, highway, length_m, ST_AsEWKT(geom) FROM {}.road_sections "
        "WHERE ST_Intersects(geom, ST_GeomFromEWKT(%s)) ORDER BY section_id"
    ).format(sql.Identifier(schema))
    return conn.execute(query, (boundary_ewkt,)).fetchall()
