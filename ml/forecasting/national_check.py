"""Read-only check before the US-wide step: can this computer reach the free national and city data,
how big would one project's download be, and is there room? Nothing is saved or changed.

Run with scripts\\national-check.bat (inside the API container, so it uses the laptop's own internet).
"""

import shutil
import time
from pathlib import Path

import requests

UA = {"User-Agent": "GeoInfraLens-national-check/0.1"}  # app name only, no personal details
HPMS = "https://services6.arcgis.com/clPWQMwZfdWn4MQZ/ArcGIS/rest/services/HPMS_2024_Data/FeatureServer/34"

ENVELOPE = '{"xmin":-87.70,"ymin":41.85,"xmax":-87.60,"ymax":41.90,"spatialReference":{"wkid":4326}}'
GEO_DOT = "https://geo.dot.gov/server/rest/services/Hosted"

# Third round (2026-11-05): layer 34 above holds other states only; FHWA keeps one full HPMS service per state.
CHECKS: list = []


BOSTON = "https://data.boston.gov/api/3/action"


PHILLY = "https://phl.carto.com/api/v2/sql"


def philly_round() -> None:
    """Sixth round (2026-11-09): Philadelphia 311 (Carto): columns, how potholes are named, years, duplicates."""

    def q(text: str) -> object:
        answer = requests.get(PHILLY, params={"q": text}, headers=UA, timeout=180).json()
        return answer.get("rows", answer.get("error"))

    t = "public_cases_fc"
    print("columns:", list((q(f"SELECT * FROM {t} LIMIT 1") or [{}])[0].keys()))  # noqa: S608
    print("first Street Defect row:", str(q(f"SELECT * FROM {t} WHERE service_name = 'Street Defect' LIMIT 1"))[:900])  # noqa: S608
    print(
        "Street Defect subjects:",
        q(
            f"SELECT left(subject, 60) AS v, count(*) AS n FROM {t} WHERE service_name = 'Street Defect' GROUP BY 1 ORDER BY 2 DESC LIMIT 15"
        ),
    )  # noqa: S608
    print(
        "other names with pothole:",
        q(
            f"SELECT service_name, left(subject, 60) AS s, count(*) AS n FROM {t} WHERE subject ILIKE '%pothole%' "  # noqa: S608
            "OR service_name ILIKE '%pothole%' GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 15"
        ),
    )
    print(
        "Street Defect per year:",
        q(
            f"SELECT extract(year FROM requested_datetime) AS y, count(*) AS n FROM {t} WHERE service_name = 'Street Defect' "  # noqa: S608
            "GROUP BY 1 ORDER BY 1"
        ),
    )
    print(
        "Street Defect status notes:",
        q(
            f"SELECT left(status_notes, 80) AS v, count(*) AS n FROM {t} WHERE service_name = 'Street Defect' GROUP BY 1 "  # noqa: S608
            "ORDER BY 2 DESC LIMIT 25"
        ),
    )
    print(
        "Street Defect without a location:",
        q(f"SELECT count(*) AS n FROM {t} WHERE service_name = 'Street Defect' AND (lat IS NULL OR lon IS NULL)"),
    )  # noqa: S608


def boston_round() -> None:
    """Fifth round (2026-11-09): Boston's 2014 file, and the words used for duplicates."""

    def sql_(q: str) -> object:
        answer = requests.get(f"{BOSTON}/datastore_search_sql", params={"sql": q}, headers=UA, timeout=180).json()
        return answer.get("result", {}).get("records", answer.get("error"))

    y2014 = "bdae89c8-d4ce-40e9-a6e1-a5203953a2e0"
    y2019 = "ea2e4696-4a2d-429c-9807-d02eb92e0222"
    new = "254adca6-64ab-4c5c-9fc0-a6da622be185"
    print("2014 rows:", sql_(f'SELECT count(*) AS n FROM "{y2014}"'))  # noqa: S608
    print("2014 types like pothole:", sql_(
        f'SELECT "type" AS v, count(*) AS n FROM "{y2014}" WHERE "type" ILIKE \'%pot%\' OR "case_title" ILIKE \'%pot%\' '  # noqa: S608
        "GROUP BY 1 ORDER BY 2 DESC LIMIT 15"))  # fmt: skip
    print("2014 most common types:", sql_(f'SELECT "type" AS v, count(*) AS n FROM "{y2014}" GROUP BY 1 ORDER BY 2 DESC LIMIT 25'))  # noqa: S608
    print("2014 first row:", str(sql_(f'SELECT * FROM "{y2014}" LIMIT 1'))[:900])  # noqa: S608
    print("2019 pothole closure reasons:", sql_(
        f'SELECT left("closure_reason", 90) AS v, count(*) AS n FROM "{y2019}" WHERE "type" = \'Request for Pothole Repair\' '  # noqa: S608
        "GROUP BY 1 ORDER BY 2 DESC LIMIT 30"))  # fmt: skip
    print("new system pothole closure reasons:", sql_(
        f'SELECT left("closure_reason", 90) AS v, count(*) AS n FROM "{new}" WHERE "service_name" = \'Pothole\' '  # noqa: S608
        "GROUP BY 1 ORDER BY 2 DESC LIMIT 20"))  # fmt: skip


def hpms_round() -> None:
    listing = requests.get(f"{GEO_DOT}?f=json", headers=UA, timeout=90).json()
    names = sorted(s["name"] for s in listing.get("services", []) if "HPMS" in s["name"].upper())
    print(f"HPMS services at FHWA: {len(names)}; first 60: {names[:60]}")
    illinois = [n for n in names if "HPMS_FULL_IL_" in n.upper()]
    print(f"Illinois: {illinois}")
    if not illinois:
        return
    service = f"https://geo.dot.gov/server/rest/services/{sorted(illinois)[-1]}/FeatureServer"
    layers = requests.get(f"{service}?f=json", headers=UA, timeout=120).json().get("layers", [])
    print(f"Layers in {service}: " + ", ".join(f"{x['id']}={x['name']}" for x in layers))
    for layer in layers[:25]:
        url = f"{service}/{layer['id']}/query"
        box = {
            "where": "1=1",
            "geometry": ENVELOPE,
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "f": "json",
        }
        count = requests.get(url, params={**box, "returnCountOnly": "true"}, headers=UA, timeout=120).json()
        print(f"  layer {layer['id']} {layer['name']}: {count.get('count', count)} pieces in the Chicago box")
        if count.get("count"):
            one = requests.get(
                url, params={**box, "outFields": "*", "returnGeometry": "false", "resultRecordCount": "1"}, headers=UA, timeout=60
            ).json()
            feats = one.get("features") or [{}]
            print(f"     sample: {str(feats[0].get('attributes'))[:600]}")


def main() -> None:
    print("Read-only check. Nothing is saved.\n")
    try:
        philly_round()
    except Exception as error:  # noqa: BLE001
        print(f"Philadelphia round: {type(error).__name__}: {str(error)[:200]}")
    ok = 0
    for name, url, params in CHECKS:
        start = time.perf_counter()
        try:
            answer = requests.get(url, params=params, headers=UA, timeout=120)
            seconds = time.perf_counter() - start
            size = len(answer.content)
            detail = answer.text[:1500].replace("\n", " ")
            good = answer.status_code == 200
            ok += good
            print(f"[{'OK ' if good else 'NO '}] {name}: answer {answer.status_code}, {size / 1024:.1f} KB in {seconds:.1f} s")
            print(f"       {detail}")
        except Exception as error:  # noqa: BLE001 - this is a report, every problem is printed
            print(f"[NO ] {name}: {type(error).__name__}: {str(error)[:160]}")
    for folder in ("/ml", "/data", "/app"):
        if Path(folder).exists():
            usage = shutil.disk_usage(folder)
            print(f"\nFree disk where {folder} lives: {usage.free / 1e9:.0f} GB of {usage.total / 1e9:.0f} GB")
            break
    try:
        mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        print(
            f"Memory Docker can use: {int(mem['MemTotal'].split()[0]) / 1e6:.1f} GB "
            f"(free now {int(mem['MemAvailable'].split()[0]) / 1e6:.1f} GB)"
        )
    except Exception as error:  # noqa: BLE001
        print(f"Memory: not known ({error})")
    print(f"\n{ok} of {len(CHECKS)} services answered. Send this whole text to Claude.")


if __name__ == "__main__":
    main()
