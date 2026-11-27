"""Step-by-step, read-only check: is HPMS 2024 (FHWA, on data.transportation.gov) usable for Illinois?

Dataset: "HPMS Spatial All Sections - 2024" (Socrata id 42um-tgh5). A searchable table, so we ask only for Illinois rows.
Prints every step as it runs. Saves nothing except the log the .ps1 writes.
"""
import json
import sys
import time

import requests

S = requests.Session()
S.headers["User-Agent"] = "GeoInfraLens-research/1.0 (HPMS table check)"
BASE = "https://data.transportation.gov"
ID = "42um-tgh5"
RESULTS = []


def say(text=""):
    print(text, flush=True)


def get(name, url, timeout=120, **params):
    say(f"\n[{len(RESULTS) + 1}] {name}")
    say(f"    {url}  {params if params else ''}")
    start = time.time()
    try:
        r = S.get(url, params=params, timeout=timeout)
        secs = time.time() - start
        if r.status_code != 200:
            note = f"HTTP {r.status_code}: {r.text[:150]!r}"
            say(f"    FAIL after {secs:.1f}s -> {note}")
            RESULTS.append((name, False, note))
            return None
        say(f"    OK in {secs:.1f}s ({len(r.content):,} bytes)")
        RESULTS.append((name, True, f"{secs:.1f}s"))
        return r.json()
    except Exception as e:  # noqa: BLE001
        note = f"{type(e).__name__}: {str(e)[:150]}"
        say(f"    FAIL after {time.time() - start:.1f}s -> {note}")
        RESULTS.append((name, False, note))
        return None


say("HPMS 2024 TABLE CHECK  (each step prints as it runs; about 1-3 minutes)")

say("\n===== A. What is in the table? =====")
meta = get("Dataset description", f"{BASE}/api/views/{ID}.json")
cols = []
if meta:
    say(f"    name: {meta.get('name')}")
    say(f"    licence: {meta.get('license') or meta.get('licenseId')}")
    say(f"    rows updated: {meta.get('rowsUpdatedAt')}  (unix time)")
    cols = [(c.get("fieldName"), c.get("dataTypeName")) for c in meta.get("columns", [])]
    say(f"    {len(cols)} columns. First 60: {[c[0] for c in cols][:60]}")
    geo = [c for c in cols if c[1] in ("line", "multiline", "point", "multipoint", "polygon", "multipolygon", "location")]
    say(f"    map columns: {geo}")

say("\n===== B. Look at a few rows =====")
sample = get("3 sample rows", f"{BASE}/resource/{ID}.json", **{"$limit": 3})
keys = []
if sample:
    keys = list(sample[0].keys())
    say(f"    keys in a row: {keys}")
    for k in keys:
        if "geom" not in k and "line" not in k:
            say(f"      {k} = {str(sample[0].get(k))[:60]}")

state_col = next((k for k in keys if k in ("state_code", "stateid", "state_id", "state")), None) or next((k for k in keys if "state" in k), None)
say(f"\n    state column guess: {state_col}")

say("\n===== C. Illinois =====")
il_where = None
if state_col:
    for label, where in ((f"{state_col}='17'", f"{state_col}='17'"), (f"{state_col}=17", f"{state_col}=17"), (f"{state_col}='IL'", f"{state_col}='IL'")):
        d = get(f"Count of Illinois rows ({label})", f"{BASE}/resource/{ID}.json", **{"$select": "count(*) as n", "$where": where})
        if d and int(d[0].get("n", 0)) > 0:
            say(f"    Illinois rows: {d[0]['n']}")
            il_where = where
            break

if il_where:
    for field in ("iri", "cracking_percent", "rutting", "aadt", "aadt_single_unit", "aadt_combination", "surface_type"):
        if field in keys:
            d = get(f"Illinois rows with {field} filled in", f"{BASE}/resource/{ID}.json", **{"$select": "count(*) as n", "$where": f"{il_where} AND {field} IS NOT NULL"})
            if d:
                say(f"    {field}: {d[0].get('n')} rows filled")
    mapcol = next((c[0] for c in cols if c[1] in ("line", "multiline")), None)
    if mapcol:
        box = "41.70, -88.30, 41.90, -88.00"  # DuPage-sized box: lat/lon corners
        d = get("Illinois rows inside a DuPage-sized box", f"{BASE}/resource/{ID}.json", **{"$select": "count(*) as n", "$where": f"{il_where} AND within_box({mapcol}, 41.90, -88.30, 41.70, -88.00)"})
        if d:
            say(f"    rows in the box: {d[0].get('n')}")
        d = get("Two Illinois rows in the box (to see real values)", f"{BASE}/resource/{ID}.json", **{"$where": f"{il_where} AND within_box({mapcol}, 41.90, -88.30, 41.70, -88.00)", "$limit": 2})
        if d:
            for row in d:
                say("    " + json.dumps({k: v for k, v in row.items() if k != mapcol})[:600])

say("\n===== SUMMARY =====")
fails = [r for r in RESULTS if not r[1]]
say(f"{len(RESULTS) - len(fails)} steps OK, {len(fails)} failed.")
for name, ok, note in RESULTS:
    say(f"  {'OK  ' if ok else 'FAIL'}  {name}  {'' if ok else '-> ' + note}")
say("")
say("READING: if the Illinois count is above 0 and the condition fields are filled, we can load HPMS for the six areas from this table.")
say("Send Claude this whole text.")
sys.stdout.flush()
