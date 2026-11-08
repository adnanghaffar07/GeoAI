"""US plan step B: HPMS road condition (no network, no database)."""

from forecasting.risk_factors import level_of
from forecasting.static import hpms_rows


def test_measured_condition_uses_fhwa_limits():
    assert [level_of("road_roughness", v, {}) for v in (60, 95, 170, 171)] == ["low", "medium", "medium", "high"]
    assert [level_of("cracking", v, {}) for v in (2, 5, 20, 25)] == ["low", "medium", "medium", "high"]
    assert [level_of("rutting", v, {}) for v in (0.1, 0.2, 0.41)] == ["low", "medium", "high"]
    assert level_of("road_roughness", None, {}) == "missing"


def test_hpms_rows_keep_only_measured_values():
    line = {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}
    data = {
        "features": [
            {"properties": {"iri": 120, "CRACKING_PERCENT": 0, "rutting": None, "AADT": 9000, "aadt_single_unit": 300,
                            "aadt_combination": 200}, "geometry": line},
            {"properties": {"iri": "bad"}, "geometry": None},  # no shape: skipped
        ]
    }  # fmt: skip
    rows = hpms_rows(data)
    assert len(rows) == 1
    iri, cracking, rutting, aadt, trucks, _geometry = rows[0]
    assert (iri, cracking, rutting, aadt, trucks) == (120.0, None, None, 9000, 500)  # 0 = not measured


def test_hpms_fast_matching_on_the_database(tmp_path):
    import json
    from collections import Counter

    import pytest

    from forecasting import load, settings
    from forecasting.static import load_hpms
    from tests.test_forecast_load import RULES, SCHEMA, SRC, TEST_DB, make_raw_dir

    if not TEST_DB:
        pytest.skip("set FORECAST_TEST_DATABASE_URL to run the PostGIS test")
    raw = tmp_path / "raw"
    make_raw_dir(raw)
    load.run_load(TEST_DB, raw, SRC, RULES)
    with settings.connect(TEST_DB, SCHEMA) as conn:
        line = json.loads(conn.execute("SELECT ST_AsGeoJSON(geom) FROM road_sections ORDER BY section_id LIMIT 1").fetchone()[0])
    piece = {"type": "Feature", "properties": {"iri": 200, "aadt": 5000, "aadt_combination": 40}, "geometry": line}
    data = {"type": "FeatureCollection", "features": [piece], "hpms": {"state": "IL", "year": 2025}}
    (raw / "hpms.geojson").write_text(json.dumps(data), encoding="utf-8")
    with settings.connect(TEST_DB, SCHEMA) as conn:
        used = load_hpms(conn, raw, {**SRC, "hpms": {}}, Counter())
        assert used["pieces"] == 1 and used["sections_matched"] >= 1
        row = conn.execute("SELECT iri, hpms_aadt, hpms_trucks, hpms_year FROM section_static WHERE iri IS NOT NULL LIMIT 1").fetchone()
    assert row == (200.0, 5000, 40, 2025)
