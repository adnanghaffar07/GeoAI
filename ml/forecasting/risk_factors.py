"""Level 1 "risk factors" for any area (any-area plan FA3; roadmap §7.7). Factors, NEVER a percentage.

For every road section and one day ("as of"), the factors that already feed the Chicago forecast: recent freeze-thaw
days, days below freezing, heavy-rain days, snow (from the area's weather stations, only days BEFORE the as-of day),
dips where water collects, slope, flood zone, traffic, heavy vehicles and bus routes. Each gets a plain level
(low / medium / high, or missing) using fixed cut-offs written in config/risk-factors.yaml.

The cut-offs are drafted from Chicago's TRAINING years only (`draft_cutoffs`, owner decision D5) and must be shown to
the owner before use; while the file says DRAFT, every Level 1 report says so at the top.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import psycopg
import yaml

from forecasting import settings
from forecasting.f2_build import EPOCH, day_number, weather_features

CUTOFFS_FILE = settings.CONFIG_DIR / "risk-factors.yaml"
LEVELS = ["low", "medium", "high"]

# name -> (plain words, unit, which way is risky). "up": higher values are riskier; "down": lower (more negative).
FACTORS: dict[str, tuple[str, str, str]] = {
    "freeze_thaw_14d": ("Freeze-thaw days in the last 14 days", "days", "up"),
    "below_freezing_days_30d": ("Days below freezing in the last 30 days", "days", "up"),
    "heavy_rain_days_30d": ("Heavy-rain days (25 mm or more) in the last 30 days", "days", "up"),
    "snow_mm_30d": ("Snow in the last 30 days", "mm", "up"),
    "low_spot_m": ("Dip where water collects (height compared with roads within 200 m)", "m", "down"),
    "slope_pct": ("Slope", "%", "up"),
    "flood_zone": ("FEMA flood zone (high = 1% yearly chance, medium = 0.2%)", "", "fixed"),
    "traffic_band": ("Traffic (vehicles per day: high = 30,000 or more, medium = 15,000-30,000)", "band", "fixed"),
    "heavy_vehicle_band": ("Heavy vehicles (per day: high = 2,500 or more, medium = 1,000-2,500)", "band", "fixed"),
    "bus_routes": ("Bus routes on the road (high = 2 or more, medium = 1)", "routes", "fixed"),
}
WEATHER_FACTORS = ["freeze_thaw_14d", "below_freezing_days_30d", "heavy_rain_days_30d", "snow_mm_30d"]
WINTER_ONLY = {"freeze_thaw_14d", "below_freezing_days_30d", "snow_mm_30d"}  # cut-offs measured on Nov-Apr Mondays


# ---------- levels (pure functions) ----------


def level_of(name: str, value: float | None, cutoffs: dict[str, Any]) -> str:
    """'low' / 'medium' / 'high', or 'missing' when there is no value."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "missing"
    direction = FACTORS[name][2]
    if direction == "fixed":
        if name == "flood_zone":
            return {2: "high", 1: "medium"}.get(int(value), "low")
        if name in ("traffic_band", "heavy_vehicle_band"):
            return "missing" if int(value) == 0 else {4: "high", 3: "medium"}.get(int(value), "low")
        if name == "bus_routes":
            return "high" if value >= 2 else "medium" if value >= 1 else "low"
    cut = cutoffs[name]
    if direction == "up":
        return "high" if value >= cut["high"] else "medium" if value >= cut["medium"] else "low"
    return "high" if value <= cut["high"] else "medium" if value <= cut["medium"] else "low"


def levels_array(name: str, values: np.ndarray, cutoffs: dict[str, Any]) -> np.ndarray:
    """Level index per value: -1 missing, 0 low, 1 medium, 2 high (vectorised level_of)."""
    return np.array([-1 if (lv := level_of(name, float(v), cutoffs)) == "missing" else LEVELS.index(lv) for v in values])


def read_cutoffs(path: Path = CUTOFFS_FILE) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(
            f"No risk-factor cut-offs yet ({path.name}). Run the Chicago check first "
            "(`scripts\\forecast-area-check-chicago.bat`): it drafts them from Chicago's training years."
        )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ---------- drafting the cut-offs from Chicago's training years (D5) ----------


def nice(value: float, unit: str) -> float:
    if unit == "days":
        return float(max(1, round(value)))
    if unit == "mm":
        return float(max(1, round(value)))
    return round(float(value), 2)


def level_counts(level_idx: np.ndarray, positives: np.ndarray, rows: np.ndarray) -> dict[str, dict[str, float | None]]:
    """Share of rows and report rate per level (index -1 missing, 0 low, 1 medium, 2 high)."""
    rows_per = np.bincount(level_idx + 1, weights=rows, minlength=4)
    pos_per = np.bincount(level_idx + 1, weights=positives, minlength=4)
    total = float(rows_per.sum())
    return {
        lv: {
            "share": round(float(rows_per[k]) / total, 3) if total else 0.0,
            "report_rate": round(float(pos_per[k] / rows_per[k]), 4) if rows_per[k] else None,
        }
        for k, lv in enumerate(["missing", *LEVELS])
    }


def draft_cutoffs(store, rules: dict[str, Any], purge_days: int) -> tuple[dict[str, Any], list[dict[str, Any]], float]:
    """Cut-offs from the training Mondays only (medium = 75th, high = 95th percentile; dips: 10th and 2nd), and how
    often a new pothole report followed within 30 days at each level (sections outside the held-out areas).
    Returns (cut-offs, evidence per factor, base rate)."""
    from forecasting.f2_store import is_winter, period_weeks

    p = rules["periods"]
    weeks = period_weeks(store, p["train"], p["validation"]["start"], purge_days)
    winter = np.array([is_winter(store.monday(int(w))) for w in weeks])
    keep = ~store.held_out
    station = store.station[keep]
    labels = np.stack([np.asarray(store.label(int(w)))[keep] for w in weeks]).astype(np.int8)  # (weeks, sections)
    n_stations = int(store.station.max()) + 1
    # positives and rows per (station, Monday), so weather levels are counted without a (weeks x sections) level table
    pos_sw = np.stack([np.bincount(station, weights=labels[i], minlength=n_stations) for i in range(len(weeks))], axis=1)
    rows_sw = np.repeat(np.bincount(station, minlength=n_stations)[:, None].astype(float), len(weeks), axis=1)
    cutoffs: dict[str, Any] = {}
    evidence: list[dict[str, Any]] = []

    def record(name: str, levels: dict[str, Any]) -> None:
        low, high = levels["low"]["report_rate"], levels["high"]["report_rate"]
        evidence.append({"factor": name, "levels": levels, "lines_up": None if low is None or high is None else bool(high > low)})

    for name in WEATHER_FACTORS:  # one value per (station, Monday)
        values = np.asarray(store.a[f"weather__{name}"], dtype=float)[:, weeks]
        use = values[:, winter] if name in WINTER_ONLY else values
        flat = use[~np.isnan(use)]
        unit = FACTORS[name][1]
        cut = {"medium": nice(np.percentile(flat, 75), unit), "high": nice(np.percentile(flat, 95), unit)}
        if cut["high"] <= cut["medium"]:
            cut["high"] = cut["medium"] + 1
        cutoffs[name] = cut
        idx = np.stack([levels_array(name, values[s], cutoffs) for s in range(values.shape[0])])
        record(name, level_counts(idx.ravel(), pos_sw.ravel(), rows_sw.ravel()))

    positives = labels.sum(axis=0, dtype=np.int64).astype(float)  # per section: Mondays followed by a report
    rows = np.full(len(positives), float(len(weeks)))
    bridge = np.asarray(store.a["static__probably_bridge"])[keep] > 0
    for name in ("low_spot_m", "slope_pct"):
        values = np.asarray(store.a[f"static__{name}"], dtype=float)[keep].copy()
        values[bridge] = np.nan  # a bridge is not a dip or a hill
        flat = values[~np.isnan(values)]
        if name == "low_spot_m":
            cutoffs[name] = {"medium": nice(np.percentile(flat, 10), "m"), "high": nice(np.percentile(flat, 2), "m")}
        else:
            cutoffs[name] = {"medium": nice(np.percentile(flat, 75), "%"), "high": nice(np.percentile(flat, 95), "%")}
        record(name, level_counts(levels_array(name, values, cutoffs), positives, rows))
    f1 = np.asarray(store.a["static__flood_1pct"], dtype=float)[keep]
    f02 = np.asarray(store.a["static__flood_02pct"], dtype=float)[keep]
    flood = np.where(np.isnan(f1), np.nan, np.where(f1 > 0, 2.0, np.where(f02 > 0, 1.0, 0.0)))
    record("flood_zone", level_counts(levels_array("flood_zone", flood, cutoffs), positives, rows))
    for name in ("traffic_band", "heavy_vehicle_band", "bus_routes"):
        values = np.asarray(store.a[f"static__{name}"], dtype=float)[keep]
        record(name, level_counts(levels_array(name, values, cutoffs), positives, rows))
    return cutoffs, evidence, float(labels.mean())


def write_cutoffs_draft(cutoffs: dict[str, Any], evidence: list[dict[str, Any]], base_rate: float, out_yaml: Path, out_md: Path) -> None:
    meta = {
        "status": "DRAFT",  # becomes APPROVED only after the owner has read the draft report (decision D5)
        "drafted": date.today().isoformat(),
        "drafted_from": "Chicago training Mondays (2012-01-02 to 2021-05-31), held-out areas left out",
        "rule": "medium = 75th, high = 95th percentile (dips: 10th and 2nd); freeze, frost and snow on Nov-Apr Mondays",
        "fixed_levels": "flood zone, traffic, heavy vehicles and bus routes use fixed levels (see risk_factors.py)",
    }
    out_yaml.write_text(
        "# Level 1 risk-factor cut-offs (any-area plan FA3, owner decision D5). Written by `forecasting.run risk-cutoffs-draft`.\n"
        "# Levels are plain labels, never a percentage. Change `status` to APPROVED only with the owner's OK (decisions log).\n"
        + yaml.safe_dump(
            {
                **meta,
                # Owner decision D5 (2026-10-30): factors linked to more reports in Chicago are risk warnings; the others
                # are shown as plain background information, without a warning level.
                "risk_factors": [row["factor"] for row in evidence if row["lines_up"]],
                "background": [row["factor"] for row in evidence if not row["lines_up"]],
                "cutoffs": cutoffs,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    lines = [
        "# Level 1 risk factors: DRAFT cut-offs (Chicago training years)",
        "",
        f"Drafted {meta['drafted']} from {meta['drafted_from']}. Rule: {meta['rule']}.",
        "Each factor is shown as low / medium / high. **No percentage is ever shown for a Level 1 area.**",
        "",
        "The last columns show how often a new pothole report followed within 30 days in Chicago at each level. "
        "'Lines up' means the high level was followed by reports more often than the low level.",
        "",
        "| Factor | Medium from | High from | Share low / medium / high / missing | Report rate low / medium / high | Lines up |",
        "|---|---|---|---|---|---|",
    ]
    for row in evidence:
        name, lv = row["factor"], row["levels"]
        words, unit, _ = FACTORS[name]
        cut = cutoffs.get(name)
        medium = f"{cut['medium']} {unit}".strip() if cut else "fixed"
        high = f"{cut['high']} {unit}".strip() if cut else "fixed"
        shares = " / ".join(f"{100 * lv[k]['share']:.0f}%" for k in ("low", "medium", "high", "missing"))
        rates = " / ".join("–" if lv[k]["report_rate"] is None else f"{100 * lv[k]['report_rate']:.1f}%" for k in LEVELS)
        lines_up = {True: "yes", False: "**no**", None: "–"}[row["lines_up"]]
        lines.append(f"| {words} | {medium} | {high} | {shares} | {rates} | {lines_up} |")
    lines += [
        "",
        f"On average {100 * base_rate:.1f}% of section-Mondays in these years were followed by a new report within 30 days.",
        "",
        "A factor that does **not** line up in Chicago should be shown with care or left out; Claude and the owner decide.",
        "To approve: the owner says so, the decision is logged, and `status` in `config/risk-factors.yaml` becomes APPROVED.",
        "",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")


# ---------- computing the factors for an area ----------

SECTIONS_SQL = """
SELECT s.section_id, s.highway, s.length_m, t.low_spot_m, t.slope_pct, t.flood_1pct, t.flood_02pct, t.aadt, t.hcv_aadt,
       t.bus_routes,
       (SELECT w.station_id FROM weather_stations w
        ORDER BY ST_Distance(w.geom::geography, ST_LineInterpolatePoint(s.geom, 0.5)::geography, false), w.station_id LIMIT 1)
FROM road_sections s LEFT JOIN section_static t USING (section_id)
ORDER BY s.section_id
"""

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS section_risk_factors (
    section_id text NOT NULL REFERENCES road_sections (section_id) ON DELETE CASCADE,
    as_of date NOT NULL,                 -- weather counts only days before this day
    factor text NOT NULL,
    value real,                          -- NULL = missing (never guessed)
    level text NOT NULL CHECK (level IN ('low', 'medium', 'high', 'missing')),
    PRIMARY KEY (section_id, as_of, factor)
);
-- 'risk' = linked to more pothole reports in Chicago (a warning); 'background' = shown as information only (D5)
ALTER TABLE section_risk_factors ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'risk' CHECK (kind IN ('risk', 'background'));
"""


def weather_at(conn: psycopg.Connection, stations: list[str], as_of: date) -> dict[str, dict[str, float]]:
    """Weather factors per station for one day (counting only the days before it)."""
    first = day_number(as_of) - 400
    rows = conn.execute(
        "SELECT station_id, (date - DATE '1970-01-01'), tmax_c, tmin_c, prcp_mm, snow_mm FROM weather_daily WHERE date >= %s AND date < %s",
        (EPOCH + timedelta(days=first), as_of),
    ).fetchall()
    total = day_number(as_of) - first
    daily = {s: {k: np.full(total, np.nan) for k in ("tmax", "tmin", "prcp", "snow")} for s in stations}
    for station, day, *values in rows:
        if station in daily:
            for key, value in zip(("tmax", "tmin", "prcp", "snow"), values, strict=True):
                if value is not None:
                    daily[station][key][day - first] = value
    out = {}
    for station in stations:
        features = weather_features(daily[station], first, np.array([day_number(as_of)], dtype=np.int32))
        out[station] = {name: float(features[name][0]) for name in WEATHER_FACTORS}
    return out


def latest_weather_day(conn: psycopg.Connection) -> date | None:
    row = conn.execute("SELECT max(date) FROM weather_daily WHERE tmax_c IS NOT NULL AND tmin_c IS NOT NULL").fetchone()
    return row[0] if row else None


def band(value: Any, edges: list[float]) -> float:
    from forecasting.f2_build import band as f2_band

    return float(f2_band(value, edges))


def compute(
    conn: psycopg.Connection,
    src: dict[str, Any],
    cfg: dict[str, Any],
    cutoffs: dict[str, Any],
    as_of: date | None = None,
    background: tuple[str, ...] | list[str] = (),
):
    """Rows (section_id, as_of, factor, value, level, kind) for every section, and a summary for the report."""
    last = latest_weather_day(conn)
    as_of = as_of or (last + timedelta(days=1) if last else date.today())
    sections = conn.execute(SECTIONS_SQL).fetchall()
    stations = [row[0] for row in conn.execute("SELECT station_id FROM weather_stations ORDER BY station_id")]
    weather = weather_at(conn, stations, as_of) if stations else {}
    snow_station = src.get("snow_station")
    rows: list[tuple] = []
    for section_id, _highway, _length, low, slope, f1, f02, aadt, hcv, bus, station in sections:
        bridge = (slope is not None and slope > 10) or (low is not None and abs(low) > 5)  # same rule as F2
        w = weather.get(station, {})
        values = {
            "freeze_thaw_14d": w.get("freeze_thaw_14d"),
            "below_freezing_days_30d": w.get("below_freezing_days_30d"),
            "heavy_rain_days_30d": w.get("heavy_rain_days_30d"),
            "snow_mm_30d": weather.get(snow_station, w).get("snow_mm_30d") if snow_station else w.get("snow_mm_30d"),
            "low_spot_m": None if bridge else low,
            "slope_pct": None if bridge else slope,
            "flood_zone": None if f1 is None else (2.0 if f1 else 1.0 if f02 else 0.0),
            "traffic_band": band(aadt, cfg["traffic_bands"]) if "traffic_counts" in src else None,
            "heavy_vehicle_band": band(hcv, cfg["heavy_vehicle_bands"]) if "traffic_counts" in src else None,
            "bus_routes": None if bus is None else float(bus),
        }
        for name, value in values.items():
            value = None if value is None or (isinstance(value, float) and np.isnan(value)) else float(value)
            kind = "background" if name in background else "risk"
            rows.append((section_id, as_of, name, value, level_of(name, value, cutoffs), kind))
    return rows, {"as_of": str(as_of), "weather_up_to": str(last) if last else None, "stations": stations, "sections": len(sections)}


def save(conn: psycopg.Connection, rows: list[tuple]) -> None:
    conn.execute(TABLE_SQL)
    if rows:
        conn.execute("DELETE FROM section_risk_factors WHERE as_of = %s", (rows[0][1],))
    with conn.cursor().copy("COPY section_risk_factors (section_id, as_of, factor, value, level, kind) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)


def summary_table(rows: list[tuple]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {name: dict.fromkeys(["high", "medium", "low", "missing"], 0) for name in FACTORS}
    for row in rows:
        counts[row[2]][row[4]] += 1
    return counts


def report_markdown(
    area_name: str,
    info: dict[str, Any],
    counts: dict[str, dict[str, int]],
    cutoffs_meta: dict[str, Any],
    extra: list[str],
    background: tuple[str, ...] | list[str] = (),
) -> str:
    status = cutoffs_meta.get("status", "DRAFT")
    lines = [
        f"# Level 1 risk factors: {area_name} (TRIAL)",
        "",
        *(
            [f"**The cut-offs are a {status} (drafted {cutoffs_meta.get('drafted')}); they are not approved by the owner yet.**", ""]
            if status != "APPROVED"
            else []
        ),
        "These are **risk factors, not a forecast**: there is no pothole history here, so no chance (percentage) can be "
        "tested and none is shown. A high factor means a known cause of potholes is present, not that a pothole exists.",
        "",
        f"As of {info['as_of']} (weather up to {info['weather_up_to']}; stations: {', '.join(info['stations']) or 'none'}). "
        f"{info['sections']:,} road sections.",
        "",
        "## Risk factors (linked to more pothole reports in Chicago)",
        "",
        "| Factor | High | Medium | Low | Missing |",
        "|---|---|---|---|---|",
    ]
    for name, c in counts.items():
        if name not in background:
            lines.append(f"| {FACTORS[name][0]} | {c['high']:,} | {c['medium']:,} | {c['low']:,} | {c['missing']:,} |")
    if background:
        lines += [
            "",
            "## Background information (no link to more reports found in Chicago; shown without a warning)",
            "",
            "Useful local facts, but in Chicago's data these were not followed by more pothole reports, so they are not "
            "treated as warnings. Counts of road sections in the upper / middle / lower group:",
            "",
            "| Fact | Upper | Middle | Lower | Missing |",
            "|---|---|---|---|---|",
        ]
        for name in background:
            c = counts[name]
            lines.append(f"| {FACTORS[name][0]} | {c['high']:,} | {c['medium']:,} | {c['low']:,} | {c['missing']:,} |")
    lines += ["", *extra, ""]
    return "\n".join(lines)


def run(conn: psycopg.Connection, src: dict[str, Any], cfg: dict[str, Any], reports_dir: Path, extra: list[str] | None = None) -> Path:
    data = read_cutoffs()
    background = list(data.get("background", []))
    rows, info = compute(conn, src, cfg, data["cutoffs"], background=background)
    save(conn, rows)
    counts = summary_table(rows)
    reports_dir.mkdir(parents=True, exist_ok=True)
    meta = {k: v for k, v in data.items() if k != "cutoffs"}
    (reports_dir / "level1-risk-factors.json").write_text(
        json.dumps({"info": info, "counts": counts, "cutoffs": data}, indent=2, default=str), encoding="utf-8"
    )
    path = reports_dir / "level1-risk-factors.md"
    path.write_text(report_markdown(src.get("area_name", ""), info, counts, meta, extra or [], background), encoding="utf-8")
    return path
