"""The 7-day weather outlook from the US National Weather Service (api.weather.gov), for F4 alerts.

Two requests per place: /points/{lat},{lon} gives the forecast grid for that point, and the grid's raw data gives
max/min temperature, rain and snow in time blocks. They are turned into one row per local day for the next 7 days and
three counts the alert rules use (forecasting-f4-plan.md section 5): freeze-thaw days (max above 0 °C and min below 0 °C,
the same rule as the forecast inputs), frost days (max below 0 °C) and heavy-rain days (25 mm or more).

NWS asks every caller to name itself in the User-Agent (FORECAST_CONTACT_EMAIL). Free; no key.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

BASE_URL = "https://api.weather.gov"
HEAVY_RAIN_MM = 25.0
DAYS = 7
DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?$")


def parse_valid_time(text: str) -> tuple[datetime, timedelta]:
    """'2026-10-30T12:00:00+00:00/PT13H' -> (start, length)."""
    start_text, duration_text = text.split("/")
    match = DURATION.match(duration_text)
    if not match:
        raise ValueError(f"Unexpected NWS duration {duration_text!r}")
    days, hours, minutes = (int(v or 0) for v in match.groups())
    return datetime.fromisoformat(start_text), timedelta(days=days, hours=hours, minutes=minutes)


def to_mm(value: float | None, uom: str) -> float | None:
    if value is None:
        return None
    if uom.endswith(":mm"):
        return float(value)
    if uom.endswith(":m"):
        return float(value) * 1000
    raise ValueError(f"Unexpected NWS unit {uom!r}")


def to_celsius(value: float | None, uom: str) -> float | None:
    if value is None:
        return None
    if uom.endswith("degC"):
        return float(value)
    if uom.endswith("degF"):
        return (float(value) - 32) * 5 / 9
    raise ValueError(f"Unexpected NWS unit {uom!r}")


def daily_outlook(grid: dict[str, Any], tz_name: str, today: date) -> list[dict[str, Any]]:
    """One row per local day, today and the next 6 days. Amounts are split over the hours of each block."""
    tz = ZoneInfo(tz_name)
    props = grid["properties"]
    days = [today + timedelta(days=i) for i in range(DAYS)]
    tmax: dict[date, list[float]] = defaultdict(list)
    tmin: dict[date, list[float]] = defaultdict(list)
    amounts: dict[str, dict[date, float]] = {"rain_mm": defaultdict(float), "snow_mm": defaultdict(float)}
    known: dict[str, set[date]] = {"rain_mm": set(), "snow_mm": set()}

    for key, store, convert in (("maxTemperature", tmax, to_celsius), ("minTemperature", tmin, to_celsius)):
        layer = props.get(key) or {}
        for item in layer.get("values", []):
            start, length = parse_valid_time(item["validTime"])
            value = convert(item.get("value"), layer.get("uom", "wmoUnit:degC"))
            if value is not None:  # the day the block mostly falls in (NWS daily max/min blocks)
                middle = (start + length / 2).astimezone(tz).date()
                store[middle].append(value)
    for key, name in (("quantitativePrecipitation", "rain_mm"), ("snowfallAmount", "snow_mm")):
        layer = props.get(key) or {}
        for item in layer.get("values", []):
            start, length = parse_valid_time(item["validTime"])
            value = to_mm(item.get("value"), layer.get("uom", "wmoUnit:mm"))
            if value is None:
                continue
            hours = max(int(length.total_seconds() // 3600), 1)
            for h in range(hours):
                day = (start + timedelta(hours=h)).astimezone(tz).date()
                amounts[name][day] += value / hours
                known[name].add(day)
    rows = []
    for day in days:
        rows.append(
            {
                "date": day.isoformat(),
                "max_c": round(max(tmax[day]), 1) if tmax[day] else None,
                "min_c": round(min(tmin[day]), 1) if tmin[day] else None,
                "rain_mm": round(amounts["rain_mm"][day], 1) if day in known["rain_mm"] else None,
                "snow_mm": round(amounts["snow_mm"][day], 1) if day in known["snow_mm"] else None,
            }
        )
    return rows


def counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The numbers the alert rules use. Days with a missing value are not counted (never guessed)."""
    freeze_thaw = sum(1 for r in rows if r["max_c"] is not None and r["min_c"] is not None and r["max_c"] > 0 and r["min_c"] < 0)
    frost = sum(1 for r in rows if r["max_c"] is not None and r["max_c"] < 0)
    heavy = sum(1 for r in rows if r["rain_mm"] is not None and r["rain_mm"] >= HEAVY_RAIN_MM)
    snow = round(sum(r["snow_mm"] or 0.0 for r in rows), 1)
    return {"freeze_thaw_days": freeze_thaw, "frost_days": frost, "heavy_rain_days": heavy, "snow_mm": snow}


def fetch_outlook(session, lat: float, lon: float, today: date, sleep=None) -> dict[str, Any]:
    """Ask NWS for the point's grid and its data; return the daily rows, counts and the source."""
    from forecasting.download import request_with_retries

    kwargs = {"sleep": sleep} if sleep else {}
    headers = {"Accept": "application/geo+json"}
    point = request_with_retries(session, "GET", f"{BASE_URL}/points/{lat:.4f},{lon:.4f}", headers=headers, **kwargs).json()
    p = point["properties"]
    grid = request_with_retries(session, "GET", p["forecastGridData"], headers=headers, **kwargs).json()
    rows = daily_outlook(grid, p["timeZone"], today)
    return {
        "source": f"NWS {p['gridId']} grid {p['gridX']},{p['gridY']}",
        "issued_at": grid["properties"].get("updateTime"),
        "days": rows,
        **counts(rows),
    }
