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


def test_philadelphia_reads_carto_pages():
    cfg = areas.sources_for("philadelphia")["city_potholes"]
    record = {"service_request_id": 10055796, "requested_datetime": "2016-01-10T21:12:50Z", "status": "Closed",
              "status_notes": None, "lat": 40.05, "lon": -75.08}  # fmt: skip
    session = FakeSession([FakeResponse(body=json.dumps({"rows": [record]}).encode())])
    rows = list(cities.carto_rows(session, cfg["api"], cfg["systems"][0], 10000, sleep=no_sleep))
    assert len(rows) == 1
    query = session.calls[0][2]["params"]["q"]
    assert "service_name IN ('Street Defect')" in query and "address" not in query and "media_url" not in query
    assert cities.normalise(rows[0][1], cfg["systems"][0], "philadelphia_311")[:4] == [
        "philadelphia_311", "10055796", "2016-01-10T16:12:50", "false"]  # UTC -> Philadelphia time  # fmt: skip


def _features(rows, more=False):
    return FakeResponse(body=json.dumps({"features": [{"attributes": r} for r in rows], "exceededTransferLimit": more}).encode())


def test_naperville_requests_and_crew_repairs_side_by_side(tmp_path):
    cfg = json.loads(json.dumps(areas.sources_for("naperville")["city_potholes"]))
    requests_page = [
        {"REQUESTID": "300001", "DATE_CREATED": 1704114000000, "STATUS": "CLOSED", "LAT_DEGREE": 41.77, "LONG_DEGREE": -88.15},
        {"REQUESTID": "300002", "DATE_CREATED": 1704200400000, "STATUS": "OPEN", "LAT_DEGREE": 0.0, "LONG_DEGREE": 0.0},
    ]  # fmt: skip
    repairs_page = [
        {"Work_Order_ID": "WO1", "Date_Initiated": 1704204000000, "WOYCOORDINATE": 41.77, "WOXCOORDINATE": -88.15,
         "Service_Request_ID": "300001"},  # the repair for request 300001: the same pothole
        {"Work_Order_ID": "WO2", "Date_Initiated": 1704290400000, "WOYCOORDINATE": 41.75, "WOXCOORDINATE": -88.17,
         "Service_Request_ID": "1"},  # crew found it themselves
    ]  # fmt: skip
    session = FakeSession([_features(requests_page[:1], more=True), _features(requests_page[1:]), _features(repairs_page)])
    out = tmp_path / "potholes_city.csv"
    assert cities.download_city_potholes(session, cfg, out, sleep=no_sleep) == 4  # side by side: nothing left out
    first = session.calls[0][2]["params"]
    assert first["where"] == "UPPER(DESCRIPTION) LIKE '%POTHOLE%'" and "ADDRESS" not in first["outFields"]
    assert session.calls[1][2]["params"]["resultOffset"] == 1  # the next page
    assert "Description IN ('Streets-Pavement Potholes', 'Pavement Patching')" in session.calls[2][2]["params"]["where"]
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert [(r["source"], r["request_id"], r["is_duplicate"]) for r in rows] == [
        ("naperville_requests", "300001", "false"),
        ("naperville_requests", "300002", "false"),
        ("naperville_crew_repairs", "WO1", "true"),
        ("naperville_crew_repairs", "WO2", "false"),
    ]
    assert rows[0]["created_at"] == "2024-01-01T07:00:00"  # 13:00 UTC = 07:00 in Naperville (winter)

    stats = Counter()
    bbox = {"min_lat": 41.6, "max_lat": 41.9, "min_lon": -88.3, "max_lon": -88.0}
    loaded = list(cities.parse_city_csv(out, cfg, bbox, stats, "outside_naperville"))
    assert len(loaded) == 4 and stats["naperville_requests.location_default_point"] == 1  # 0,0 = no location
    assert stats["naperville_crew_repairs.duplicates"] == 1
