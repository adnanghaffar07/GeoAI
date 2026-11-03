"""F4b: what the app's jobs call (weather outlook, new reports, weekly levels, project areas). No network: fake sessions.

Database parts run only when FORECAST_TEST_DATABASE_URL is set.
"""

from __future__ import annotations

import json
import os
from datetime import date

import numpy as np
import pytest

from forecasting import live, nws, settings
from forecasting.f2_store import FEATURES

TEST_DB = os.environ.get("FORECAST_TEST_DATABASE_URL")
RULES = settings.rules()
CFG = settings.load_config("f2.yaml")


class JsonResponse:
    def __init__(self, data, status: int = 200):
        self.status_code = status
        self.data = data
        self.content = json.dumps(data).encode()
        self.text = self.content.decode()

    def json(self):
        return self.data

    def iter_content(self, _size):
        yield self.content


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def no_sleep(_seconds):
    return None


# ---------- NWS outlook ----------

GRID = {
    "properties": {
        "updateTime": "2026-10-30T10:00:00+00:00",
        "maxTemperature": {
            "uom": "wmoUnit:degC",
            "values": [
                {"validTime": "2026-10-31T13:00:00+00:00/PT12H", "value": 3.0},  # Sat: thaw by day
                {"validTime": "2026-11-01T13:00:00+00:00/PT12H", "value": -1.0},  # Sun: frozen all day
                {"validTime": "2026-11-02T13:00:00+00:00/PT12H", "value": 8.0},
            ],
        },
        "minTemperature": {
            "uom": "wmoUnit:degC",
            "values": [
                {"validTime": "2026-10-31T00:00:00+00:00/PT13H", "value": -2.0},  # night into Sat (Chicago time)
                {"validTime": "2026-11-01T00:00:00+00:00/PT13H", "value": -6.0},
                {"validTime": "2026-11-02T00:00:00+00:00/PT13H", "value": 1.0},
            ],
        },
        "quantitativePrecipitation": {
            "uom": "wmoUnit:mm",
            "values": [{"validTime": "2026-11-02T12:00:00+00:00/PT6H", "value": 30.0}],  # Mon morning, Chicago
        },
        "snowfallAmount": {"uom": "wmoUnit:mm", "values": [{"validTime": "2026-11-01T06:00:00+00:00/PT6H", "value": 20.0}]},
    }
}


def test_outlook_days_and_counts():
    rows = nws.daily_outlook(GRID, "America/Chicago", date(2026, 10, 31))
    assert len(rows) == 7 and rows[0]["date"] == "2026-10-31"
    sat, sun, mon = rows[0], rows[1], rows[2]
    assert (sat["max_c"], sat["min_c"]) == (3.0, -2.0)  # a freeze-thaw day
    assert sun["max_c"] == -1.0  # a frost day
    assert mon["rain_mm"] == 30.0 and sun["snow_mm"] == 20.0
    assert rows[5]["max_c"] is None and rows[5]["rain_mm"] is None  # no data: missing, never guessed
    assert nws.counts(rows) == {"freeze_thaw_days": 1, "frost_days": 1, "heavy_rain_days": 1, "snow_mm": 20.0}
    assert nws.to_celsius(32, "wmoUnit:degF") == 0 and nws.to_mm(0.03, "wmoUnit:m") == 30


def test_fetch_outlook_uses_the_point_grid():
    point = {"properties": {"forecastGridData": "https://api.weather.gov/gridpoints/LOT/74,71", "timeZone": "America/Chicago",
                            "gridId": "LOT", "gridX": 74, "gridY": 71}}  # fmt: skip
    session = FakeSession([JsonResponse(point), JsonResponse(GRID)])
    out = nws.fetch_outlook(session, 41.8781, -87.6298, date(2026, 10, 31), sleep=no_sleep)
    assert session.calls[0][1] == "https://api.weather.gov/points/41.8781,-87.6298"
    assert out["source"] == "NWS LOT grid 74,71" and out["freeze_thaw_days"] == 1 and out["issued_at"].startswith("2026-10-30")


# ---------- levels and reasons ----------


def test_level_counts_follow_f4_d2():
    assert live.level_counts(71979) == (720, 6478)  # Chicago: top 1% high, the next 9% medium
    assert live.level_counts(9) == (1, 0) and live.level_counts(0) == (0, 0)


def tiny_b1(n_rows: int = 400, seed: int = 3):
    from forecasting.f2_store import feature_names
    from forecasting.f2_train import make_b1

    rng = np.random.default_rng(seed)
    x = rng.integers(0, 4, (n_rows, len(FEATURES))).astype(np.float32)
    x[::2, FEATURES.index("lanes")] = np.nan  # an input that is often missing
    y = (x[:, FEATURES.index("reports_365d")] + rng.random(n_rows) > 2.5).astype(int)
    return make_b1(feature_names()).fit(x, y), x


def test_contributions_explain_the_score():
    model, x = tiny_b1()
    push = live.contributions(model, x[:20])
    assert push.shape == (20, len(FEATURES))
    raw = model.named_steps["model"].decision_function(model.named_steps["prepare"].transform(x[:20]))
    intercept = model.named_steps["model"].intercept_[0]
    assert np.allclose(push.sum(axis=1) + intercept, raw)  # the parts add up to the model's score
    assert np.argmax(np.abs(push).mean(axis=0)) == FEATURES.index("reports_365d")  # the input that drives the made-up answer


def test_model_needs_its_fingerprint(tmp_path):
    import joblib

    model, _ = tiny_b1()
    joblib.dump(model, tmp_path / live.MODEL_FILE)
    from forecasting.download import sha256_file

    (tmp_path / live.MODELS_JSON).write_text(
        json.dumps({"version": "forecast-test-0.2", "fingerprints": {live.MODEL_FILE: sha256_file(tmp_path / live.MODEL_FILE)}})
    )
    loaded, version = live.load_model(tmp_path)
    assert version == "forecast-test-0.2"
    (tmp_path / live.MODEL_FILE).write_bytes(b"changed")
    with pytest.raises(SystemExit, match="fingerprint"):
        live.load_model(tmp_path)


def test_project_area_file(tmp_path):
    from forecasting import areas

    square = {"type": "Polygon", "coordinates": [[[-88.2, 41.7], [-88.19, 41.7], [-88.19, 41.71], [-88.2, 41.71], [-88.2, 41.7]]]}
    pid = "1f2e3d4c-5b6a-4978-8695-a4b3c2d1e0f9"
    folder = live.write_project_area(pid, "Main Street survey", square, base=tmp_path)
    key = live.project_area_key(pid)
    assert key == "p_1f2e3d4c5b6a"
    src = areas.sources_for(key, areas_dir=folder)
    assert src["level"] == 1 and src["schema"] == key and src["weather"]["stations"] == "auto" and "traffic_counts" in src
    assert json.loads((folder / f"{key}.geojson").read_text())["features"][0]["geometry"] == square


# ---------- database: new reports, weather reload, weekly levels ----------


@pytest.mark.skipif(not TEST_DB, reason="set FORECAST_TEST_DATABASE_URL to run the PostGIS test")
def test_new_reports_weather_and_weekly_levels(tmp_path):
    from forecasting import areas, f2_build, load, weekly
    from tests.test_forecast_load import CURR_HEADER, SRC, make_raw_dir, write_csv

    raw = tmp_path / "data" / "chicago" / "raw"
    raw.parent.mkdir(parents=True)
    make_raw_dir(raw)
    load.run_load(TEST_DB, raw, SRC, RULES)
    out = tmp_path / "f2"
    with settings.connect(TEST_DB, "chicago", autocommit=True) as conn:
        f2_build.build(conn, out, date(2017, 1, 2), date(2017, 3, 27), CFG, 20)
    area = areas.load_area("chicago", forecast_dir=tmp_path)

    with settings.connect(TEST_DB, "chicago") as conn:
        weekly.seed_from_learning_table(conn, out)
        # one new report on the test road, one already known (S1, same id: not added twice)
        lat = 41.805
        body = write_csv(tmp_path / "new.csv", CURR_HEADER, [
            ["S1", "Pothole in Street Complaint", "PHF", "2019-03-01T00:00:00.000", "Completed", "false", "false", str(lat), "-87.686"],
            ["S9", "Pothole in Street Complaint", "PHF", "2026-10-29T08:00:00.000", "Open", "false", "false", str(lat), "-87.690"],
        ]).read_bytes()  # fmt: skip
        session = FakeSession([JsonResponse(None)])
        session.responses = [type("R", (), {"status_code": 200, "content": body, "text": body.decode()})()]
        assert live.download_new_reports(conn, area, session, sleep=no_sleep) == 1
        assert "created_date >= '2023-03-01T00:00:00'" in session.calls[0][2]["params"]["$where"]  # only newer than the newest
        assert weekly.match_new_reports(conn, 20) >= 1
        assert conn.execute("SELECT count(*) FROM report_matches WHERE request_id = 'S9'").fetchone()[0] >= 1

        last = live.reload_weather(conn, raw, area.src)
        assert set(last) == {"USW00094846", "USW00014819"} and last["USW00094846"] == "2011-11-04"

        model, _ = tiny_b1()
        rows = live.weekly_levels(conn, date(2017, 3, 27), CFG, "EPSG:26916", model)
        assert len(rows) == 9 and sorted(r["rank"] for r in rows) == list(range(1, 10))
        assert [r["level"] for r in rows].count("high") == 1 and all(r["level"] in {"high", "low"} for r in rows)
        top = next(r for r in rows if r["rank"] == 1)
        assert "lanes" in top["missing_inputs"] and 0 <= top["monitor_value"] <= 1
        assert all(reason["push"] > 0 for reason in top["reasons"]) and len(top["reasons"]) <= 3

        sections = live.sections_in(
            conn, "chicago", "SRID=4326;POLYGON((-87.70 41.80, -87.69 41.80, -87.69 41.81, -87.70 41.81, -87.70 41.80))"
        )
        assert 1 <= len(sections) <= 9 and sections[0][4].startswith("SRID=4326;LINESTRING")
        assert live.in_chicago(conn, "SRID=4326;POINT(-87.695 41.805)") is True
        assert live.in_chicago(conn, "SRID=4326;POINT(-88.15 41.75)") is False
        conn.rollback()
