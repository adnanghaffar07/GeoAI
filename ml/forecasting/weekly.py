"""F4b: the inputs for ONE Monday straight from the forecast database, for the weekly Chicago levels in the app.

The F2/F4a learning table is built for all Mondays at once (15-30 minutes). The app needs only the newest Monday each week,
so this module keeps a table of which reports belong to which road section (`report_matches`, filled once from the learning
table, then only new reports are matched) and builds the same inputs for one Monday in about a minute.

Rule (forecasting-f4b-design.md section 2): the one-Monday inputs must equal the learning table's inputs for past Mondays
exactly; `check` compares them, and the weekly levels are trusted only after it passes.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import psycopg

from forecasting.f2_build import (
    DUPLICATE_WINDOWS,
    EPOCH,
    HISTORY_WINDOWS,
    SECTIONS_SQL,
    day_number,
    extra_history,
    last_event_day,
    neighbour_pairs,
    static_arrays,
    weather_features,
    window_counts,
)
from forecasting.f2_store import FeatureStore

TABLES_SQL = """
CREATE TABLE IF NOT EXISTS report_matches (
    source text NOT NULL,
    request_id text NOT NULL,
    section_id text NOT NULL REFERENCES road_sections (section_id) ON DELETE CASCADE,
    day integer NOT NULL,            -- days since 1970-01-01 (report date)
    is_duplicate boolean NOT NULL,
    PRIMARY KEY (source, request_id, section_id)
);
CREATE INDEX IF NOT EXISTS report_matches_day_idx ON report_matches (day);
-- every report already looked at (matched or not), so new runs match only new reports
CREATE TABLE IF NOT EXISTS report_match_log (
    source text NOT NULL,
    request_id text NOT NULL,
    matched_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, request_id)
);
"""

# The same match as the learning table (f2_build.EVENTS_SQL): a located report within the label distance of a section.
MATCH_NEW_SQL = """
INSERT INTO report_matches (source, request_id, section_id, day, is_duplicate)
SELECT p.source, p.request_id, s.section_id, (p.created_at::date - DATE '1970-01-01'), p.is_duplicate
FROM pothole_reports p
JOIN road_sections s ON ST_DWithin(s.geom::geography, p.geom::geography, %(match_m)s)
WHERE p.geom IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM report_match_log l WHERE l.source = p.source AND l.request_id = p.request_id)
ON CONFLICT DO NOTHING
"""
LOG_NEW_SQL = """
INSERT INTO report_match_log (source, request_id)
SELECT p.source, p.request_id FROM pothole_reports p
WHERE NOT EXISTS (SELECT 1 FROM report_match_log l WHERE l.source = p.source AND l.request_id = p.request_id)
"""


def ensure_tables(conn: psycopg.Connection) -> None:
    conn.execute(TABLES_SQL)


def seed_from_learning_table(conn: psycopg.Connection, f2_dir: Path) -> dict[str, int]:
    """Fill report_matches once from the matches the learning table already made (no slow re-matching).

    The learning table keeps (section position, day) pairs per year, without report ids, so seeded rows get a made-up
    request id ("seed-<n>") and every report present at that time is marked as looked at. Later reports are matched by
    `match_new_reports` with their real ids.
    """
    ensure_tables(conn)
    if conn.execute("SELECT EXISTS (SELECT 1 FROM report_matches)").fetchone()[0]:
        return {"seeded": 0}
    meta = json.loads((f2_dir / "meta.json").read_text(encoding="utf-8"))
    ids = meta["section_ids"]
    counts = {"events": 0, "duplicates": 0}
    number = 0
    with conn.cursor().copy("COPY report_matches (source, request_id, section_id, day, is_duplicate) FROM STDIN") as copy:
        for kind, duplicate in (("events", False), ("duplicates", True)):
            for path in sorted((f2_dir / kind).glob("*.npy")):
                for position, day in np.load(path):
                    number += 1
                    copy.write_row(("seed", f"seed-{number}", ids[int(position)], int(day), duplicate))
                    counts[kind] += 1
    conn.execute(LOG_NEW_SQL)
    return counts


def match_new_reports(conn: psycopg.Connection, match_m: float) -> int:
    """Match only the reports not looked at yet (after a weekly download of new reports). Returns the new matches."""
    ensure_tables(conn)
    added = conn.execute(MATCH_NEW_SQL, {"match_m": match_m}).rowcount
    conn.execute(LOG_NEW_SQL)
    return added


def monday_store(conn: psycopg.Connection, monday: date, cfg: dict[str, Any], crs: str) -> FeatureStore:
    """A learning table with ONE Monday (and no answer), built from the database; `.matrix(0)` gives its inputs."""
    if monday.weekday() != 0:
        raise ValueError(f"{monday} is not a Monday")
    sections = [tuple(row) for row in conn.execute(SECTIONS_SQL).fetchall()]
    ids = [row[0] for row in sections]
    position = {section_id: i for i, section_id in enumerate(ids)}
    n = len(ids)
    week = np.array([day_number(monday)], dtype=np.int32)
    rows = conn.execute("SELECT section_id, day, is_duplicate FROM report_matches WHERE day < %s", (int(week[0]),)).fetchall()
    sec = np.array([position[r[0]] for r in rows], dtype=np.int32)
    days = np.array([r[1] for r in rows], dtype=np.int32)
    dup = np.array([r[2] for r in rows], dtype=bool)
    ev_s, ev_d, du_s, du_d = sec[~dup], days[~dup], sec[dup], days[dup]

    arrays: dict[str, np.ndarray] = {"weeks": week}
    for name, (a, b) in HISTORY_WINDOWS.items():
        arrays[name] = window_counts(ev_s, ev_d, week, n, a, b).T
    arrays["last_report_day"] = last_event_day(ev_s, ev_d, week, n).T
    for name, values in extra_history(ev_s, ev_d, week, n).items():
        arrays[name] = values.T
    for name, (a, b) in DUPLICATE_WINDOWS.items():
        arrays[name] = window_counts(du_s, du_d, week, n, a, b).T

    lon, lat = np.zeros(n), np.zeros(n)
    for section_id, x, y in conn.execute(
        "SELECT section_id, ST_X(p), ST_Y(p) FROM (SELECT section_id, ST_LineInterpolatePoint(geom, 0.5) AS p FROM road_sections) m"
    ).fetchall():
        lon[position[section_id]], lat[position[section_id]] = x, y
    arrays["neighbour_rows"], arrays["neighbour_cols"] = neighbour_pairs(lon, lat, cfg["neighbour_distance_m"], crs)

    stations = sorted({row[13] for row in sections})
    arrays["station_of_section"] = np.array([stations.index(row[13]) for row in sections], dtype=np.int16)
    snow_station = stations.index(cfg["snow_station"]) if cfg["snow_station"] in stations else 0
    first_day = int(week[0]) - 400
    total = int(week[0]) - first_day + 1
    per_station = {s: {k: np.full(total, np.nan) for k in ("tmax", "tmin", "prcp", "snow")} for s in stations}
    for station, day, *values in conn.execute(
        "SELECT station_id, (date - DATE '1970-01-01'), tmax_c, tmin_c, prcp_mm, snow_mm FROM weather_daily "
        "WHERE date >= %s AND date <= %s",
        (EPOCH + timedelta(days=first_day), monday),
    ).fetchall():
        if station in per_station:
            for key, value in zip(("tmax", "tmin", "prcp", "snow"), values, strict=True):
                if value is not None:
                    per_station[station][key][day - first_day] = value
    features = [weather_features(per_station[s], first_day, week) for s in stations]
    for name in features[0]:
        stacked = np.stack([f[name] for f in features])
        if name.startswith("snow_"):
            stacked = np.repeat(stacked[snow_station : snow_station + 1], len(stations), axis=0)
        arrays[f"weather__{name}"] = stacked
    for name, values in static_arrays(sections, cfg["traffic_bands"], cfg["heavy_vehicle_bands"]).items():
        arrays[f"static__{name}"] = values
    arrays["held_out"] = np.array([bool(row[5]) for row in sections])
    arrays["label"] = np.zeros((1, n), dtype=np.int8)  # unknown yet; never used for a forecast
    meta = {"section_ids": ids, "stations": stations, "first_monday": str(monday), "last_monday": str(monday)}
    return FeatureStore(arrays, meta)


def check(conn: psycopg.Connection, table: FeatureStore, mondays: list[date], cfg: dict[str, Any], crs: str) -> dict[str, Any]:
    """Compare the one-Monday inputs with the learning table's inputs for each given Monday (must be identical)."""
    results = []
    for monday in mondays:
        one = monday_store(conn, monday, cfg, crs)
        expected = table.matrix(table.week_index(monday))
        got = one.matrix(0)
        same_ids = one.meta["section_ids"] == table.meta["section_ids"]
        equal = same_ids and expected.shape == got.shape and bool(np.array_equal(expected, got, equal_nan=True))
        differing = (
            []
            if equal or not same_ids
            else sorted({int(c) for c in np.flatnonzero(~np.all((expected == got) | (np.isnan(expected) & np.isnan(got)), axis=0))})
        )
        results.append({"monday": str(monday), "same": equal, "sections": len(one.meta["section_ids"]), "differing_inputs": differing})
    return {"passed": all(r["same"] for r in results), "mondays": results}


def default_check_mondays(table: FeatureStore) -> list[date]:
    """Five Mondays spread over the table, including the newest and a winter Monday."""
    last = table.monday(len(table.weeks) - 1)
    winter = next(table.monday(w) for w in range(len(table.weeks) - 1, -1, -1) if table.monday(w).month == 2)
    picks = [table.monday(0), table.monday(len(table.weeks) // 2), winter, last - timedelta(days=7), last]
    return sorted(set(picks))
