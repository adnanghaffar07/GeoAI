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


def boston_round() -> None:
    """Fourth round (2026-11-06): Boston's 311 files, their columns and how potholes are named."""
    package = requests.get(f"{BOSTON}/package_show", params={"id": "311-service-requests"}, headers=UA, timeout=120).json()
    resources = package["result"]["resources"]
    print(f"Boston 311: {len(resources)} files")
    for r in resources:
        print(f"  {r.get('name')!s:60.60} id={r['id']} datastore={r.get('datastore_active')} format={r.get('format')}")
    active = [r for r in resources if r.get("datastore_active")]
    for r in active[:1] + active[-2:]:
        one = requests.get(f"{BOSTON}/datastore_search", params={"resource_id": r["id"], "limit": 1}, headers=UA, timeout=120).json()
        result = one.get("result", {})
        fields = [f["id"] for f in result.get("fields", [])]
        print(f"\n  {r.get('name')}: {result.get('total')} rows; columns: {fields}")
        print(f"  first row: {str((result.get('records') or [{}])[0])[:700]}")
        for column in ("type", "case_title", "reason", "subject", "service_name", "request_type"):
            if column in fields:
                q = (  # noqa: S608 (read-only check; names come from the portal itself)
                    f'SELECT "{column}" AS v, count(*) AS n FROM "{r["id"]}" '  # noqa: S608
                    f"WHERE \"{column}\" ILIKE '%pothole%' GROUP BY 1 ORDER BY 2 DESC LIMIT 10"
                )
                found = requests.get(f"{BOSTON}/datastore_search_sql", params={"sql": q}, headers=UA, timeout=120).json()
                print(f"  pothole values in {column}: {found.get('result', {}).get('records', found.get('error'))}")


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
        boston_round()
    except Exception as error:  # noqa: BLE001
        print(f"Boston round: {type(error).__name__}: {str(error)[:200]}")
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
