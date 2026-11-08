"""US plan step C: one downloader for city pothole reports, set up per city in its area file (config/areas/<city>.yaml).

Every city's reports become the same small CSV (potholes_city.csv), loaded into pothole_reports like Chicago's:
source, request_id, created_at, is_duplicate, status, latitude, longitude. Only pothole requests and only these
columns are fetched: no addresses, names or free text.

Portal types: "ckan_sql" (CKAN DataStore SQL, e.g. Boston). Socrata (New York) and Carto (Philadelphia) are added
with their cities.
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


def normalise(record: dict[str, Any], system: dict[str, Any], name: str) -> list[Any]:
    c = system["columns"]
    closure = str(record.get(c.get("closure_reason", ""), "") or "")
    duplicate = any(word in closure.lower() for word in system.get("duplicate_words", []))
    return [
        name,
        str(record.get(c["request_id"]) or "").strip(),
        str(record.get(c["created_at"]) or "").strip().replace(" ", "T")[:19],
        "true" if duplicate else "false",
        str(record.get(c.get("status", ""), "") or "").strip(),
        record.get(c["latitude"]),
        record.get(c["longitude"]),
    ]


def download_city_potholes(session: requests.Session, cfg: dict[str, Any], out_path: Path, sleep=time.sleep) -> int:
    """All configured 311 systems into one CSV. A newer system takes over from its first day (no report counted twice)."""
    if cfg["portal_type"] != "ckan_sql":
        raise SourceChangedError(f"Portal type {cfg['portal_type']} is not supported yet.")
    rows: list[list[Any]] = []
    counts: Counter = Counter()
    for system in cfg["systems"]:
        for _resource, record in ckan_rows(session, cfg["api"], system, cfg.get("page_size", 10000), sleep=sleep):
            rows.append(normalise(record, system, system["name"]))
            counts[system["name"]] += 1
    # the newer system starts on its first report; older-system reports from that day on are left out
    names = [s["name"] for s in cfg["systems"]]
    starts = {n: min((r[2] for r in rows if r[0] == n and r[2]), default=None) for n in names}
    kept, dropped = [], 0
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
    print(f"  pothole requests: {dict(counts)}; left out (newer system already running): {dropped}", flush=True)
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
