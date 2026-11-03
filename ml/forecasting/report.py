"""F1 step 4: counts and checks on an area's loaded data (areas with pothole history), written to
reports/<area>/f1-data-report.md (+ .json).

The locked test period (F0 section 5) is not analysed here: only its total number of reports is shown, so no
choice in F2 can be influenced by test-period patterns.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import psycopg

USABLE = "NOT is_duplicate AND geom IS NOT NULL"


def range_sql(label: str, column: str, digits: int) -> str:
    """Min, median, 95th percentile and max of one section_static column (names are constants from this file)."""

    def rounded(expr: str) -> str:
        return f"round(({expr})::numeric, {digits})"

    return (
        f"SELECT '{label}', {rounded(f'min({column})')}, {rounded(f'percentile_cont(0.5) WITHIN GROUP (ORDER BY {column})')}, "  # noqa: S608
        f"{rounded(f'percentile_cont(0.95) WITHIN GROUP (ORDER BY {column})')}, {rounded(f'max({column})')} FROM section_static"
    )


def gather(
    conn: psycopg.Connection, rules: dict[str, Any], switch_date: date, match_m: float, traffic_max_year: int = 2021
) -> dict[str, Any]:
    test_start = date.fromisoformat(str(rules["periods"]["test_locked"]["start"]))

    def rows(query: str, params: tuple = ()) -> list[tuple]:
        return conn.execute(query, params or None).fetchall()  # no params: "%" in text is literal

    def one(query: str, params: tuple = ()) -> Any:
        return conn.execute(query, params or None).fetchone()[0]

    load = rows("SELECT loaded_at::text, osm_extract_date, details FROM load_log ORDER BY id DESC LIMIT 1")
    if not load:
        raise SystemExit("Nothing loaded yet. Run `python -m forecasting.run load` first.")
    loaded_at, extract_date, details = load[0]

    sections = {
        "count": one("SELECT count(*) FROM road_sections"),
        "km": round(one("SELECT coalesce(sum(length_m), 0) FROM road_sections") / 1000, 1),
        "length_m_min_median_max": rows(
            "SELECT round(min(length_m)::numeric, 1), round((percentile_cont(0.5) WITHIN GROUP (ORDER BY length_m))::numeric, 1), "
            "round(max(length_m)::numeric, 1) FROM road_sections"
        )[0],
        "by_highway": rows(
            "SELECT highway, count(*), round(sum(length_m)::numeric / 1000, 1) FROM road_sections GROUP BY 1 ORDER BY 2 DESC"
        ),
        "with_lanes_tag_pct": one("SELECT round(100.0 * avg((lanes IS NOT NULL)::int), 1) FROM road_sections"),
        "with_surface_tag_pct": one("SELECT round(100.0 * avg((surface IS NOT NULL)::int), 1) FROM road_sections"),
        "held_out_areas": rows(
            "SELECT a.area_number, a.name, count(s.*) FROM community_areas a LEFT JOIN road_sections s ON s.community_area = a.area_number "
            "WHERE a.held_out GROUP BY 1, 2 ORDER BY 1"
        ),
    }

    potholes = {
        "by_source": rows(
            "SELECT source, count(*), sum(is_duplicate::int), count(*) FILTER (WHERE location_issue = 'missing'), "
            "count(*) FILTER (WHERE location_issue LIKE 'outside%'), min(created_at)::date::text, max(created_at)::date::text "
            "FROM pothole_reports GROUP BY 1 ORDER BY 1"
        ),
        "by_year_before_test": rows(
            f"SELECT extract(year FROM created_at)::int::text, count(*), sum(is_duplicate::int), sum(({USABLE})::int) "  # noqa: S608 (constant)
            "FROM pothole_reports WHERE created_at < %s GROUP BY 1 ORDER BY 1",
            (test_start,),
        ),
        "test_period_total_only": one("SELECT count(*) FROM pothole_reports WHERE created_at >= %s", (test_start,)),
    }

    # F0 section 5: are counts comparable across the 311 system change? Two years either side, same calendar dates.
    before = (date(switch_date.year - 2, switch_date.month, switch_date.day), switch_date)
    after = (switch_date, date(switch_date.year + 2, switch_date.month, switch_date.day))
    switch = {}
    for label, (start, end) in (("before", before), ("after", after)):
        total, dups, usable = rows(
            f"SELECT count(*), sum(is_duplicate::int), sum(({USABLE})::int) FROM pothole_reports "  # noqa: S608 (constant)
            "WHERE created_at >= %s AND created_at < %s",
            (start, end),
        )[0]
        weeks = (end - start).days / 7
        switch[label] = {
            "from": str(start),
            "to": str(end),
            "usable_per_week": round((usable or 0) / weeks, 1),
            "duplicate_pct": round(100 * (dups or 0) / total, 1) if total else None,
        }
    if switch["before"]["usable_per_week"]:
        switch["after_to_before_ratio"] = round(switch["after"]["usable_per_week"] / switch["before"]["usable_per_week"], 2)

    coverage = rows(
        f"SELECT count(*), count(*) FILTER (WHERE EXISTS (SELECT 1 FROM road_sections s "  # noqa: S608 (constant)
        "WHERE ST_DWithin(s.geom::geography, p.geom::geography, %s))) "
        f"FROM pothole_reports p WHERE {USABLE} AND created_at < %s",
        (match_m, test_start),
    )[0]

    weather = {
        "stations": rows(
            "SELECT station_id, min(date)::text, max(date)::text, count(*), "
            "round(100.0 * avg((tmax_c IS NULL)::int), 1), round(100.0 * avg((tmin_c IS NULL)::int), 1), "
            "round(100.0 * avg((prcp_mm IS NULL)::int), 1), round(100.0 * avg((snow_mm IS NULL)::int), 1) "
            "FROM weather_daily WHERE date < %s GROUP BY 1 ORDER BY 1",
            (test_start,),
        ),
        "freeze_thaw_days_per_winter": rows(
            "SELECT station_id, (extract(year FROM date - interval '6 months'))::int::text AS winter_start, "
            "sum((tmax_c > 0 AND tmin_c < 0)::int) FROM weather_daily "
            "WHERE extract(month FROM date) IN (11, 12, 1, 2, 3, 4) AND date < %s GROUP BY 1, 2 ORDER BY 1, 2",
            (test_start,),
        ),
    }

    cook_pci = {
        "by_township": rows(
            "SELECT township, count(*), round((sum(ST_Length(geom::geography)) / 1000)::numeric, 1), count(pci), "
            "round(min(pci)::numeric, 1), round((percentile_cont(0.5) WITHIN GROUP (ORDER BY pci))::numeric, 1), "
            "round(max(pci)::numeric, 1) "
            "FROM pavement_condition_cook GROUP BY 1 ORDER BY 1"
        ),
        "pieces_inside_chicago": one(
            "SELECT count(*) FROM pavement_condition_cook p WHERE EXISTS "
            "(SELECT 1 FROM community_areas a WHERE ST_Intersects(a.geom, p.geom))"
        ),
    }

    max_year = int(traffic_max_year)
    total, *counts = rows(
        "SELECT count(*), count(elev_mid_m), count(slope_pct), count(low_spot_m), count(flood_1pct), "
        "count(*) FILTER (WHERE flood_1pct), count(*) FILTER (WHERE flood_02pct), count(soil_drainage_rank), "
        "count(*) FILTER (WHERE soil_urban_land), count(aadt), count(aadt) FILTER (WHERE aadt_year <= %s), count(hcv_aadt), "
        "count(bus_routes), count(*) FILTER (WHERE bus_routes > 0) FROM section_static",
        (max_year,),
    )[0]
    names = [
        "Elevation (middle)",
        "Slope",
        "Low spot",
        "Flood zone answered",
        "In 1% flood zone",
        "In 0.2% flood zone",
        "Soil drainage class",
        "Soil mapped as urban land",
        "Traffic count (any year)",
        "Traffic count used in F2" + (" (any year, as a busy-ness level)" if max_year >= 9999 else f" (dated {max_year} or earlier)"),
        "Heavy-vehicle count",
        "Bus routes answered",
        "On at least one bus route",
    ]
    static_layers = {
        "sections": total,
        "coverage": [(name, value, round(100 * value / total, 1) if total else 0) for name, value in zip(names, counts, strict=True)],
        "ranges": rows(
            " UNION ALL ".join(
                range_sql(label, column, digits)
                for label, column, digits in (
                    ("slope %", "slope_pct", 2),
                    ("low spot m", "low_spot_m", 2),
                    ("elevation m", "elev_mid_m", 1),
                    ("vehicles per day", "aadt", 0),
                )
            )
        ),
        "traffic_years": rows(
            "SELECT aadt_year::text, count(*) FROM section_static WHERE aadt IS NOT NULL GROUP BY aadt_year ORDER BY aadt_year"
        ),
        "soil_classes": rows("SELECT coalesce(soil_drainage, '(none)'), count(*) FROM section_static GROUP BY 1 ORDER BY 2 DESC"),
        "used": details.get("static_layers", {}),
        "max_count_year": max_year,
    }

    return {
        "loaded_at": loaded_at,
        "osm_extract_date": extract_date,
        "load_details": details,
        "sections": sections,
        "potholes": potholes,
        "system_switch": switch,
        "coverage": {"usable_reports_before_test": coverage[0], f"within_{int(match_m)}m_of_a_section": coverage[1]},
        "weather": weather,
        "cook_county_pci": cook_pci,
        "static_layers": static_layers,
    }


def table(header: list[str], body: list[tuple] | list[list]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join("" if v is None else f"{v:,}" if isinstance(v, int) else str(v) for v in row) + " |" for row in body]
    return "\n".join(lines)


def to_markdown(r: dict[str, Any], manifest: dict[str, Any], place: str = "Chicago") -> str:
    s, p, sw, cov, w = r["sections"], r["potholes"], r["system_switch"], r["coverage"], r["weather"]
    usable, within = list(cov.values())
    lmin, lmed, lmax = s["length_m_min_median_max"]
    parts = [
        f"# F1 data report ({place})",
        "",
        f"Generated from the `forecast` database loaded at {r['loaded_at']}. OpenStreetMap extract: {r['osm_extract_date']}.",
        "Machine-readable copy: `f1-data-report.json`. The locked test period is not analysed (only its total is shown).",
        "",
        "## Sources",
        table(
            ["Name", "Downloaded (UTC)", "Rows", "MB", "SHA-256 (first 12)", "Licence"],
            [
                (name, m["downloaded_at"], m.get("rows"), round(m["bytes"] / 1e6, 1), m["sha256"][:12], m["licence"])
                for name, m in sorted(manifest.items())
            ],
        ),
        "",
        "## Road sections",
        f"{s['count']:,} sections, {s['km']:,} km. Length min / median / max: {lmin} / {lmed} / {lmax} m. "
        f"Lanes tagged: {s['with_lanes_tag_pct']}%, surface tagged: {s['with_surface_tag_pct']}%.",
        "",
        table(["Road type", "Sections", "km"], s["by_highway"]),
        "",
        "Building steps: " + ", ".join(f"{k.replace('_', ' ')}: {v:,}" for k, v in r["load_details"]["sections"].items()),
        "",
        "Held-out community areas (place check, never used in training):",
        "",
        table(["Area", "Name", "Sections"], s["held_out_areas"]),
        "",
        "## 311 pothole reports",
        table(["Source", "Rows", "Duplicates", "No location", "Outside the area's box", "First", "Last"], p["by_source"]),
        "",
        table(["Year (before test period)", "Reports", "Duplicates", "Usable (not duplicate, located)"], p["by_year_before_test"]),
        "",
        f"Locked test period: {p['test_period_total_only']:,} reports in total (not analysed).",
        "",
        "### 311 system change (2018-12-18)",
        table(
            ["Window", "From", "To", "Usable reports per week", "Duplicates %"],
            [(k, v["from"], v["to"], v["usable_per_week"], v["duplicate_pct"]) for k, v in sw.items() if isinstance(v, dict)],
        ),
        "",
        f"After / before ratio: {sw.get('after_to_before_ratio')}. Weather and the 2020 pandemic also change counts, "
        "so this is a warning sign to read, not a pass/fail test.",
        "",
        "### Coverage",
        f"{within:,} of {usable:,} usable reports before the test period ({round(100 * within / usable, 1) if usable else 0}%) "
        "lie within the label distance of a section. Reports farther away are on excluded roads (expressways, alleys) or mislocated.",
        "",
        "## Weather (before the test period)",
        table(["Station", "First", "Last", "Days", "TMAX missing %", "TMIN missing %", "PRCP missing %", "SNOW missing %"], w["stations"]),
        "",
        table(["Station", "Winter starting", "Freeze-thaw days (Nov-Apr)"], w["freeze_thaw_days_per_winter"]),
        "",
        "## Cook County pavement condition, 2025 (checking only)",
        "Team lead's suggestion. One survey year, six suburban townships, no licence stated: used only to check the photo AI and "
        "the forecast (F3), never as a training label or in the product until CCDOTH agrees in writing.",
        "",
        table(["Township", "Road pieces", "km", "With PCI", "PCI min", "PCI median", "PCI max"], r["cook_county_pci"]["by_township"])
        if r["cook_county_pci"]["by_township"]
        else "Not downloaded yet.",
        "",
        f"Road pieces inside the City of Chicago: {r['cook_county_pci']['pieces_inside_chicago']:,} "
        "(Lake Township covers much of Chicago's south-west side, so these can check the Chicago forecast).",
        "",
        "## Static layers (F1b)",
        f"{r['static_layers']['sections']:,} sections. Missing values stay missing (flagged), never guessed.",
        "",
        table(["Input", "Sections with a value", "%"], r["static_layers"]["coverage"]),
        "",
        table(["Value", "Min", "Median", "95th percentile", "Max"], r["static_layers"]["ranges"]),
        "",
        "Traffic count years (F2 uses the latest count of any year as a busy-ness level, owner decision B, and is also trained without it):"
        if r["static_layers"]["max_count_year"] >= 9999
        else f"Traffic count years (F2 uses only counts dated {r['static_layers']['max_count_year']} or earlier):",
        "",
        table(["Count year", "Sections"], r["static_layers"]["traffic_years"])
        if r["static_layers"]["traffic_years"]
        else "No traffic counts loaded.",
        "",
        table(["Soil drainage class", "Sections"], r["static_layers"]["soil_classes"]),
        "",
        f"Layers loaded and soil rule: `{json.dumps(r['static_layers']['used'])}`",
        "",
        "## Counts while loading",
        table(["Item", "Count"], sorted(r["load_details"]["counts"].items())),
        "",
    ]
    return "\n".join(parts)


def write_report(conn: psycopg.Connection, rules: dict[str, Any], src: dict[str, Any], manifest: dict[str, Any], out_dir: Path) -> Path:
    switch_date = date.fromisoformat(str(src["system_switch_date"]))
    traffic_max_year = src.get("traffic_counts", {}).get("max_count_year") or 9999  # null = any year (owner decision B)
    result = gather(conn, rules, switch_date, rules["target"]["match_distance_m"], traffic_max_year)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "f1-data-report.json").write_text(
        json.dumps({"report": result, "sources": manifest}, indent=2, default=str), encoding="utf-8"
    )
    path = out_dir / "f1-data-report.md"
    place = "Chicago" if src.get("area_key", "chicago") == "chicago" else src.get("area_name", src.get("area_key"))
    path.write_text(to_markdown(result, manifest, place), encoding="utf-8")
    return path
