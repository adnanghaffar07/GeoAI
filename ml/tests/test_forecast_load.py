"""Forecasting F1 loading: parsing rules (no database) and a full load + report into a throwaway PostGIS database.

The database part runs only when FORECAST_TEST_DATABASE_URL is set (a database that may be dropped and re-created).
"""

from __future__ import annotations

import csv
import json
import os
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from forecasting import areas, load, settings, static
from forecasting.download import point_key
from forecasting.sections import Section, sample_points, sections_from_file

SRC = areas.sources_for("chicago")
SCHEMA = "chicago"  # the test database gets the same per-area schema as the real one
RULES = settings.rules()
BBOX = SRC["bbox"]


def write_csv(path: Path, header: list[str], rows: list[list]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


HIST_HEADER = SRC["potholes_historical"]["select"]
CURR_HEADER = SRC["potholes_current"]["select"]


def test_historical_potholes_duplicates_and_locations(tmp_path):
    path = write_csv(
        tmp_path / "h.csv",
        HIST_HEADER,
        [
            ["P1", "2015-03-01T10:00:00.000", "Completed", "Pothole in Street", "41.85", "-87.65"],
            ["P2", "2015-03-01T11:00:00.000", "Completed - Dup", "Pothole in Street", "41.85", "-87.65"],
            ["P3", "2015-03-02T00:00:00.000", "Open", "Pothole in Street", "", ""],
            ["P4", "2015-03-02T00:00:00.000", "Open", "Pothole in Street", "40.00", "-87.65"],
            ["P1", "2015-03-03T00:00:00.000", "Completed", "Pothole in Street", "41.85", "-87.65"],
            ["P5", "not a date", "Open", "Pothole in Street", "41.85", "-87.65"],
        ],
    )
    stats = Counter()
    rows = list(load.parse_pothole_csv(path, "potholes_historical", SRC["potholes_historical"], BBOX, stats))
    assert [(r[1], r[3], r[7]) for r in rows] == [
        ("P1", False, None),
        ("P2", True, None),
        ("P3", False, "missing"),
        ("P4", False, "outside_chicago"),
    ]
    assert rows[0][2] == datetime(2015, 3, 1, 10)
    assert stats["potholes_historical.skipped_repeated_id"] == 1
    assert stats["potholes_historical.skipped_no_id_or_date"] == 1
    assert stats["potholes_historical.duplicates"] == 1


def test_current_potholes_use_the_duplicate_flag(tmp_path):
    path = write_csv(
        tmp_path / "c.csv",
        CURR_HEADER,
        [
            ["SR1", "Pothole in Street Complaint", "PHF", "2019-02-01T08:00:00.000", "Completed", "false", "false", "41.85", "-87.65"],
            ["SR2", "Pothole in Street Complaint", "PHF", "2019-02-01T09:00:00.000", "Completed", "true", "true", "41.85", "-87.65"],
        ],
    )
    stats = Counter()
    rows = list(load.parse_pothole_csv(path, "potholes_current", SRC["potholes_current"], BBOX, stats))
    assert [(r[1], r[3]) for r in rows] == [("SR1", False), ("SR2", True)]
    assert stats["potholes_current.legacy_records"] == 1


GHCN_HEADER = ["STATION", "DATE", "PRCP", "PRCP_ATTRIBUTES", "SNOW", "SNOW_ATTRIBUTES", "SNWD", "SNWD_ATTRIBUTES"]
GHCN_HEADER += ["TMAX", "TMAX_ATTRIBUTES", "TMIN", "TMIN_ATTRIBUTES"]


def test_ghcn_units_and_quality_flags(tmp_path):
    path = write_csv(
        tmp_path / "w.csv",
        GHCN_HEADER,
        [
            ["S", "2010-09-30", "0", ",,W,", "0", ",,W,", "0", ",,W,", "200", ",,W", "100", ",,W"],  # before start: skipped
            ["S", "2011-01-05", "254", ",,W,2400", "30", ",,W,", "50", ",,W,", "-56", ",,W", "-120", ",,W"],
            ["S", "2011-01-06", "", "", "0", ",,W,", "0", ",,W,", "999", ",X,W", "-10", ",,W"],  # TMAX failed a quality check
        ],
    )
    stats = Counter()
    rows = list(load.parse_ghcn_csv(path, "S", date(2010, 10, 1), stats))
    assert rows[0] == ("S", date(2011, 1, 5), pytest.approx(-5.6), pytest.approx(-12.0), pytest.approx(25.4), 30.0, 50.0)
    assert rows[1][2] is None and rows[1][4] is None
    assert stats["S.TMAX.rejected_quality_flag"] == 1 and stats["S.PRCP.missing"] == 1 and stats["S.days"] == 2


def test_temperature_unit_check_catches_tenths():
    good = [("S", None, float(t % 40 - 10)) for t in range(400)]
    load.check_temperature_units(good)
    with pytest.raises(ValueError, match="not degrees C"):
        load.check_temperature_units([("S", None, t * 10.0) for _, _, t in good])


def test_held_out_areas_are_fixed_by_the_seed():
    first = load.choose_held_out_areas(range(1, 78), 10, 20261028)
    assert first == load.choose_held_out_areas(reversed(range(1, 78)), 10, 20261028)
    assert len(set(first)) == 10 and all(1 <= a <= 77 for a in first)


def test_community_areas_must_be_77():
    feature = {"properties": {"area_numbe": "1", "community": "ROGERS PARK"}, "geometry": {"type": "Polygon", "coordinates": []}}
    with pytest.raises(ValueError, match="Expected 77 districts"):
        load.community_area_rows({"features": [feature]}, SRC["districts"])
    assert load.community_area_rows({"features": [feature] * 77}, SRC["districts"])[0][:2] == (1, "Rogers Park")


def test_cook_pci_rows_keep_bad_scores_as_missing():
    line = {"type": "LineString", "coordinates": [[-87.9, 41.6], [-87.89, 41.6]]}
    features = [
        {"properties": {"OBJECTID": 1, "FULLSTNA": "W 1st St", "PCIsegment": 72.5, "township": "Bloom"}, "geometry": line},
        {"properties": {"OBJECTID": 2, "PCIsegment": 140, "township": "Bloom"}, "geometry": line},
        {"properties": {"OBJECTID": 3, "PCIsegment": None, "township": "Bloom"}, "geometry": line},
        {"properties": {"OBJECTID": 4, "PCIsegment": 50, "township": "Bloom"}, "geometry": None},
    ]
    stats = Counter()
    rows = load.pci_rows({"features": features}, 2025, stats)
    assert [(r[0], r[1], r[2], r[6], r[7]) for r in rows] == [
        ("Bloom", 1, "W 1st St", 72.5, 2025),
        ("Bloom", 2, None, None, 2025),
        ("Bloom", 3, None, None, 2025),
    ]
    assert stats["cook_pci.pci_out_of_range"] == 1 and stats["cook_pci.pci_missing"] == 1 and stats["cook_pci.skipped_no_shape_or_id"] == 1


# ---------- full load + report against a real PostGIS database ----------

TEST_DB = os.environ.get("FORECAST_TEST_DATABASE_URL")


def square(lon: float, lat: float, size: float) -> dict:
    return {"type": "Polygon", "coordinates": [[[lon, lat], [lon + size, lat], [lon + size, lat + size], [lon, lat + size], [lon, lat]]]}


def make_raw_dir(raw: Path) -> None:
    raw.mkdir()
    # 77 community areas: an 11 x 7 grid of 0.01-degree squares starting at -87.70, 41.80
    features = [
        {
            "properties": {"area_numbe": str(i + 1), "community": f"AREA {i + 1}"},
            "geometry": square(-87.70 + (i % 11) * 0.01, 41.80 + (i // 11) * 0.01, 0.01),
        }
        for i in range(77)
    ]
    (raw / "community_areas.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}))

    # One east-west road across the grid (about 900 m) and one road outside the city
    lat = 41.805
    elements = [{"type": "node", "id": n, "lon": -87.695 + (n - 1) * 0.0055, "lat": lat} for n in range(1, 4)]
    elements += [{"type": "node", "id": 9, "lon": -87.40, "lat": 41.70}, {"type": "node", "id": 10, "lon": -87.39, "lat": 41.70}]
    elements += [
        {"type": "way", "id": 100, "nodes": [1, 2, 3], "tags": {"highway": "residential", "name": "Test Ave"}},
        {"type": "way", "id": 200, "nodes": [9, 10], "tags": {"highway": "primary"}},
    ]
    (raw / "osm_roads.json").write_text(json.dumps({"osm3s": {"timestamp_osm_base": "2026-10-28T00:00:00Z"}, "elements": elements}))

    write_csv(
        raw / "potholes_historical.csv",
        HIST_HEADER,
        [
            ["H1", "2017-02-01T00:00:00.000", "Completed", "Pothole in Street", str(lat + 0.0001), "-87.69"],  # ~11 m from the road
            ["H2", "2017-02-02T00:00:00.000", "Completed - Dup", "Pothole in Street", str(lat), "-87.69"],
            ["H3", "2017-02-03T00:00:00.000", "Completed", "Pothole in Street", "41.835", "-87.65"],  # far from the road
        ],
    )
    write_csv(
        raw / "potholes_current.csv",
        CURR_HEADER,
        [
            ["S1", "Pothole in Street Complaint", "PHF", "2019-03-01T00:00:00.000", "Completed", "false", "false", str(lat), "-87.686"],
            [
                "S2",
                "Pothole in Street Complaint",
                "PHF",
                "2023-03-01T00:00:00.000",
                "Open",
                "false",
                "false",
                str(lat),
                "-87.68",
            ],  # test period
        ],
    )
    for station in SRC["weather"]["stations"]:
        days = [date(2010, 10, 1) + timedelta(days=i) for i in range(400)]
        write_csv(
            raw / f"weather_{station['id']}.csv",
            GHCN_HEADER,
            [[station["id"], d.isoformat(), "10", ",,W,", "0", ",,W,", "0", ",,W,", "15", ",,W", "-20", ",,W"] for d in days],
        )
    # Cook County pavement condition: two suburban road pieces, one with a MultiLineString shape
    pci = [
        {
            "properties": {"OBJECTID": 1, "PCIsegment": 61.0, "township": "Bloom"},
            "geometry": {"type": "LineString", "coordinates": [[-87.62, 41.50], [-87.61, 41.50]]},
        },
        {
            "properties": {"OBJECTID": 2, "PCIsegment": 83.0, "township": "Bloom"},
            "geometry": {"type": "MultiLineString", "coordinates": [[[-87.60, 41.50], [-87.59, 41.50]]]},
        },
    ]
    (raw / "cook_county_pci.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": pci}))
    write_static_layers(raw)


def write_static_layers(raw: Path) -> None:
    """F1b fixtures around the test road (lat 41.805, lon -87.695 to -87.684)."""
    sections, _, _ = sections_from_file(raw / "osm_roads.json")
    rows = [["key", "elevation_m"]]
    for section in sections:
        for lon, lat in sample_points(section):
            height = 180 + (lon + 87.695) * 100  # rises 1 m per 0.01 degree going east
            if section.section_id == "100-0-2" and (lon, lat) == sample_points(section)[1]:
                height -= 3  # a dip in the middle of one section
            rows.append([point_key(lon, lat), round(height, 3)])
    write_csv(raw / "elevation_samples.csv", rows[0], rows[1:])
    flood = {"properties": {"FLD_ZONE": "AE", "ZONE_SUBTY": None, "SFHA_TF": "T"}, "geometry": square(-87.696, 41.803, 0.004)}
    (raw / "flood_zones.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [flood]}))
    soil = "POLYGON((-87.70 41.80, -87.68 41.80, -87.68 41.81, -87.70 41.81, -87.70 41.80))"
    (raw / "soils.json").write_text(
        json.dumps(
            {
                "polygons": {"1": {"mukey": "501", "wkt": soil}},
                "units": {"501": {"muname": "Urban land-Markham complex", "compname": "Markham", "drainagecl": "Moderately well drained"}},
            }
        )
    )
    lat = 41.805
    parallel = {
        "properties": {"ROAD_NAME": "TEST AVE", "AADT": 12000, "AADT_YR": 2019, "HCV_AADT": 600, "HCV_AADTYR": 2019},
        "geometry": {"type": "MultiLineString", "coordinates": [[[-87.696, lat + 0.0001], [-87.683, lat + 0.0001]]]},
    }
    crossing = {  # crosses the road at a right angle: must not be matched
        "properties": {"ROAD_NAME": "CROSS ST", "AADT": 99999, "AADT_YR": 2019},
        "geometry": {"type": "LineString", "coordinates": [[-87.6895, lat - 0.002], [-87.6895, lat + 0.002]]},
    }
    (raw / "traffic_counts.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [parallel, crossing]}))
    bus = [
        {
            "properties": {"route": "9", "name": "Ashland"},
            "geometry": {"type": "LineString", "coordinates": [[-87.696, lat], [-87.683, lat]]},
        },
        {
            "properties": {"route": "X9", "name": "Ashland Express"},
            "geometry": {"type": "LineString", "coordinates": [[-87.696, lat], [-87.690, lat]]},
        },
    ]
    (raw / "bus_routes.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": bus}))


@pytest.mark.skipif(not TEST_DB, reason="set FORECAST_TEST_DATABASE_URL to run the PostGIS load test")
def test_full_load_and_report(tmp_path):

    from forecasting.report import write_report

    raw = tmp_path / "raw"
    make_raw_dir(raw)
    load.ensure_database(TEST_DB)
    details = load.run_load(TEST_DB, raw, SRC, RULES)
    details_again = load.run_load(TEST_DB, raw, SRC, RULES)  # safe to run twice: the load replaces itself
    assert SRC["schema"] == SCHEMA
    assert details_again["sections"] == details["sections"]

    with settings.connect(TEST_DB, SCHEMA) as conn:
        counts = conn.execute(
            "SELECT (SELECT count(*) FROM community_areas), (SELECT count(*) FROM community_areas WHERE held_out), "
            "(SELECT count(*) FROM road_sections), (SELECT count(*) FROM road_sections WHERE community_area IS NULL), "
            "(SELECT count(*) FROM pothole_reports), (SELECT count(*) FROM pothole_reports WHERE geom IS NULL), "
            "(SELECT count(*) FROM weather_daily)"
        ).fetchone()
        assert counts == (77, 10, 9, 0, 5, 0, 800)
        # every section of the road outside the city is removed, none of the city road
        assert details["sections"]["sections_outside_city_removed"] == details["sections"]["sections_built"] - 9
        assert conn.execute("SELECT count(*) FROM road_sections WHERE osm_way_id = 200").fetchone()[0] == 0

        path = write_report(conn, RULES, SRC, {}, tmp_path / "reports")
    data = json.loads((tmp_path / "reports" / "f1-data-report.json").read_text())["report"]
    assert data["potholes"]["test_period_total_only"] == 1
    assert data["coverage"] == {"usable_reports_before_test": 3, "within_20m_of_a_section": 2}
    assert data["system_switch"]["before"]["duplicate_pct"] == 33.3
    assert data["cook_county_pci"]["by_township"][0][:2] == ["Bloom", 2]
    assert data["cook_county_pci"]["pieces_inside_chicago"] == 0
    text = path.read_text()
    assert "# F1 data report (Chicago)" in text and "Test Ave" not in text
    assert "| 2017 |" in text and "2,017" not in text  # years are not shown with a thousands comma
    assert "## Static layers (F1b)" in text


@pytest.mark.skipif(not TEST_DB, reason="set FORECAST_TEST_DATABASE_URL to run the PostGIS load test")
def test_static_layers_per_section(tmp_path):

    raw = tmp_path / "raw"
    make_raw_dir(raw)
    details = load.run_load(TEST_DB, raw, SRC, RULES)
    assert details["static_layers"]["soil"]["kept"] is True and details["static_layers"]["soil"]["missing_share"] == 0.0
    with settings.connect(TEST_DB, SCHEMA) as conn:
        rows = {
            r[0]: r[1:]
            for r in conn.execute(
                "SELECT section_id, slope_pct, low_spot_m, flood_1pct, soil_drainage_rank, soil_urban_land, "
                "aadt, aadt_year, hcv_aadt, bus_routes "
                "FROM section_static t JOIN road_sections s USING (section_id) WHERE s.osm_way_id = 100 ORDER BY section_id"
            )
        }
    assert len(rows) == 9
    first, dip, last = rows["100-0-0"], rows["100-0-2"], rows["100-0-8"]
    assert 0.10 < first[0] < 0.15  # about 0.12 m rise over 100 m (0.0012 degrees x 100 m per degree)
    assert dip[1] < -2  # the dipped section is a low spot
    assert first[2] is True and last[2] is False  # flood square covers only the west end
    assert first[3] == 4 and first[4] is True  # moderately well drained, urban land
    assert {r[5] for r in rows.values()} == {12000}  # the parallel count, never the crossing street (99,999)
    assert first[6] == 2019 and first[7] == 600
    assert first[8] == 2 and last[8] == 1  # route 9 everywhere, X9 only on the west half


def test_static_helpers():
    assert static.drainage_rank("Poorly drained") == 6 and static.drainage_rank(None) is None
    section = Section("s", 1, "residential", None, None, None, 100.0, ((-87.70, 41.80), (-87.6988, 41.80)))
    start, mid, end = sample_points(section)
    heights = {point_key(*start): 180.0, point_key(*end): 181.0}
    assert static.elevation_rows([section], heights, {"s"}) == [("s", 180.0, None, 181.0, 1.0)]
    assert static.elevation_rows([section], heights, set()) == []
    rows = static.soil_rows({"polygons": {"1": {"mukey": "9", "wkt": "W"}}, "units": {}})
    assert rows == [("9", None, None, None, "W")]
