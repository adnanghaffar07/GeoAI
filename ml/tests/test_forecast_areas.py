"""Any-area pipeline (plan: documentation/04-design/forecasting-any-area-plan.md): area files, Chicago unchanged,
boundary and station choice, the one-time move, Level 1 risk factors and the same-results comparison.

Database parts run only when FORECAST_TEST_DATABASE_URL is set (a database that may be dropped and re-created).
"""

from __future__ import annotations

import csv
import json
import os
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
import yaml

from forecasting import areas, download, migrate, risk_factors, settings, stations

DATA = Path(__file__).parent / "data"
RULES = settings.rules()
TEST_DB = os.environ.get("FORECAST_TEST_DATABASE_URL")


# ---------- Chicago gives the same settings as before the change ----------


def test_chicago_area_file_matches_the_old_sources_file():
    old = yaml.safe_load((DATA / "sources-before-any-area.yaml").read_text(encoding="utf-8"))
    new = areas.sources_for("chicago")
    renamed = {"chicago_portal": "portal", "chicago_bbox": "bbox", "community_areas": "districts"}
    for key, value in old.items():
        if key == "study_area":
            continue
        got = new[renamed.get(key, key)]
        if key == "community_areas":
            got = {k: v for k, v in got.items() if k not in ("expected_count", "held_out")}
        if key == "weather":
            got = {k: v for k, v in got.items() if k not in ("station_list_url", "inventory_url")}
        if key == "osm":
            got = {("city_area_filter" if k == "osm_area_filter" else k): v for k, v in got.items()}
        if key == "traffic_counts":
            got = {("limit_to_chicago_box" if k == "limit_to_area_box" else k): v for k, v in got.items()}
        assert got == value, key
    assert new["projected_crs"] == "EPSG:26916" and new["level"] == 2 and new["schema"] == "chicago"
    assert new["snow_station"] == settings.load_config("f2.yaml")["snow_station"] == "USW00094846"
    assert settings.load_config("f2.yaml") == yaml.safe_load((DATA / "f2-before-any-area.yaml").read_text(encoding="utf-8"))


def test_chicago_road_query_is_exactly_the_old_one():
    jobs = download.plan_downloads(areas.sources_for("chicago"), RULES)
    assert [j["name"] for j in jobs][:6] == [
        "potholes_historical",
        "potholes_current",
        "community_areas",
        "weather_USW00094846",
        "weather_USW00014819",
        "osm_roads",
    ]
    query = next(j for j in jobs if j["name"] == "osm_roads")["query"]
    assert query == (
        "[out:json][timeout:900];\n"
        'area["wikidata"="Q1297"]["boundary"="administrative"]->.city;\n'
        'way(area.city)["highway"~"^(primary|secondary|tertiary|residential|unclassified|primary_link|secondary_link|tertiary_link)$"]'
        '["area"!="yes"]["access"!~"^(private|no)$"];\n'
        "out body;\n>;\nout skel qt;\n"
    )


def test_map_zone_from_the_centre():
    assert areas.utm_crs(-87.7, 41.8) == "EPSG:26916"  # Chicago
    assert areas.utm_crs(-88.15, 41.75) == "EPSG:26916"  # Naperville
    assert areas.utm_crs(-122.4, 37.7) == "EPSG:26910"  # San Francisco
    with pytest.raises(SystemExit):
        areas.utm_crs(10.0, 50.0)  # not a US zone


def test_area_names_are_safe_and_files_are_checked(tmp_path):
    with pytest.raises(SystemExit, match="small letters"):
        areas.check_name("Chicago; DROP")
    (tmp_path / "nowhere.yaml").write_text("name: Nowhere\nlevel: 1\n")
    with pytest.raises(SystemExit, match="boundary"):
        areas.sources_for("nowhere", areas_dir=tmp_path)
    (tmp_path / "fake.yaml").write_text("name: Fake\nlevel: 2\nboundary: {geojson_file: x.geojson}\n")
    with pytest.raises(SystemExit, match="no pothole history"):
        areas.sources_for("fake", areas_dir=tmp_path)


# ---------- a Level 1 area: Naperville ----------


def test_naperville_plan_starts_with_the_boundary_and_needs_the_area_check(tmp_path):
    src = areas.sources_for("naperville")
    jobs = download.plan_downloads(src, RULES)
    assert jobs[0]["name"] == "boundary" and jobs[0]["kind"] == "osm_boundary"
    assert not any(j["portal"] for j in jobs)  # no city portal data for a Level 1 area
    assert {j["name"] for j in jobs} >= {"boundary", "osm_roads", "elevation", "flood_zones", "soils", "traffic_counts"}
    assert "bus_routes" not in {j["name"] for j in jobs} and "potholes_current" not in {j["name"] for j in jobs}
    roads = next(j for j in jobs if j["name"] == "osm_roads")["query"]
    assert 'rel(area.within)["boundary"="administrative"]["admin_level"="8"]["name"="Naperville"]' in roads
    assert "map_to_area->.city" in roads
    with pytest.raises(SystemExit, match="area-check"):
        download.download_all(tmp_path, src, RULES, terms_confirmed=False, session=object())


def square_ways():
    """A 0.01-degree square boundary made of two OpenStreetMap ways (as Overpass returns them with `out geom`)."""
    a, b, c, d = (-88.20, 41.70), (-88.19, 41.70), (-88.19, 41.71), (-88.20, 41.71)

    def way(points):
        return {"type": "way", "role": "outer", "geometry": [{"lon": x, "lat": y} for x, y in points]}

    return {"elements": [{"type": "relation", "id": 7, "tags": {"name": "Squareville"}, "members": [way([a, b, c]), way([c, d, a])]}]}


def test_boundary_from_overpass_and_geojson(tmp_path):
    from shapely.geometry import shape

    data = download.boundary_from_overpass(square_ways())
    geometry = shape(data["features"][0]["geometry"])
    assert geometry.geom_type == "MultiPolygon" and geometry.bounds == (-88.20, 41.70, -88.19, 41.71)
    with pytest.raises(download.SourceChangedError, match="Expected one boundary relation"):
        download.boundary_from_overpass({"elements": []})
    path = tmp_path / "area.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [data["features"][0]]}))
    again = download.boundary_from_geojson(path)
    assert shape(again["features"][0]["geometry"]).equals(geometry)
    src = areas.resolve_after_boundary({"osm": {}}, geometry.bounds)
    assert src["bbox"] == {"min_lon": -88.205, "min_lat": 41.695, "max_lon": -88.185, "max_lat": 41.715}
    assert src["projected_crs"] == "EPSG:26916"


def test_ready_sources_uses_the_station_choice_and_boundary(tmp_path):
    area = areas.load_area("naperville", forecast_dir=tmp_path)
    with pytest.raises(SystemExit, match="not downloaded yet"):
        areas.ready_sources(area)
    assert areas.ready_sources(area, need_box=False)["weather"]["stations"] == "auto"
    area.raw_dir.mkdir(parents=True)
    (area.raw_dir / "boundary.geojson").write_text(json.dumps(download.boundary_from_overpass(square_ways())))
    choice = {"stations": [{"id": "USC00111111", "name": "A", "lat": 41.7, "lon": -88.2}], "snow_station": "USC00111111"}
    (area.raw_dir / "weather_choice.json").write_text(json.dumps(choice))
    src = areas.ready_sources(area)
    assert src["weather"]["stations"] == choice["stations"] and src["snow_station"] == "USC00111111"
    assert src["bbox"]["min_lon"] == -88.205 and src["projected_crs"] == "EPSG:26916"
    assert area.raw_dir == tmp_path / "data" / "naperville" / "raw" and area.reports_dir == tmp_path / "reports" / "naperville"


# ---------- weather station choice (rule D3) ----------

STATIONS_TXT = "\n".join(
    [
        "USW00000001  41.7000  -88.1500  200.0 IL NEAR AIRPORT",
        "USC00000002  41.9000  -88.1500  200.0 IL FARTHER COOP",
        "USC00000003  43.5000  -88.1500  200.0 WI TOO FAR",
        "US1ILDP0004  41.7100  -88.1500  200.0 IL RAIN ONLY",
    ]
)
INVENTORY_TXT = "\n".join(
    [
        f"{sid}  41.0000  -88.0000 {element} {first} {last}"
        for sid, elements in (
            ("USW00000001", ("TMAX", "TMIN", "PRCP", "SNOW")),
            ("USC00000002", ("TMAX", "TMIN", "PRCP", "SNOW")),
            ("USC00000003", ("TMAX", "TMIN", "PRCP")),
            ("US1ILDP0004", ("PRCP",)),
        )
        for element in elements
        for first, last in ((1990, 2026),)
    ]
)


def test_station_lists_and_candidates():
    parsed = stations.parse_station_list(STATIONS_TXT)
    assert parsed["USW00000001"]["lat"] == 41.7 and parsed["USW00000001"]["name"] == "NEAR AIRPORT"
    inventory = stations.parse_inventory(INVENTORY_TXT)
    assert inventory["USW00000001"]["SNOW"] == (1990, 2026)
    bbox = {"min_lon": -88.25, "min_lat": 41.65, "max_lon": -88.10, "max_lat": 41.80}
    cfg = settings.sources()["station_choice"]
    found = stations.candidates(parsed, inventory, bbox, cfg, 2026)
    assert [s["id"] for s in found] == ["USW00000001", "USC00000002"]  # too far and rain-only are left out
    assert found[0]["distance_km"] == 0.0 and 10 < found[1]["distance_km"] < 12


def write_ghcn(path: Path, first: date, days: int, skip_temp_every: int = 0, snow: bool = True) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["STATION", "DATE", "TMAX", "TMAX_ATTRIBUTES", "TMIN", "TMIN_ATTRIBUTES", "PRCP", "PRCP_ATTRIBUTES", "SNOW", "SNOW_ATTRIBUTES"]
        )
        for i in range(days):
            day = first + timedelta(days=i)
            missing = skip_temp_every and i % skip_temp_every == 0
            writer.writerow(["X", day.isoformat(), "" if missing else "10", ",,W", "-20", ",,W", "0", ",,W", "5" if snow else "", ",,W"])


def test_completeness_and_choice(tmp_path):
    first, last = date(2016, 1, 1), date(2025, 12, 31)
    days = (last - first).days + 1
    write_ghcn(tmp_path / "full.csv", first, days)
    write_ghcn(tmp_path / "gappy.csv", first, days, skip_temp_every=5, snow=False)  # 80% temperature days
    full = stations.completeness(tmp_path / "full.csv", first, last)
    gappy = stations.completeness(tmp_path / "gappy.csv", first, last)
    assert full == {"temperature": 1.0, "rain": 1.0, "snow": 1.0}
    assert gappy["temperature"] == 0.8 and gappy["snow"] == 0.0
    measured = [
        {"id": "A", "distance_km": 0.0, "share": gappy},
        {"id": "B", "distance_km": 5.0, "share": {"temperature": 0.95, "rain": 0.99, "snow": 0.4}},
        {"id": "C", "distance_km": 9.0, "share": full},
        {"id": "D", "distance_km": 12.0, "share": full},
        {"id": "E", "distance_km": 20.0, "share": full},
    ]
    chosen, snow = stations.choose(measured, {"min_complete_share": 0.9, "max_stations": 3})
    assert [s["id"] for s in chosen] == ["B", "C", "D"]  # A fails the 90% rule; at most 3, nearest first
    assert snow == "C"  # most complete snow record among the chosen (C and D tie: the nearer one)


# ---------- the one-time move to the per-area layout ----------


def test_move_files_once(tmp_path):
    for path in ("data/raw/a.csv", "data/f2/meta.json", "models/m.txt", "models/work/x.npy", "reports/r.md", "reports/f2-test-work/p.json"):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(path)
    moved = migrate.move_files(tmp_path)
    assert len(moved) == 6
    for path in ("data/chicago/raw/a.csv", "data/chicago/f2/meta.json", "models/chicago/m.txt", "models/chicago/work/x.npy"):
        assert (tmp_path / path).read_text() == path.replace("chicago/", "")  # moved, content unchanged
    assert (tmp_path / "reports/chicago/f2-test-work/p.json").exists() and not (tmp_path / "data/raw").exists()
    assert migrate.move_files(tmp_path) == []  # running again does nothing
    (tmp_path / "data/raw").mkdir()
    (tmp_path / "data/raw/new.csv").write_text("x")
    with pytest.raises(SystemExit, match="Both"):
        migrate.move_files(tmp_path)


# ---------- Level 1 levels and the cut-off draft ----------

CUTOFFS = {
    "freeze_thaw_14d": {"medium": 4, "high": 8},
    "below_freezing_days_30d": {"medium": 5, "high": 12},
    "heavy_rain_days_30d": {"medium": 1, "high": 2},
    "snow_mm_30d": {"medium": 50, "high": 200},
    "low_spot_m": {"medium": -0.5, "high": -1.5},
    "slope_pct": {"medium": 1.0, "high": 3.0},
}


def test_levels():
    level = risk_factors.level_of
    assert [level("freeze_thaw_14d", v, CUTOFFS) for v in (0, 4, 7.9, 8, None)] == ["low", "medium", "medium", "high", "missing"]
    assert [level("low_spot_m", v, CUTOFFS) for v in (0.3, -0.5, -2.0)] == ["low", "medium", "high"]  # dips are negative
    assert [level("flood_zone", v, CUTOFFS) for v in (0, 1, 2)] == ["low", "medium", "high"]
    assert [level("traffic_band", v, CUTOFFS) for v in (0, 1, 3, 4)] == ["missing", "low", "medium", "high"]
    assert [level("bus_routes", v, CUTOFFS) for v in (0, 1, 3, float("nan"))] == ["low", "medium", "high", "missing"]
    assert list(risk_factors.levels_array("slope_pct", np.array([0.5, 2.0, 5.0, np.nan]), CUTOFFS)) == [0, 1, 2, -1]


def test_cutoff_draft_from_training_years_only(tmp_path):
    from tests.test_forecast_f2 import synthetic_city

    store = synthetic_city(60)
    store.a["static__slope_pct"] = np.linspace(0, 6, 60).astype(np.float32)
    store.a["static__low_spot_m"] = np.linspace(-3, 1, 60).astype(np.float32)
    store.a["static__probably_bridge"] = np.zeros(60, np.float32)
    store.a["static__flood_1pct"] = (np.arange(60) % 10 == 0).astype(np.float32)
    store.a["static__flood_02pct"] = np.zeros(60, np.float32)
    test_start = risk_factors.day_number(date.fromisoformat(str(RULES["periods"]["validation"]["start"])))
    for name in risk_factors.WEATHER_FACTORS:  # values after training must never move the cut-offs
        values = np.array(store.a[f"weather__{name}"])
        values[:, store.weeks >= test_start] = 1e6
        store.a[f"weather__{name}"] = values
    cutoffs, evidence, base_rate = risk_factors.draft_cutoffs(store, RULES, 30)
    assert all(c["high"] < 1e5 for c in cutoffs.values())
    assert (
        cutoffs["slope_pct"]["medium"] < cutoffs["slope_pct"]["high"]
        and cutoffs["low_spot_m"]["high"] < cutoffs["low_spot_m"]["medium"] < 0
    )
    assert {row["factor"] for row in evidence} == set(risk_factors.FACTORS)
    for row in evidence:
        assert abs(sum(v["share"] for v in row["levels"].values()) - 1) < 0.01
    assert 0 < base_rate < 1
    yml, md = tmp_path / "risk-factors.yaml", tmp_path / "draft.md"
    risk_factors.write_cutoffs_draft(cutoffs, evidence, base_rate, yml, md)
    saved = yaml.safe_load(yml.read_text())
    assert saved["status"] == "DRAFT" and saved["cutoffs"] == cutoffs
    assert "No percentage is ever shown" in md.read_text()


def test_area_check_markdown():
    from forecasting.area_check import markdown

    result = {
        "name": "Squareville",
        "level": 1,
        "map_zone": "EPSG:26916",
        "box": {},
        "area_km2": 1.2,
        "osm_extract": "2026-10-29",
        "sections_before_boundary_cut": 12,
        "km_before_boundary_cut": 1.1,
        "weather": {"stations": [], "snow_station": None, "choice": None},
        "layers": {"pothole history (Level 2)": False, "traffic counts": True},
    }
    text = markdown(result)
    assert "**Level 1 only**" in text and "None passed the rule" in text and "| traffic counts | yes |" in text


# ---------- database: Level 1 load and factors, the move of tables, the same-results comparison ----------


def make_level1_area(tmp_path: Path) -> areas.Area:
    """A made-up Level 1 area with a GeoJSON boundary around the F1 test road (lat 41.805)."""
    from tests.test_forecast_load import make_raw_dir

    areas_dir = tmp_path / "areas"
    areas_dir.mkdir()
    boundary = {"type": "Polygon", "coordinates": [[[-87.70, 41.80], [-87.60, 41.80], [-87.60, 41.83], [-87.70, 41.83], [-87.70, 41.80]]]}
    (areas_dir / "boundary.geojson").write_text(json.dumps(boundary))
    (areas_dir / "testville.yaml").write_text(
        "name: Testville\nlevel: 1\nschema: testville\nboundary: {geojson_file: boundary.geojson}\n"
        "weather_stations: [{id: USW00094846, name: Station A, lat: 41.80, lon: -87.70}]\ntraffic_counts: idot\n"
    )
    area = areas.load_area("testville", forecast_dir=tmp_path, areas_dir=areas_dir)
    area.raw_dir.parent.mkdir(parents=True)
    make_raw_dir(area.raw_dir)  # the F1 fixture: roads, weather, static layers (its city files are simply not used)
    (area.raw_dir / "bus_routes.geojson").unlink()
    (area.raw_dir / "boundary.geojson").write_text(json.dumps(download.boundary_from_geojson(areas_dir / "boundary.geojson")))
    return area


@pytest.mark.skipif(not TEST_DB, reason="set FORECAST_TEST_DATABASE_URL to run the PostGIS test")
def test_level1_area_load_and_risk_factors(tmp_path):
    from forecasting import load

    area = make_level1_area(tmp_path)
    src = areas.ready_sources(area)
    details = load.run_load(TEST_DB, area.raw_dir, src, RULES)
    assert details["held_out_community_areas"] == [] and details["sections"]["sections_outside_city_removed"] >= 1
    with settings.connect(TEST_DB, "testville") as conn:
        assert conn.execute("SELECT count(*), max(area_number) FROM community_areas").fetchone() == (1, 0)
        assert conn.execute("SELECT count(*) FROM road_sections").fetchone()[0] == 9  # the road outside is removed
        assert conn.execute("SELECT count(*) FROM pothole_reports").fetchone()[0] == 0  # no history in a Level 1 area
        rows, info = risk_factors.compute(conn, src, settings.load_config("f2.yaml"), CUTOFFS, as_of=date(2011, 1, 31))
        risk_factors.save(conn, rows)
        saved = Counter(conn.execute("SELECT factor, level FROM section_risk_factors").fetchall())
    assert info["sections"] == 9 and info["stations"] == ["USW00094846"] and len(rows) == 9 * len(risk_factors.FACTORS)
    # the fixture: every day max 1.5 °C / min -2.0 °C (a freeze-thaw day), 1 mm of rain (never heavy), no snow
    assert saved[("freeze_thaw_14d", "high")] == 9 and saved[("heavy_rain_days_30d", "low")] == 9
    assert saved[("bus_routes", "missing")] == 9  # no bus data for this area: missing, never guessed
    assert saved[("traffic_band", "low")] == 9  # 12,000 vehicles per day: below the 15,000 of "medium"
    assert saved[("snow_mm_30d", "low")] == 9
    assert saved[("flood_zone", "high")] >= 1
    with settings.connect(TEST_DB, "testville") as conn:
        risk_factors.save(conn, rows)  # the same day again replaces, never doubles
        assert conn.execute("SELECT count(*) FROM section_risk_factors").fetchone()[0] == len(rows)
    text = risk_factors.report_markdown("Testville", info, risk_factors.summary_table(rows), {"status": "DRAFT", "drafted": "x"}, [])
    assert "risk factors, not a forecast" in text and "DRAFT" in text and "chance (percentage)" in text


@pytest.mark.skipif(not TEST_DB, reason="set FORECAST_TEST_DATABASE_URL to run the PostGIS test")
def test_move_tables_and_compare_tables(tmp_path):
    from psycopg import sql

    from forecasting import check, load
    from tests.test_forecast_load import SRC, make_raw_dir

    raw = tmp_path / "raw"
    make_raw_dir(raw)
    load.ensure_database(TEST_DB)
    with settings.connect(TEST_DB, autocommit=True) as conn:
        for name in ("legacy_test", "moved_test", "copy_test"):
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(name)))
    load.run_load(TEST_DB, raw, SRC, RULES, schema="legacy_test")
    load.run_load(TEST_DB, raw, SRC, RULES, schema="copy_test")
    with settings.connect(TEST_DB) as conn:
        before = conn.execute("SELECT count(*) FROM legacy_test.road_sections").fetchone()[0]
        moved = migrate.move_tables(conn, "moved_test", source="legacy_test")
        assert set(moved) == set(migrate.TABLES)
        assert conn.execute("SELECT count(*) FROM moved_test.road_sections").fetchone()[0] == before
        assert migrate.move_tables(conn, "moved_test", source="legacy_test") == []  # nothing left to move
        result = check.compare_table(conn, "road_sections", "moved_test", "copy_test")
        assert result["same"] and result["rows"] == before
        assert check.compare_table(conn, "section_static", "moved_test", "copy_test")["same"]
        conn.execute("UPDATE copy_test.section_static SET slope_pct = slope_pct + 0.001 WHERE section_id = '100-0-0'")
        changed = check.compare_table(conn, "section_static", "moved_test", "copy_test")
        assert not changed["same"] and changed["only_in_old"] == 1 and changed["only_in_new"] == 1


def test_learning_table_comparison(tmp_path):
    from forecasting import check

    old, new = tmp_path / "old", tmp_path / "new"
    for folder in (old, new):
        (folder / "events").mkdir(parents=True)
        np.save(folder / "label.npy", np.array([[0, 1], [1, 0]], np.int8))
        np.save(folder / "weather__x.npy", np.array([np.nan, 1.5], np.float32))
        (folder / "sections.json").write_text('[["a", 1.0]]')
        (folder / "meta.json").write_text(
            json.dumps({"section_ids": ["a"], "stations": ["X"], "first_monday": "1", "last_monday": "2", "stamp": "x"})
        )
    np.save(old / "events" / "2017.npy", np.array([[0, 5], [1, 7]], np.int32))
    np.save(new / "events" / "2017.npy", np.array([[1, 7], [0, 5]], np.int32))  # same pairs, other order
    (new / "meta.json").write_text(
        json.dumps({"section_ids": ["a"], "stations": ["X"], "first_monday": "1", "last_monday": "2", "stamp": "y"})
    )
    assert all(r["same"] for r in check.compare_learning_tables(old, new))
    np.save(new / "label.npy", np.array([[0, 1], [1, 1]], np.int8))
    results = {r["item"]: r["same"] for r in check.compare_learning_tables(old, new)}
    assert results["label.npy"] is False and results["weather__x.npy"] is True
