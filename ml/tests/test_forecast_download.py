"""Forecasting F1 downloads, tested with a fake web session (no network)."""

from __future__ import annotations

import csv
import json

import pytest

from forecasting import areas, download, settings

CHICAGO = areas.sources_for("chicago")


class FakeResponse:
    def __init__(self, status: int = 200, body: bytes = b""):
        self.status_code = status
        self.content = body
        self.text = body.decode()

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


def test_plan_covers_every_source_and_marks_chicago_items():
    jobs = {job["name"]: job for job in download.plan_downloads(CHICAGO, settings.rules())}
    assert set(jobs) == {
        "potholes_historical",
        "potholes_current",
        "community_areas",
        "weather_USW00094846",
        "weather_USW00014819",
        "osm_roads",
        "cook_county_pci",
        "elevation",
        "flood_zones",
        "traffic_counts",
        "soils",
        "bus_routes",
        "hpms",
    }
    assert {name for name, job in jobs.items() if job["portal"]} == {
        "potholes_historical",
        "potholes_current",
        "community_areas",
        "bus_routes",
    }
    names = list(jobs)
    assert names.index("osm_roads") < names.index("elevation")  # elevation needs the roads first
    # Privacy (F0 section 9): never download the street address
    assert not any("address" in column for job in jobs.values() for column in job.get("select") or [])
    query = jobs["osm_roads"]["query"]
    assert "residential|unclassified" in query and "motorway" not in query and 'access"!~"^(private|no)$' in query


def test_chicago_downloads_need_the_terms_confirmed(tmp_path):
    session = FakeSession([])
    with pytest.raises(SystemExit, match="Terms of Use"):
        download.download_all(tmp_path, CHICAGO, settings.rules(), terms_confirmed=False, session=session)
    assert session.calls == []


def test_socrata_pages_until_a_short_page(tmp_path):
    select = ["sr_number", "created_date"]
    page1 = b'"sr_number","created_date"\n"A","2020-01-01T00:00:00.000"\n"B","2020-01-02T00:00:00.000"\n'
    page2 = b'"sr_number","created_date"\n"C","2020-01-03T00:00:00.000"\n'
    session = FakeSession([FakeResponse(body=page1), FakeResponse(body=page2)])
    out = tmp_path / "x.csv"
    rows = download.download_socrata_csv(
        session, base_url="https://portal", dataset_id="abcd-1234", select=select, where="1=1", page_size=2, out_path=out, sleep=no_sleep
    )
    assert rows == 3
    assert out.read_text().splitlines() == [
        "sr_number,created_date",
        "A,2020-01-01T00:00:00.000",
        "B,2020-01-02T00:00:00.000",
        "C,2020-01-03T00:00:00.000",
    ]
    assert [call[2]["params"]["$offset"] for call in session.calls] == [0, 2]
    assert session.calls[0][2]["params"]["$select"] == "sr_number,created_date"


def test_socrata_renamed_column_stops_with_a_clear_message(tmp_path):
    session = FakeSession([FakeResponse(body=b'"sr_number","created"\n')])
    with pytest.raises(download.SourceChangedError, match="Update config/sources.yaml"):
        download.download_socrata_csv(
            session,
            base_url="https://portal",
            dataset_id="abcd-1234",
            select=["sr_number", "created_date"],
            where="1=1",
            page_size=2,
            out_path=tmp_path / "x.csv",
            sleep=no_sleep,
        )


def test_arcgis_layers_page_and_tag_each_piece(tmp_path):
    def page(ids):
        return FakeResponse(
            body=json.dumps(
                {"type": "FeatureCollection", "features": [{"properties": {"OBJECTID": i}, "geometry": None} for i in ids]}
            ).encode()
        )

    session = FakeSession([page([1, 2]), page([3]), page([7])])
    out = tmp_path / "pci.geojson"
    rows = download.download_arcgis_layers(
        session,
        base_url="https://gis/MapServer",
        layers={0: "Barrington", 5: "Thornton"},
        out_fields=["OBJECTID"],
        page_size=2,
        out_path=out,
        sleep=no_sleep,
    )
    assert rows == 4
    features = json.loads(out.read_text())["features"]
    assert [(f["properties"]["OBJECTID"], f["properties"]["township"]) for f in features] == [
        (1, "Barrington"),
        (2, "Barrington"),
        (3, "Barrington"),
        (7, "Thornton"),
    ]
    assert [call[1] for call in session.calls] == ["https://gis/MapServer/0/query"] * 2 + ["https://gis/MapServer/5/query"]
    assert [call[2]["params"]["resultOffset"] for call in session.calls] == [0, 2, 0]


def test_arcgis_error_stops_with_a_clear_message(tmp_path):
    session = FakeSession([FakeResponse(body=b'{"error": {"code": 400, "message": "Invalid field: PCIsegment"}}')])
    with pytest.raises(download.SourceChangedError, match="Invalid field"):
        download.download_arcgis_layers(
            session,
            base_url="https://gis/MapServer",
            layers={0: "Barrington"},
            out_fields=["PCIsegment"],
            page_size=2,
            out_path=tmp_path / "x",
            sleep=no_sleep,
        )


def test_retries_rate_limits_but_not_bad_requests():
    session = FakeSession([FakeResponse(429), FakeResponse(200, b"ok")])
    assert download.request_with_retries(session, "GET", "https://x", sleep=no_sleep).content == b"ok"
    session = FakeSession([FakeResponse(400, b"no such column")])
    with pytest.raises(download.SourceChangedError, match="no such column"):
        download.request_with_retries(session, "GET", "https://x", sleep=no_sleep)
    assert len(session.calls) == 1


def test_download_records_manifest_and_skips_existing(tmp_path):
    src = CHICAGO
    body = b"STATION,DATE,TMAX\nUSW00094846,2020-01-01,10\n"
    session = FakeSession([FakeResponse(body=body)])
    manifest = download.download_all(
        tmp_path, src, settings.rules(), terms_confirmed=False, only="weather_USW00094846", session=session, sleep=no_sleep
    )
    entry = manifest["weather_USW00094846"]
    assert entry["rows"] == 1 and entry["bytes"] == len(body) and len(entry["sha256"]) == 64
    assert json.loads((tmp_path / "manifest.json").read_text())["weather_USW00094846"]["sha256"] == entry["sha256"]
    # second run: nothing downloaded
    download.download_all(tmp_path, src, settings.rules(), terms_confirmed=False, only="weather_USW00094846", session=FakeSession([]))


def test_arcgis_can_be_limited_to_the_chicago_box(tmp_path):
    session = FakeSession([FakeResponse(body=b'{"type": "FeatureCollection", "features": []}')])
    extra = download.bbox_envelope(CHICAGO["bbox"])
    download.download_arcgis_layers(
        session,
        base_url="https://fema/MapServer",
        layers={28: "Flood Hazard Zones"},
        out_fields=["FLD_ZONE"],
        page_size=1000,
        out_path=tmp_path / "f.geojson",
        tag_field="layer_name",
        extra_params=extra,
        sleep=no_sleep,
    )
    params = session.calls[0][2]["params"]
    assert params["geometry"] == "-87.95,41.62,-87.5,42.03" and params["inSR"] == 4326 and params["f"] == "geojson"


def samples(values):
    return FakeResponse(body=json.dumps({"samples": [{"locationId": i, "value": v} for i, v in enumerate(values)]}).encode())


def test_elevation_samples_in_batches_and_resume(tmp_path):
    out = tmp_path / "elevation_samples.csv"
    points = [(-87.6, 41.8), (-87.61, 41.8), (-87.62, 41.8), (-87.6, 41.8)]  # one repeated point is asked once
    # first run stops after one batch (the second request fails)
    session = FakeSession([samples(["180.5", "NoData"])])
    with pytest.raises(IndexError):
        download.download_elevation_samples(
            session, url="https://usgs/ImageServer", points=points, batch_size=2, out_path=out, sleep=no_sleep
        )
    assert not out.exists() and out.with_suffix(".part").exists()
    # second run only asks for the point still missing
    session = FakeSession([samples(["179.25"])])
    count = download.download_elevation_samples(
        session, url="https://usgs/ImageServer", points=points, batch_size=2, out_path=out, sleep=no_sleep
    )
    assert count == 3
    form = session.calls[0][2]["data"]
    assert json.loads(form["geometry"])["points"] == [[-87.62, 41.8]] and session.calls[0][1].endswith("/getSamples")
    with out.open(newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["key", "elevation_m"]
    assert sorted(rows[1:]) == [["-87.600000,41.800000", "180.5"], ["-87.610000,41.800000", ""], ["-87.620000,41.800000", "179.25"]]


def test_soils_tiles_and_main_component(tmp_path):
    poly = "POLYGON ((-87.7 41.8, -87.6 41.8, -87.6 41.9, -87.7 41.8))"
    tile_answer = json.dumps({"Table": [["mupolygonkey", "mukey", "wkt"], ["11", "501", poly]]}).encode()
    units_answer = json.dumps(
        {
            "Table": [
                ["mukey", "muname", "compname", "comppct_r", "drainagecl"],
                ["501", "Urban land-Orthents complex", "Orthents", "30", "Well drained"],
                ["501", "Urban land-Orthents complex", "Urban land", "60", None],
            ]
        }
    ).encode()
    bbox = {"min_lon": -87.7, "min_lat": 41.8, "max_lon": -87.6, "max_lat": 41.9}
    session = FakeSession(
        [
            FakeResponse(body=tile_answer),
            FakeResponse(body=b"{}"),
            FakeResponse(body=b"{}"),
            FakeResponse(body=b"{}"),
            FakeResponse(body=units_answer),
        ]
    )
    count = download.download_sda_soils(
        session, url="https://sda/post.rest", bbox=bbox, tile_deg=0.05, out_path=tmp_path / "soils.json", sleep=no_sleep
    )
    assert count == 1 and len(session.calls) == 5  # 4 tiles + 1 attribute query
    data = json.loads((tmp_path / "soils.json").read_text())
    assert data["polygons"]["11"] == {"mukey": "501", "wkt": poly}
    assert data["units"]["501"]["compname"] == "Urban land" and data["units"]["501"]["drainagecl"] is None  # biggest component wins


def test_one_failed_item_does_not_stop_the_others(tmp_path):
    src = CHICAGO
    session = FakeSession([FakeResponse(400, b"bad request"), FakeResponse(body=b"STATION,DATE\nX,2020-01-01\n")])
    with pytest.raises(SystemExit) as stop:
        for name in ("weather_USW00094846", "weather_USW00014819"):
            try:
                download.download_all(tmp_path, src, settings.rules(), terms_confirmed=False, only=name, session=session, sleep=no_sleep)
            except SystemExit as error:
                failed = error
        raise failed
    assert stop.value.code == download.PARTIAL_DOWNLOAD_EXIT_CODE
    assert "weather_USW00014819" in json.loads((tmp_path / "manifest.json").read_text())


def geo(features, cut_short=False):
    body = {"type": "FeatureCollection", "features": features}
    if cut_short:
        body["properties"] = {"exceededTransferLimit": True}
    return FakeResponse(body=json.dumps(body).encode())


def zone(object_id):
    return {"properties": {"OBJECTID": object_id, "SFHA_TF": "T"}, "geometry": None}


def test_flood_zones_small_squares_split_when_cut_short_and_kept_once(tmp_path):
    bbox = {"min_lon": -87.70, "min_lat": 41.80, "max_lon": -87.60, "max_lat": 41.85}  # two 0.05° squares
    session = FakeSession(
        [
            geo([zone(1)], cut_short=True),  # first square too big: asked again as four quarters
            geo([zone(1)]),
            geo([zone(2)]),
            geo([]),
            geo([]),
            geo([zone(2), zone(3)]),  # second square; zone 2 crosses the border and is kept once
        ]
    )
    count = download.download_arcgis_tiled(
        session,
        layer_url="https://fema/MapServer/28",
        where="SFHA_TF = 'T'",
        out_fields=["OBJECTID"],
        bbox=bbox,
        tile_deg=0.05,
        max_offset_deg=0.00005,
        out_path=tmp_path / "flood.geojson",
        sleep=no_sleep,
    )
    assert count == 3 and len(session.calls) == 6
    first = session.calls[0][2]["params"]
    assert first["where"] == "SFHA_TF = 'T'" and first["maxAllowableOffset"] == 0.00005 and "resultOffset" not in first
    assert first["geometry"].startswith("-87.7,41.8,")
    assert session.calls[1][2]["params"]["geometry"] == "-87.7,41.8,-87.675,41.825"  # a quarter of the first square


def test_flood_zones_server_error_is_reported(tmp_path):
    session = FakeSession([FakeResponse(500, b"<html>")] * 3)
    with pytest.raises(RuntimeError, match="HTTP 500"):
        download.download_arcgis_tiled(
            session,
            layer_url="https://fema/MapServer/28",
            where="1=1",
            out_fields=["OBJECTID"],
            bbox={"min_lon": 0, "min_lat": 0, "max_lon": 0.05, "max_lat": 0.05},
            tile_deg=0.05,
            max_offset_deg=0.00005,
            out_path=tmp_path / "x",
            sleep=no_sleep,
        )


class StallingResponse(FakeResponse):
    """Answers, then the connection stalls while the file is coming in (the NOAA "Read timed out" of 2026-11-04)."""

    def iter_content(self, _size):
        yield b"part"
        raise download.requests.ConnectionError("Read timed out.")


def test_download_file_retries_when_the_file_stops_coming_in(tmp_path):
    out = tmp_path / "weather.csv"
    session = FakeSession([StallingResponse(body=b"x"), FakeResponse(body=b"all of it")])
    download.download_file(session, "https://www.ncei.noaa.gov/x.csv", out, sleep=no_sleep)
    assert out.read_bytes() == b"all of it" and len(session.calls) == 2
    assert not out.with_suffix(".part").exists()


def test_download_file_gives_a_clear_error_after_the_last_try(tmp_path):
    session = FakeSession([StallingResponse(body=b"x") for _ in range(download.RETRIES)])
    with pytest.raises(RuntimeError, match="Could not reach https://www.ncei.noaa.gov/x.csv: the download stopped"):
        download.download_file(session, "https://www.ncei.noaa.gov/x.csv", tmp_path / "w.csv", sleep=no_sleep)


def _json(data) -> FakeResponse:
    return FakeResponse(body=json.dumps(data).encode())


HPMS_CFG = {**areas.sources_for("chicago")["hpms"]}
BOX = {"min_lon": -87.70, "min_lat": 41.85, "max_lon": -87.60, "max_lat": 41.90}


def test_hpms_uses_the_state_of_the_area_and_the_newest_year_that_answers(tmp_path):
    out = tmp_path / "hpms.geojson"
    line = {"type": "LineString", "coordinates": [[-87.65, 41.87], [-87.64, 41.87]]}
    piece = {"type": "Feature", "properties": {"iri": 180, "AADT": 12000}, "geometry": line}
    session = FakeSession([
        _json({"properties": {"relativeLocation": {"properties": {"state": "IL"}}}}),
        _json({"error": {"code": 400, "message": "Service not found"}}),  # 2025 not published yet
        _json({"fields": [{"name": "iri"}, {"name": "AADT"}, {"name": "rutting"}]}),  # 2024
        _json({"type": "FeatureCollection", "features": [piece]}),
    ])  # fmt: skip
    assert download.download_hpms(session, HPMS_CFG, BOX, out, sleep=no_sleep) == 1
    urls = [call[1] for call in session.calls]
    assert "HPMS_FULL_IL_2025" in urls[1] and "HPMS_FULL_IL_2024" in urls[2]
    assert session.calls[3][2]["params"]["outFields"] == "iri,rutting,AADT"  # only fields that exist, in config order
    saved = json.loads(out.read_text())
    assert saved["hpms"] == {"state": "IL", "year": 2024, "fields": ["iri", "rutting", "AADT"]}


def test_hpms_is_optional_in_a_full_download(tmp_path, monkeypatch):
    monkeypatch.setattr(download, "plan_downloads", lambda _src, _rules: [
        {"name": "hpms", "file": "hpms.geojson", "kind": "hpms", "portal": False, "url": "x", "licence": "x"}])  # fmt: skip

    def slow(*_a, **_k):
        raise RuntimeError("Could not reach geo.dot.gov")

    monkeypatch.setattr(download, "run_job", slow)
    src = {**CHICAGO, "weather": {**CHICAGO["weather"], "stations": ["USW00094846"]}}
    download.download_all(tmp_path, src, settings.rules(), terms_confirmed=False, session=FakeSession([]), sleep=no_sleep)  # no SystemExit
