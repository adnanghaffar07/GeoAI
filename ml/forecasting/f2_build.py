"""F2 step 1: build the learning table from the `forecast` database (plan: documentation/04-design/forecasting-f2-plan.md).

The table is never stored as one big table (about 50 million rows). Instead, compact arrays are saved in data/f2/:
counts per (section, Monday) for each history window, the answer (label), the last report day, daily weather per station
and the fixed facts per section. `f2_store.FeatureStore` turns them into feature rows one Monday at a time.

No-cheating rule (F0 section 4): every history and weather input counts only days strictly BEFORE the Monday.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import psycopg

from forecasting.checkpoints import Checkpoints, Progress, save_array, stamp_of

EPOCH = date(1970, 1, 1)

# Windows over report days d, relative to a Monday D: an event counts when D - start <= d < D - end.
HISTORY_WINDOWS = {
    "reports_30d": (30, 0),
    "reports_90d": (90, 0),
    "reports_365d": (365, 0),
    "reports_same_30d_last_year": (365, 335),
}
# Improvement round (2026-10-29): more history inputs, all strictly before the Monday.
EXTRA_WINDOWS = {"reports_7d": (7, 0), "reports_14d": (14, 0), "reports_all_before": (100_000, 0)}
SAME_SEASON_YEARS = 3  # reports within +-30 days of the same date, 1, 2 and 3 years before (summed)
HABIT_YEARS = 5  # in how many of the last 5 years (365-day blocks) the section had at least one report
DUPLICATE_WINDOWS = {"duplicate_reports_30d": (30, 0), "duplicate_reports_90d": (90, 0)}
LABEL_WINDOW = (0, -30)  # the answer: D <= d < D + 30 (the Monday plus the following 29 days)

HIGHWAY_CODES = {
    "residential": 1,
    "unclassified": 2,
    "tertiary": 3,
    "tertiary_link": 3,
    "secondary": 4,
    "secondary_link": 4,
    "primary": 5,
    "primary_link": 5,
}


def day_number(value: date) -> int:
    return (value - EPOCH).days


def mondays(first: date, last: date) -> np.ndarray:
    if first.weekday() != 0:
        raise ValueError(f"{first} is not a Monday")
    count = (last - first).days // 7 + 1
    return np.array([day_number(first) + 7 * i for i in range(count)], dtype=np.int32)


def window_counts(sections: np.ndarray, days: np.ndarray, weeks: np.ndarray, n_sections: int, start: int, end: int) -> np.ndarray:
    """counts[s, w] = number of events of section s with weeks[w] - start <= day < weeks[w] - end.

    An event on day d is counted for the Mondays D with d + end < D <= d + start. Done with a difference array, so it is
    fast for millions of events.
    """
    first = np.searchsorted(weeks, days + end, side="right")  # first Monday with D > d + end
    last = np.searchsorted(weeks, days + start, side="right")  # first Monday with D > d + start (exclusive)
    keep = first < last
    diff = np.zeros((n_sections, len(weeks) + 1), dtype=np.int32)
    np.add.at(diff, (sections[keep], first[keep]), 1)
    np.add.at(diff, (sections[keep], last[keep]), -1)
    counts = np.cumsum(diff[:, :-1], axis=1, dtype=np.int32)
    return np.minimum(counts, np.iinfo(np.int16).max).astype(np.int16)


def last_event_day(sections: np.ndarray, days: np.ndarray, weeks: np.ndarray, n_sections: int) -> np.ndarray:
    """last[s, w] = latest event day strictly before Monday weeks[w] (-1 when there is none)."""
    first = np.searchsorted(weeks, days, side="right")  # first Monday after the event day
    keep = first < len(weeks)
    last = np.full((n_sections, len(weeks)), -1, dtype=np.int32)
    np.maximum.at(last, (sections[keep], first[keep]), days[keep])
    return np.maximum.accumulate(last, axis=1)


def weather_features(daily: dict[str, np.ndarray], first_day: int, weeks: np.ndarray) -> dict[str, np.ndarray]:
    """Per-Monday weather from daily arrays starting at first_day (NaN = missing). Only days before the Monday are used.

    Missing days are left out of counts and totals (never guessed); a window with no known day is NaN.
    """
    tmax, tmin, prcp, snow = daily["tmax"], daily["tmin"], daily["prcp"], daily["snow"]
    known_t = ~np.isnan(tmax) & ~np.isnan(tmin)
    series = {
        "freeze_thaw": np.where(known_t, (tmax > 0) & (tmin < 0), np.nan),
        "below_freezing": np.where(~np.isnan(tmax), tmax < 0, np.nan),  # frozen all day (max below 0 °C)
        "rain": prcp,
        "heavy_rain": np.where(~np.isnan(prcp), prcp >= 25, np.nan),
        "snow": snow,
        "hot": np.where(~np.isnan(tmax), tmax >= 32, np.nan),
    }
    windows = {
        "freeze_thaw_7d": ("freeze_thaw", 7),
        "freeze_thaw_14d": ("freeze_thaw", 14),
        "freeze_thaw_30d": ("freeze_thaw", 30),
        "below_freezing_days_30d": ("below_freezing", 30),
        "rain_mm_7d": ("rain", 7),
        "rain_mm_30d": ("rain", 30),
        "heavy_rain_days_30d": ("heavy_rain", 30),
        "snow_mm_7d": ("snow", 7),
        "snow_mm_30d": ("snow", 30),
        "hot_days_30d": ("hot", 30),
    }
    index = weeks - first_day  # position of each Monday in the daily arrays
    out: dict[str, np.ndarray] = {}
    for name, (source, length) in windows.items():
        values = series[source].astype(np.float64)
        known = ~np.isnan(values)
        csum = np.concatenate([[0.0], np.cumsum(np.where(known, values, 0.0))])
        ccount = np.concatenate([[0], np.cumsum(known)])
        start = np.clip(index - length, 0, len(values))
        end = np.clip(index, 0, len(values))  # days before the Monday only
        total = csum[end] - csum[start]
        n_known = ccount[end] - ccount[start]
        out[name] = np.where(n_known > 0, total, np.nan).astype(np.float32)
    # days since the last freeze (min below 0 °C) before the Monday, capped at 365
    freeze_days = np.flatnonzero(np.where(np.isnan(tmin), False, tmin < 0))
    if len(freeze_days) == 0:  # no freeze known at all: 365 if there is temperature data, else missing
        since = np.full(len(index), 365.0 if np.any(~np.isnan(tmin)) else np.nan)
    else:
        position = np.searchsorted(freeze_days, index, side="left") - 1
        since = np.where(position >= 0, index - freeze_days[np.clip(position, 0, None)], 365)
    out["days_since_freeze"] = np.minimum(since, 365).astype(np.float32)
    return out


def number_or_nan(value: Any) -> float:
    try:
        return float(str(value).split(";")[0])
    except (TypeError, ValueError):
        return float("nan")


def band(value: Any, edges: list[float]) -> int:
    """0 = missing, 1..len(edges)+1 = quiet .. very busy."""
    if value is None:
        return 0
    return 1 + int(np.searchsorted(edges, float(value), side="right"))


SURFACE_CODES = {"asphalt": 1, "concrete": 2, "paved": 3, "concrete:plates": 2, "paving_stones": 4, "sett": 4, "bricks": 4}


def static_arrays(rows: list[tuple], traffic_bands: list[float], heavy_bands: list[float]) -> dict[str, np.ndarray]:
    """Fixed facts per section, from the query in `extract`. Missing stays NaN (or code 0 for categories)."""
    columns = list(zip(*rows, strict=True)) if rows else [[]] * 14
    (_, highway, length, lanes, surface, _, slope, low_spot, flood_1, flood_02, aadt, hcv, bus, _) = columns
    slope_a = np.array([np.nan if v is None else v for v in slope], dtype=np.float32)
    low_a = np.array([np.nan if v is None else v for v in low_spot], dtype=np.float32)
    return {
        "highway_code": np.array([HIGHWAY_CODES.get(h, 0) for h in highway], dtype=np.float32),
        "length_m": np.array(length, dtype=np.float32),
        "lanes": np.array([number_or_nan(v) for v in lanes], dtype=np.float32),
        "surface_code": np.array([SURFACE_CODES.get((v or "").lower(), 0 if v is None else 5) for v in surface], dtype=np.float32),
        "slope_pct": slope_a,
        "low_spot_m": low_a,
        "flood_1pct": np.array([np.nan if v is None else float(v) for v in flood_1], dtype=np.float32),
        "flood_02pct": np.array([np.nan if v is None else float(v) for v in flood_02], dtype=np.float32),
        "probably_bridge": ((np.nan_to_num(slope_a) > 10) | (np.abs(np.nan_to_num(low_a)) > 5)).astype(np.float32),
        "traffic_band": np.array([band(v, traffic_bands) for v in aadt], dtype=np.float32),
        "heavy_vehicle_band": np.array([band(v, heavy_bands) for v in hcv], dtype=np.float32),
        "bus_routes": np.array([np.nan if v is None else v for v in bus], dtype=np.float32),
    }


# Nearest weather station: distance on a sphere (use_spheroid = false), the same as the <-> search used for the F2
# build, so Chicago keeps exactly the same station per section (same-results check, 2026-10-30).
SECTIONS_SQL = """
SELECT s.section_id, s.highway, s.length_m, s.lanes, s.surface, coalesce(a.held_out, false),
       t.slope_pct, t.low_spot_m, t.flood_1pct, t.flood_02pct, t.aadt, t.hcv_aadt, t.bus_routes,
       (SELECT w.station_id FROM weather_stations w
        ORDER BY ST_Distance(w.geom::geography, ST_LineInterpolatePoint(s.geom, 0.5)::geography, false), w.station_id LIMIT 1)
FROM road_sections s
LEFT JOIN community_areas a ON a.area_number = s.community_area
LEFT JOIN section_static t ON t.section_id = s.section_id
ORDER BY s.section_id
"""

EVENTS_SQL = """
SELECT s.section_id, (p.created_at::date - DATE '1970-01-01') AS day
FROM pothole_reports p
JOIN road_sections s ON ST_DWithin(s.geom::geography, p.geom::geography, %(match_m)s)
WHERE NOT p.is_duplicate AND p.geom IS NOT NULL
"""

MIDPOINTS_SQL = """
SELECT section_id, ST_X(p), ST_Y(p) FROM (SELECT section_id, ST_LineInterpolatePoint(geom, 0.5) AS p FROM road_sections) m
"""


def neighbour_pairs(lon: np.ndarray, lat: np.ndarray, distance_m: float, crs: str = "EPSG:26916") -> tuple[np.ndarray, np.ndarray]:
    """All pairs of sections whose middles are within distance_m (meters, in the area's UTM zone), not a section with itself.

    A k-d tree finds them in seconds; comparing every pair inside the database took hours (2026-10-29).
    """
    from pyproj import Transformer
    from scipy.spatial import cKDTree

    x, y = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(lon, lat)
    pairs = cKDTree(np.column_stack([x, y])).query_pairs(distance_m, output_type="ndarray")
    rows = np.concatenate([pairs[:, 0], pairs[:, 1]]).astype(np.int32)  # both directions
    cols = np.concatenate([pairs[:, 1], pairs[:, 0]]).astype(np.int32)
    return rows, cols


EVENTS_YEAR_SQL = EVENTS_SQL + " AND p.created_at >= %(start)s AND p.created_at < %(end)s"
# duplicates: several people reporting the same pothole (an input only, never an answer)
DUPLICATES_YEAR_SQL = EVENTS_YEAR_SQL.replace("WHERE NOT p.is_duplicate", "WHERE p.is_duplicate")


def extra_history(sections: np.ndarray, days: np.ndarray, weeks: np.ndarray, n: int) -> dict[str, np.ndarray]:
    """The improvement-round inputs from non-duplicate reports (all windows end before the Monday)."""
    out = {name: window_counts(sections, days, weeks, n, a, b) for name, (a, b) in EXTRA_WINDOWS.items()}
    season = np.zeros((n, len(weeks)), dtype=np.int32)
    for k in range(1, SAME_SEASON_YEARS + 1):
        season += window_counts(sections, days, weeks, n, 365 * k + 30, 365 * k - 30)
    out["reports_same_season_3y"] = np.minimum(season, np.iinfo(np.int16).max).astype(np.int16)
    habit = np.zeros((n, len(weeks)), dtype=np.int16)
    for k in range(1, HABIT_YEARS + 1):
        habit += window_counts(sections, days, weeks, n, 365 * k, 365 * (k - 1)) > 0
    out["years_with_reports_5y"] = habit
    return out


def match_by_year(
    conn, cp: Checkpoints, out_dir: Path, kind: str, sql: str, years: list[int], position: dict, match_m: float
) -> np.ndarray:
    """Match reports to sections one year at a time; each finished year is saved (folder out_dir/kind)."""
    todo = [y for y in years if not cp.done(f"{kind}_{y}")]
    progress = Progress(f"{kind}: years matched", len(todo), every=0)
    for year in todo:
        found = conn.execute(sql, {"match_m": match_m, "start": date(year, 1, 1), "end": date(year + 1, 1, 1)}).fetchall()
        pairs = np.array([(position[s], d) for s, d in found], dtype=np.int32).reshape(-1, 2)
        save_array(out_dir / kind, str(year), pairs)
        cp.mark(f"{kind}_{year}", len(pairs))
        progress.step()
    if not years:
        return np.zeros((0, 2), np.int32)
    return np.concatenate([np.load(out_dir / kind / f"{y}.npy") for y in years])


BUILD_VERSION = 2  # change when the build logic changes, so old saved parts are not reused


def data_stamp(conn: psycopg.Connection) -> Any:
    row = conn.execute("SELECT max(id), max(loaded_at)::text FROM load_log").fetchone()
    return list(row) if row else None


def build(
    conn: psycopg.Connection,
    out_dir: Path,
    first_monday: date,
    last_monday: date,
    cfg: dict[str, Any],
    match_m: float,
    fresh: bool = False,
    crs: str = "EPSG:26916",
) -> None:
    """Build the learning table in steps; each finished step is saved, and a re-run continues after the last one."""
    keys = ["neighbour_distance_m", "snow_station", "traffic_bands", "heavy_vehicle_bands"]
    stamp = stamp_of(BUILD_VERSION, data_stamp(conn), {k: cfg[k] for k in keys}, first_monday, last_monday, match_m)
    cp = Checkpoints(out_dir, stamp, fresh)
    weeks = mondays(first_monday, last_monday)

    # 1. sections and their fixed facts
    if not cp.done("sections"):
        print("  step 1/7: reading road sections", flush=True)
        rows = conn.execute(SECTIONS_SQL).fetchall()
        if not rows:
            raise SystemExit("No road sections in the forecast database. Run the F1 load first.")
        (out_dir / "sections.json").write_text(json.dumps(rows, default=float), encoding="utf-8")
        cp.mark("sections", len(rows))
    sections = [tuple(row) for row in json.loads((out_dir / "sections.json").read_text(encoding="utf-8"))]
    ids = [row[0] for row in sections]
    position = {section_id: i for i, section_id in enumerate(ids)}
    n = len(ids)

    # 2. pothole reports matched to sections, one year at a time (the slowest step; each year is saved)
    first_year, last_year = (
        int(v)
        for v in conn.execute(
            "SELECT extract(year FROM min(created_at)), extract(year FROM max(created_at)) FROM pothole_reports"
        ).fetchone()
    )
    years = list(range(first_year, last_year + 1))
    done_years = sum(cp.done(f"events_{y}") for y in years)
    print(f"  step 2/7: matching pothole reports to sections, year by year ({done_years} of {len(years)} years already done)", flush=True)
    events = match_by_year(conn, cp, out_dir, "events", EVENTS_YEAR_SQL, years, position, match_m)
    event_sections, event_days = events[:, 0].copy(), events[:, 1].copy()

    # 3. history windows, answers, last report day (saved Monday-first: one Monday = one fast read)
    if not cp.done("history"):
        print(f"  step 3/7: history windows and answers ({n:,} sections, {len(weeks):,} Mondays, {len(events):,} matches)", flush=True)
        save_array(out_dir, "weeks", weeks)
        for name, (start, end) in HISTORY_WINDOWS.items():
            save_array(out_dir, name, np.ascontiguousarray(window_counts(event_sections, event_days, weeks, n, start, end).T))
        label = window_counts(event_sections, event_days, weeks, n, *LABEL_WINDOW)
        save_array(out_dir, "label", np.ascontiguousarray((label > 0).astype(np.int8).T))
        del label
        save_array(out_dir, "last_report_day", np.ascontiguousarray(last_event_day(event_sections, event_days, weeks, n).T))
        cp.mark("history", len(events))

    # 3b. improvement round: recent, seasonal-habit and duplicate-report inputs
    if not cp.done("history_extra"):
        print("  step 3b/7: extra history inputs and duplicate reports (duplicates matched year by year)", flush=True)
        duplicates = match_by_year(conn, cp, out_dir, "duplicates", DUPLICATES_YEAR_SQL, years, position, match_m)
        for name, values in extra_history(event_sections, event_days, weeks, n).items():
            save_array(out_dir, name, np.ascontiguousarray(values.T))
        for name, (a, b) in DUPLICATE_WINDOWS.items():
            counts = window_counts(duplicates[:, 0].copy(), duplicates[:, 1].copy(), weeks, n, a, b)
            save_array(out_dir, name, np.ascontiguousarray(counts.T))
        cp.mark("history_extra", len(duplicates))

    # 4. neighbours within 200 m
    if not cp.done("neighbours"):
        print("  step 4/7: finding neighbours", flush=True)
        lon, lat = np.zeros(n), np.zeros(n)
        for section_id, x, y in conn.execute(MIDPOINTS_SQL).fetchall():
            lon[position[section_id]], lat[position[section_id]] = x, y
        rows, cols = neighbour_pairs(lon, lat, cfg["neighbour_distance_m"], crs)
        save_array(out_dir, "neighbour_rows", rows)
        save_array(out_dir, "neighbour_cols", cols)
        cp.mark("neighbours", len(rows))

    # 5. weather per station
    stations = sorted({row[13] for row in sections})
    if not cp.done("weather"):
        print("  step 5/7: weather", flush=True)
        save_array(out_dir, "station_of_section", np.array([stations.index(row[13]) for row in sections], dtype=np.int16))
        snow_station = stations.index(cfg["snow_station"]) if cfg["snow_station"] in stations else 0
        first_day = day_number(first_monday) - 400
        days_total = day_number(last_monday) - first_day + 1
        weather_rows = conn.execute(
            "SELECT station_id, (date - DATE '1970-01-01'), tmax_c, tmin_c, prcp_mm, snow_mm FROM weather_daily "
            "WHERE date >= %s AND date <= %s",
            (EPOCH + timedelta(days=first_day), last_monday),
        ).fetchall()
        per_station = {s: {k: np.full(days_total, np.nan) for k in ("tmax", "tmin", "prcp", "snow")} for s in stations}
        for station, day, tmax, tmin, prcp, snow in weather_rows:
            if station in per_station:
                for key, value in (("tmax", tmax), ("tmin", tmin), ("prcp", prcp), ("snow", snow)):
                    if value is not None:
                        per_station[station][key][day - first_day] = value
        station_features = [weather_features(per_station[s], first_day, weeks) for s in stations]
        for name in station_features[0]:
            stacked = np.stack([f[name] for f in station_features])  # (stations, Mondays)
            if name.startswith("snow_"):
                stacked = np.repeat(stacked[snow_station : snow_station + 1], len(stations), axis=0)  # one snow station (Chicago: O'Hare)
            save_array(out_dir, f"weather__{name}", stacked)
        cp.mark("weather", len(weather_rows))

    # 6. fixed facts, held-out areas, and the "complete" marker (meta.json)
    if not cp.done("static"):
        print("  step 6/7: fixed facts per section", flush=True)
        for name, values in static_arrays(sections, cfg["traffic_bands"], cfg["heavy_vehicle_bands"]).items():
            save_array(out_dir, f"static__{name}", values)
        save_array(out_dir, "held_out", np.array([bool(row[5]) for row in sections]))
        meta = {
            "section_ids": ids,
            "stations": stations,
            "first_monday": str(first_monday),
            "last_monday": str(last_monday),
            "stamp": stamp,
        }
        (out_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        cp.mark("static")
    print("  learning table complete", flush=True)
