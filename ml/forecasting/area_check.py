"""`area-check`: what data an area has, in plain words, and whether it gets Level 1 (risk factors) or Level 2 too.

Steps: download the boundary (areas without districts), choose weather stations (areas with `weather_stations: auto`,
rule D3), download the roads and count the sections. Nothing else large is downloaded; `download` does the rest and
skips what is already there. Writes reports/<area>/area-check.md (+ .json).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from forecasting import areas, download, settings
from forecasting.sections import sections_from_file


def area_km2(raw_dir: Path, crs: str) -> float | None:
    path = raw_dir / areas.BOUNDARY_FILE
    if not path.exists():
        return None
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform

    geometry = shape(json.loads(path.read_text(encoding="utf-8"))["features"][0]["geometry"])
    to_m = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    return round(transform(to_m, geometry).area / 1e6, 1)


def run(area: areas.Area, rules: dict[str, Any], terms_confirmed: bool, session=None, today: date | None = None) -> Path:
    from forecasting import stations as station_choice

    session = session or download.new_session()
    raw = area.raw_dir
    src = area.src
    if "districts" not in src:
        download.download_all(
            raw,
            dict(src, weather=dict(src["weather"], stations=[])),
            rules,
            terms_confirmed=terms_confirmed,
            only="boundary",
            session=session,
        )
    src = areas.ready_sources(area)
    choice = None
    if area.src["weather"]["stations"] == "auto":
        print("- weather stations: choosing (rule D3)", flush=True)
        choice = station_choice.run_station_choice(raw, settings.FORECAST_DIR / "data" / "_national", src, session, today)
        src = areas.ready_sources(area)
    download.download_all(raw, src, rules, terms_confirmed=terms_confirmed, only="osm_roads", session=session)
    sec = rules["sections"]
    sections, stats, extract = sections_from_file(raw / "osm_roads.json", sec["length_m"], sec["min_end_piece_m"], src["projected_crs"])
    weather_ok = bool(src["weather"]["stations"])
    result = {
        "area": area.key,
        "name": area.name,
        "level": 2 if area.has_potholes else 1,
        "schema": area.schema,
        "map_zone": src["projected_crs"],
        "box": src["bbox"],
        "area_km2": area_km2(raw, src["projected_crs"]),
        "osm_extract": extract,
        "sections_before_boundary_cut": len(sections),
        "km_before_boundary_cut": round(sum(s.length_m for s in sections) / 1000, 1),
        "weather": {"stations": src["weather"]["stations"], "snow_station": src.get("snow_station"), "choice": choice},
        "layers": {
            "pothole history (Level 2)": area.has_potholes or "city_potholes" in area.src,  # city connector (step C)
            "weather (freeze-thaw, rain, snow)": weather_ok,
            "elevation (USGS, national)": "elevation" in src,
            "flood zones (FEMA, national)": "flood_zones" in src,
            "soil (USDA, national)": "soils" in src,
            "traffic counts": "traffic_counts" in src,
            "bus routes": "bus_routes" in src,
        },
    }
    area.reports_dir.mkdir(parents=True, exist_ok=True)
    (area.reports_dir / "area-check.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    path = area.reports_dir / "area-check.md"
    path.write_text(markdown(result), encoding="utf-8")
    return path


def markdown(r: dict[str, Any]) -> str:
    level = (
        "**Level 2** (has pothole history: a tested forecast is possible) and Level 1"
        if r["level"] == 2
        else "**Level 1 only** (risk factors; no pothole history, so no tested percentage)"
    )
    lines = [
        f"# Area check: {r['name']}",
        "",
        f"Result: {level}.",
        "",
        f"- Map zone for measuring meters: {r['map_zone']}; box: {r['box']}"
        + (f"; area inside the boundary: {r['area_km2']:,} km²" if r["area_km2"] else ""),
        f"- Roads (OpenStreetMap extract {r['osm_extract']}): {r['sections_before_boundary_cut']:,} sections, "
        f"{r['km_before_boundary_cut']:,} km before roads outside the boundary are removed at load.",
        "",
        "## Data available",
        "",
        "| Layer | Available |",
        "|---|---|",
        *[f"| {name} | {'yes' if ok else 'no (shown as missing)'} |" for name, ok in r["layers"].items()],
        "",
        "## Weather stations",
        "",
    ]
    stations = r["weather"]["stations"] or []
    lines += [f"- {s['id']} {s['name']}" for s in stations] or ["- **None passed the rule**: weather factors are shown as missing."]
    lines.append(f"- Snow from: {r['weather']['snow_station'] or 'no station with a snow record'}")
    choice = r["weather"]["choice"]
    if choice:
        rule = choice["rule"]
        lines += [
            "",
            f"Rule D3: within {rule['max_distance_km']} km of the area's box, at least {int(100 * rule['min_complete_share'])}% of days "
            f"with temperature and with rain, {choice['measured_from']} to {choice['measured_to']}. "
            f"{choice['candidates_found']} candidates found; the nearest {len(choice['measured'])} were measured:",
            "",
            "| Station | Name | Distance (km) | Temperature days | Rain days | Snow days | Chosen |",
            "|---|---|---|---|---|---|---|",
        ]
        chosen = {s["id"] for s in stations}
        for s in choice["measured"]:
            share = s["share"]
            lines.append(
                f"| {s['id']} | {s['name'].title()} | {s['distance_km']} | {100 * share['temperature']:.0f}% | "
                f"{100 * share['rain']:.0f}% | {100 * share['snow']:.0f}% | {'yes' if s['id'] in chosen else ''} |"
            )
    lines.append("")
    return "\n".join(lines)
