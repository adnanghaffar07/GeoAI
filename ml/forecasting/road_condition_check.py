"""Step-by-step, read-only check of the free road-condition services. Prints every step as it runs.

Goal: find out WHERE it fails: our internet, FHWA's server, one state's data, or the Cook County server.
Saves nothing except the log the .ps1 writes.
"""
import sys
import time

import requests

S = requests.Session()
S.headers["User-Agent"] = "GeoInfraLens-research/1.0 (road condition check)"
RESULTS = []  # (step, ok, note)
FHWA = "https://geo.dot.gov/server/rest/services/Hosted"
COOK = "https://gis.cookcountyil.gov/traditional/rest/services"
COOK12 = "https://gis12.cookcountyil.gov/arcgis/rest/services"
IL_BOX = {"geometry": "-88.30,41.70,-88.00,41.90", "geometryType": "esriGeometryEnvelope", "inSR": "4326", "spatialRel": "esriSpatialRelIntersects"}


def say(text=""):
    print(text, flush=True)


def step(name, url, timeout=60, **params):
    """One request. Prints OK or FAIL with the time and the reason. Returns the JSON (or None)."""
    params.setdefault("f", "json")
    say(f"\n[{len(RESULTS) + 1}] {name}")
    say(f"    {url}")
    start = time.time()
    try:
        r = S.get(url, params=params, timeout=timeout)
        secs = time.time() - start
        try:
            data = r.json()
        except ValueError:
            data = None
        err = data.get("error") if isinstance(data, dict) else None
        if r.status_code != 200 or err:
            note = f"HTTP {r.status_code}" + (f", server says: {err.get('code')} {err.get('message')}" if err else f", body: {r.text[:120]!r}")
            say(f"    FAIL after {secs:.1f}s -> {note}")
            RESULTS.append((name, False, note))
            return None
        say(f"    OK in {secs:.1f}s ({len(r.content):,} bytes)")
        RESULTS.append((name, True, f"{secs:.1f}s"))
        return data if data is not None else r.text
    except requests.exceptions.Timeout:
        note = f"no answer in {timeout}s (timeout)"
    except requests.exceptions.ConnectionError as e:
        note = f"cannot connect: {str(e)[:120]}"
    except Exception as e:  # noqa: BLE001
        note = f"error: {str(e)[:120]}"
    say(f"    FAIL after {time.time() - start:.1f}s -> {note}")
    RESULTS.append((name, False, note))
    return None


say("ROAD CONDITION CHECK  (each step prints as it runs; about 2-5 minutes)")

say("\n===== A. Is the internet fine? (control sites that should always answer) =====")
step("Weather service (api.weather.gov)", "https://api.weather.gov/")
step("Esri public ArcGIS server", "https://services.arcgisonline.com/arcgis/rest/services")

say("\n===== B. FHWA server (geo.dot.gov): does it answer at all? =====")
listing = step("FHWA list of hosted services", FHWA)
if listing:
    hpms = sorted(s["name"] for s in listing.get("services", []) if "hpms" in s["name"].lower())
    say(f"    {len(hpms)} HPMS services listed; Illinois: {[n for n in hpms if '_IL_' in n]}")

say("\n===== C. Service details: which part breaks? =====")
for svc in ("HPMS_FULL_IL_2024", "HPMS_IL_GeoIntersections_2019", "HPMS_FULL_IN_2024", "HPMS_FULL_WI_2024", "HPMS_FULL_TX_2024"):
    root = step(f"{svc}: service description", f"{FHWA}/{svc}/FeatureServer")
    if root:
        say(f"    layers: {[(l.get('id'), l.get('name')) for l in root.get('layers', [])]}")
    step(f"{svc}: layer 0 fields", f"{FHWA}/{svc}/FeatureServer/0")

say("\n===== D. Can we ask for data? (Illinois 2024, different ways) =====")
q = f"{FHWA}/HPMS_FULL_IL_2024/FeatureServer/0/query"
step("IL 2024: count of all pieces (no map box)", q, where="1=1", returnCountOnly="true")
step("IL 2024: one piece only (no map box)", q, where="1=1", outFields="*", resultRecordCount="1", returnGeometry="false")
step("IL 2024: count inside the DuPage-sized box", q, where="1=1", returnCountOnly="true", **IL_BOX)
step("IL 2024: one piece as GeoJSON", q, where="1=1", outFields="*", resultRecordCount="1", f="geojson")

say("\n===== E. Cook County pavement condition =====")
step("Cook County: list of services", COOK)
step("Cook County: pavement condition service", f"{COOK}/Pavement_Condition_Index/MapServer")
step("Cook County (second server): list of services", COOK12)
step("Cook County (second server): pavement condition", f"{COOK12}/Pavement_Condition_Index/MapServer")

say("\n===== SUMMARY =====")
fails = [r for r in RESULTS if not r[1]]
say(f"{len(RESULTS) - len(fails)} steps OK, {len(fails)} failed.")
for name, ok, note in RESULTS:
    say(f"  {'OK  ' if ok else 'FAIL'}  {name}  {'' if ok else '-> ' + note}")
control_ok = all(ok for _, ok, _ in RESULTS[0:2])
say("")
if not control_ok:
    say("READING: the internet controls failed -> the problem is on this computer's connection (firewall, VPN, proxy).")
else:
    say("READING: the internet is fine. If the FHWA list works but every FHWA data step fails, the fault is on FHWA's side.")
say("Send Claude this whole text.")
sys.stdout.flush()
