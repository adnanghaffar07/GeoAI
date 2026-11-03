"""F2: turn the saved arrays (f2_build) into feature rows for one Monday at a time, and choose rows for each period."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from scipy import sparse

from forecasting.f2_build import EPOCH, HISTORY_WINDOWS, day_number

NEIGHBOUR_WINDOWS = ["reports_7d", "reports_30d", "reports_90d", "reports_365d"]
EXTRA_HISTORY = [  # improvement round 2026-10-29
    "reports_7d",
    "reports_14d",
    "reports_all_before",
    "reports_same_season_3y",
    "years_with_reports_5y",
    "duplicate_reports_30d",
    "duplicate_reports_90d",
]
WEATHER = [
    "freeze_thaw_7d",
    "freeze_thaw_14d",
    "freeze_thaw_30d",
    "below_freezing_days_30d",
    "rain_mm_7d",
    "rain_mm_30d",
    "heavy_rain_days_30d",
    "snow_mm_7d",
    "snow_mm_30d",
    "hot_days_30d",
    "days_since_freeze",
]
STATIC = [
    "highway_code",
    "length_m",
    "lanes",
    "surface_code",
    "slope_pct",
    "low_spot_m",
    "flood_1pct",
    "flood_02pct",
    "probably_bridge",
    "traffic_band",
    "heavy_vehicle_band",
    "bus_routes",
]
CATEGORICAL = ["highway_code", "surface_code", "traffic_band", "heavy_vehicle_band"]
SYSTEM_SWITCH = date(2018, 12, 18)

FEATURES = (
    list(HISTORY_WINDOWS)
    + EXTRA_HISTORY
    + ["days_since_last_report"]
    + [f"neighbour_{name}" for name in NEIGHBOUR_WINDOWS]
    + WEATHER
    + STATIC
    + ["week_of_year", "month", "new_311_system"]
)


class FeatureStore:
    """Holds the arrays of one build and returns feature rows for (Monday, sections)."""

    def __init__(self, arrays: dict[str, np.ndarray], meta: dict[str, Any]):
        self.a = arrays
        self.meta = meta
        self.weeks = arrays["weeks"]
        self.n_sections = len(meta["section_ids"])
        self.held_out = arrays["held_out"].astype(bool)
        self.station = arrays["station_of_section"].astype(np.int64)
        self.neighbours = sparse.csr_matrix(
            (np.ones(len(arrays["neighbour_rows"]), dtype=np.float32), (arrays["neighbour_rows"], arrays["neighbour_cols"])),
            shape=(self.n_sections, self.n_sections),
        )

    @classmethod
    def load(cls, folder: Path) -> FeatureStore:
        if not (folder / "meta.json").exists():
            raise SystemExit("The learning table is not complete yet. Run `forecasting.run f2-build` (it continues where it stopped).")
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        arrays = {path.stem: np.load(path, mmap_mode="r") for path in folder.glob("*.npy")}
        return cls(arrays, meta)

    def week_index(self, monday: date) -> int:
        matches = np.flatnonzero(self.weeks == day_number(monday))
        if len(matches) == 0:
            raise KeyError(f"{monday} is not a Monday of this build")
        return int(matches[0])

    def monday(self, w: int) -> date:
        return date.fromordinal(EPOCH.toordinal() + int(self.weeks[w]))

    def label(self, w: int, rows: np.ndarray | None = None) -> np.ndarray:
        values = np.asarray(self.a["label"][w])
        return values if rows is None else values[rows]

    def matrix(self, w: int, rows: np.ndarray | None = None, drop: list[str] | None = None) -> np.ndarray:
        """Feature rows (float32, NaN = missing) for Monday w, for all sections or the given section positions."""
        rows = np.arange(self.n_sections) if rows is None else rows
        monday = self.monday(w)
        columns: list[np.ndarray] = []
        for name in list(HISTORY_WINDOWS) + EXTRA_HISTORY:
            columns.append(np.asarray(self.a[name][w], dtype=np.float32)[rows])
        last = np.asarray(self.a["last_report_day"][w])[rows]
        columns.append(np.where(last >= 0, self.weeks[w] - last, np.nan).astype(np.float32))
        for name in NEIGHBOUR_WINDOWS:
            all_sections = np.asarray(self.a[name][w], dtype=np.float32)
            columns.append((self.neighbours @ all_sections)[rows].astype(np.float32))
        for name in WEATHER:
            columns.append(np.asarray(self.a[f"weather__{name}"])[self.station[rows], w].astype(np.float32))
        for name in STATIC:
            columns.append(np.asarray(self.a[f"static__{name}"])[rows].astype(np.float32))
        n = len(rows)
        columns.append(np.full(n, monday.isocalendar()[1], dtype=np.float32))
        columns.append(np.full(n, monday.month, dtype=np.float32))
        columns.append(np.full(n, float(monday >= SYSTEM_SWITCH), dtype=np.float32))
        x = np.column_stack(columns)
        if drop:
            keep = [i for i, name in enumerate(FEATURES) if name not in drop]
            x = x[:, keep]
        return x


def feature_names(drop: list[str] | None = None) -> list[str]:
    return [name for name in FEATURES if not drop or name not in drop]


def period_weeks(store: FeatureStore, period: dict[str, Any], next_start: Any, purge_days: int) -> np.ndarray:
    """Mondays of a period whose answer window ends before the next period starts (the purge)."""
    start = day_number(date.fromisoformat(str(period["start"])))
    end = day_number(date.fromisoformat(str(period["end"])))
    weeks = store.weeks
    keep = (weeks >= start) & (weeks <= end)
    if next_start is not None:
        keep &= weeks + purge_days <= day_number(date.fromisoformat(str(next_start)))
    return np.flatnonzero(keep)


def is_winter(monday: date) -> bool:
    return monday.month in (11, 12, 1, 2, 3, 4)
