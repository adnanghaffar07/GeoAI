"""US plan step C: one downloader for city pothole reports, set up per city in its area file (config/areas/<city>.yaml).

Every city's reports become the same small CSV (potholes_city.csv), loaded into pothole_reports like Chicago's:
source, request_id, created_at, is_duplicate, status, latitude, longitude. Only pothole requests and only these
columns are fetched: no addresses, names or free text.

Portal types: "ckan_sql" (CKAN DataStore SQL, e.g. Boston), "carto_sql" (Carto SQL API, e.g. Philadelphia),
"arcgis" (ArcGIS Feature Service layers, e.g. Naperville). Socrata (New York) is added with its city.

Systems run one after the other (an old 311 system replaced by a new one), or side by side ("parallel_systems": e.g.
Naperville's residents' requests and the city crews' repair work orders). A work order made for a request that is
already counted is marked as a repeat, so one pothole is never counted twice.
"""

from __future__ import annotations

import csv
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import requests

from forecasting.download import SourceChangedError, request_with_retries

COLUMNS = ["source", "request_id", "created_at", "is_duplicate", "status", "latitude", "longitude"]


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def ckan_rows(session: requests.Session, api: str, system: dict[str, Any], page: int, sleep=time.sleep):
    """Pothole rows of one 311 system, every yearly file, paged. Yields (resource name, record)."""
    names = ", ".join(f'"{c}"' for c in system["columns"].values())
    kinds = ", ".join(_quote(k) for k in system["pothole_values"])
    for resource in system["resources"]:
        offset = 0
        while True:
            query = (  # noqa: S608 (names and values come from the area file, not from users)
                f'SELECT {names} FROM "{resource["id"]}" WHERE "{system["type_column"]}" IN ({kinds}) '  # noqa: S608
                f'ORDER BY "_id" LIMIT {page} OFFSET {offset}'
            )
            answer = request_with_retries(session, "GET", f"{api}/datastore_search_sql", params={"sql": query}, sleep=sleep)
            data = json.loads(answer.content)
            if not data.get("success"):
                raise SourceChangedError(f"{resource['name']}: the portal refused the query ({str(data.get('error'))[:200]}).")
            records = data["result"]["records"]
            for record in records:
                yield resource["name"], record
            if len(records) < page:
                break
            offset += page


def carto_rows(session: requests.Session, api: str, system: dict[str, Any], page: int, sleep=time.sleep):
    """Pothole rows from a Carto SQL table (e.g. Philadelphia), paged. Yields (table, record)."""
    names = ", ".join(system["columns"].values())
    kinds = ", ".join(_quote(k) for k in system["pothole_values"])
    offset = 0
    while True:
        query = (  # noqa: S608 (names and values come from the area file, not from users)
            f"SELECT {names} FROM {system['table']} WHERE {system['type_column']} IN ({kinds}) "  # noqa: S608
            f"ORDER BY {system.get('order_by', 'cartodb_id')} LIMIT {page} OFFSET {offset}"
        )
        answer = request_with_retries(session, "GET", api, params={"q": query}, sleep=sleep)
        data = json.loads(answer.content)
        if "rows" not in data:
            raise SourceChangedError(f"{system['table']}: the portal refused the query ({str(data.get('error'))[:200]}).")
        for record in data["rows"]:
            yield system["table"], record
        if len(data["rows"]) < page:
            break
        offset += page


def arcgis_rows(session: requests.Session, api: str, system: dict[str, Any], page: int, sleep=time.sleep):
    """Pothole rows from one ArcGIS Feature Service layer (e.g. Naperville), paged. Yields (layer, record).

    Only the configured columns are asked for (no addresses or free text); dates come as milliseconds since 1970 (UTC)."""
    names = ",".join(dict.fromkeys(system["columns"].values()))
    column = system["type_column"]
    tests = []
    if system.get("pothole_values"):
        tests.append(f"{column} IN ({', '.join(_quote(k) for k in system['pothole_values'])})")
    tests += [f"UPPER({column}) LIKE {_quote('%' + w.upper() + '%')}" for w in system.get("pothole_words", [])]
    if not tests:
        raise SourceChangedError(f"{system['name']}: no pothole_values or pothole_words in the area file.")
    url = f"{api}/{system['layer']}/query"
    offset = 0
    while True:
        params = {
            "where": " OR ".join(tests),
            "outFields": names,
            "orderByFields": system.get("order_by", "OBJECTID"),
            "resultOffset": offset,
            "resultRecordCount": page,
            "returnGeometry": "false",
            "f": "json",
        }
        answer = request_with_retries(session, "GET", url, params=params, sleep=sleep)
        data = json.loads(answer.content)
        if "features" not in data:
            raise SourceChangedError(f"{system['name']}: the map service refused the query ({str(data.get('error'))[:200]}).")
        for feature in data["features"]:
            yield system["layer"], feature.get("attributes") or {}
        if not data["features"] or not (data.get("exceededTransferLimit") or len(data["features"]) >= page):
            break
        offset += len(data["features"])


def local_time(value: str, timezone: str | None) -> str:
    """'2016-01-10T21:12:50Z' (UTC) or milliseconds since 1970 (UTC) -> the city's local time, like Chicago's;
    times without a zone are kept."""
    if value.isdigit() and len(value) >= 11 and timezone:
        from datetime import UTC, datetime
        from zoneinfo import ZoneInfo

        moment = datetime.fromtimestamp(int(value) / 1000, UTC).astimezone(ZoneInfo(timezone))
        return moment.strftime("%Y-%m-%dT%H:%M:%S")
    if value.endswith("Z") and timezone:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        moment = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ZoneInfo(timezone))
        return moment.strftime("%Y-%m-%dT%H:%M:%S")
    return value.replace(" ", "T")[:19]


def normalise(record: dict[str, Any], system: dict[str, Any], name: str) -> list[Any]:
    c = system["columns"]
    closure = str(record.get(c.get("closure_reason", ""), "") or "")
    duplicate = any(word in closure.lower() for word in system.get("duplicate_words", []))
    return [
        name,
        str(record.get(c["request_id"]) or "").strip(),
        local_time(str(record.get(c["created_at"]) or "").strip(), system.get("timezone")),
        "true" if duplicate else "false",
        str(record.get(c.get("status", ""), "") or "").strip(),
        record.get(c["latitude"]),
        record.get(c["longitude"]),
    ]


def download_city_potholes(session: requests.Session, cfg: dict[str, Any], out_path: Path, sleep=time.sleep) -> int:
    """All configured 311 systems into one CSV. A newer system takes over from its first day (no report counted twice)."""
    readers = {"ckan_sql": ckan_rows, "carto_sql": carto_rows, "arcgis": arcgis_rows}
    if cfg["portal_type"] not in readers:
        raise SourceChangedError(f"Portal type {cfg['portal_type']} is not supported yet.")
    reader = readers[cfg["portal_type"]]
    rows: list[list[Any]] = []
    counts: Counter = Counter()
    ids: dict[str, set[str]] = {}
    linked = 0
    for system in cfg["systems"]:
        link = system.get("linked_to")  # e.g. a crew work order made for a residents' request
        for _resource, record in reader(session, cfg["api"], system, cfg.get("page_size", 10000), sleep=sleep):
            row = normalise(record, system, system["name"])
            if link and str(record.get(link["column"]) or "").strip() in ids.get(link["system"], set()):
                row[3] = "true"  # the same pothole as a request already counted
                linked += 1
            ids.setdefault(system["name"], set()).add(row[1])
            rows.append(row)
            counts[system["name"]] += 1
    names = [s["name"] for s in cfg["systems"]]
    kept, dropped = [], 0
    if cfg.get("parallel_systems"):
        kept = rows  # side by side: nothing is left out (repeats are marked above)
    else:
        # the newer system starts on its first report; older-system reports from that day on are left out
        starts = {n: min((r[2] for r in rows if r[0] == n and r[2]), default=None) for n in names}
        for row in rows:
            later = [starts[n] for n in names[names.index(row[0]) + 1 :] if starts[n]]
            if later and row[2] >= min(later):
                dropped += 1
                continue
            kept.append(row)
    tmp = out_path.with_suffix(".part")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerows(kept)
    tmp.replace(out_path)
    print(
        f"  pothole requests: {dict(counts)}; left out (newer system already running): {dropped}; "
        f"marked as the same pothole as a request: {linked}",
        flush=True,
    )
    return len(kept)


def parse_city_csv(path: Path, cfg: dict[str, Any], bbox: dict[str, float], stats: Counter, outside: str):
    """Yield pothole_reports rows from potholes_city.csv. Points the city uses for "no location" count as missing."""
    from forecasting.load import location_issue, parse_float, parse_portal_time

    unknown = {(round(p[0], 4), round(p[1], 4)) for p in cfg.get("unknown_points", [])}
    seen: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            source = record["source"]
            stats[f"{source}.rows"] += 1
            request_id = record["request_id"]
            created = parse_portal_time(record["created_at"].replace(" ", "T")[:19])
            if not request_id or created is None:
                stats[f"{source}.skipped_no_id_or_date"] += 1
                continue
            if (source, request_id) in seen:
                stats[f"{source}.skipped_repeated_id"] += 1
                continue
            seen.add((source, request_id))
            lat, lon = parse_float(record["latitude"]), parse_float(record["longitude"])
            if lat is not None and lon is not None and (round(lat, 4), round(lon, 4)) in unknown:
                lat = lon = None
                stats[f"{source}.location_default_point"] += 1
            issue = location_issue(lat, lon, bbox, outside)
            if issue:
                stats[f"{source}.location_{issue}"] += 1
            is_duplicate = record["is_duplicate"] == "true"
            if is_duplicate:
                stats[f"{source}.duplicates"] += 1
            stats[f"{source}.loaded"] += 1
            yield (source, request_id, created, is_duplicate, record["status"] or None, lat, lon, issue)


def load_city_potholes(conn: Any, raw_dir: Path, src: dict[str, Any], stats: Counter) -> dict[str, Any]:
    """Load only this city's reports (`run potholes`): replaces the rows of its own systems in pothole_reports and
    touches nothing else (road sections, weather and other tables stay as they are)."""
    from forecasting.load import copy_rows, require

    cfg = src["city_potholes"]
    names = [s["name"] for s in cfg["systems"]]
    outside = f"outside_{src.get('area_key', 'city')}"
    conn.execute("DELETE FROM pothole_reports WHERE source = ANY(%s)", (names,))
    rows = parse_city_csv(require(raw_dir, "potholes_city.csv"), cfg, src["bbox"], stats, outside)
    copy_rows(
        conn,
        "pothole_reports",
        ["source", "request_id", "created_at", "is_duplicate", "status", "latitude", "longitude", "location_issue"],
        rows,
    )
    conn.execute(
        "UPDATE pothole_reports SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) "
        "WHERE location_issue IS NULL AND source = ANY(%s)",
        (names,),
    )
    return {key: value for key, value in sorted(stats.items())}
