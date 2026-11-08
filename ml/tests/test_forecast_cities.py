"""US plan step C: the city connector (no network)."""

import csv
import json
from collections import Counter

from forecasting import areas, cities
from tests.test_forecast_download import FakeResponse, FakeSession, no_sleep

BOSTON = areas.sources_for("boston")["city_potholes"]


def _answer(records):
    return FakeResponse(body=json.dumps({"success": True, "result": {"records": records}}).encode())


def _config():
    cfg = json.loads(json.dumps(BOSTON))
    cfg["systems"][0]["resources"] = cfg["systems"][0]["resources"][:1]
    return cfg


def test_boston_both_systems_newer_one_takes_over(tmp_path):
    old = [
        {"case_enquiry_id": "1", "open_dt": "2026-06-30 10:00:00.5", "case_status": "Closed",
         "closure_reason": "Case Closed. Case Noted. Duplicate of 0", "latitude": 42.33, "longitude": -71.07},
        {"case_enquiry_id": "2", "open_dt": "2026-07-20 09:00:00", "case_status": "Open", "closure_reason": None,
         "latitude": 42.35, "longitude": -71.06},
    ]  # fmt: skip
    new = [{"case_id": "BCS-9", "open_date": "2026-07-14T10:56:30", "case_status": "Open", "closure_reason": None,
            "latitude": 42.34, "longitude": -71.05}]  # fmt: skip
    session = FakeSession([_answer(old), _answer(new)])
    out = tmp_path / "potholes_city.csv"
    assert cities.download_city_potholes(session, _config(), out, sleep=no_sleep) == 2
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert [(r["source"], r["request_id"], r["is_duplicate"]) for r in rows] == [
        ("boston_311_old", "1", "true"),  # "Duplicate" in the closure reason
        ("boston_311_new", "BCS-9", "false"),
    ]  # old-system report 2 (after the new system started on 2026-07-14) is left out
    query = session.calls[0][2]["params"]["sql"]
    assert "\"type\" IN ('Request for Pothole Repair')" in query and "LIMIT 10000 OFFSET 0" in query
    assert "location" not in query.split("FROM")[0]  # no address column is fetched


def test_city_csv_default_point_counts_as_missing(tmp_path):
    out = tmp_path / "potholes_city.csv"
    out.write_text(
        "source,request_id,created_at,is_duplicate,status,latitude,longitude\n"
        "boston_311_old,1,2015-03-01T08:00:00,false,Closed,42.3594,-71.0587\n"
        "boston_311_old,2,2015-03-02T08:00:00,false,Closed,42.33,-71.07\n"
        "boston_311_old,2,2015-03-02T08:00:00,false,Closed,42.33,-71.07\n",
        encoding="utf-8",
    )
    bbox = {"min_lon": -71.2, "min_lat": 42.2, "max_lon": -70.9, "max_lat": 42.4}
    stats: Counter = Counter()
    rows = list(cities.parse_city_csv(out, BOSTON, bbox, stats, "outside_boston"))
    assert [r[7] for r in rows] == ["missing", None]
    assert stats["boston_311_old.location_default_point"] == 1 and stats["boston_311_old.skipped_repeated_id"] == 1
