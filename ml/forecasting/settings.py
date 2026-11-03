"""Paths, config files and the database address for the forecasting pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

FORECAST_DIR = Path(__file__).resolve().parent
CONFIG_DIR = FORECAST_DIR / "config"
DEFAULT_DATA_DIR = FORECAST_DIR / "data"  # git-ignored ("data/" in .gitignore); raw downloads and the manifest
REPORTS_DIR = FORECAST_DIR / "reports"
MODELS_DIR = FORECAST_DIR / "models"  # small trained model files with fingerprints (may be committed)


def load_config(name: str) -> dict[str, Any]:
    with (CONFIG_DIR / name).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def sources() -> dict[str, Any]:
    return load_config("sources.yaml")


def rules() -> dict[str, Any]:
    """The frozen F0 rules (sections, periods, held-out areas) in machine-readable form."""
    return load_config("acceptance-thresholds.yaml")


def connect(url: str, schema: str | None = None, **kwargs: Any):
    """Open the forecast database; with a schema, the area's tables are found first (PostGIS stays in public).

    On the owner's Windows/Docker laptop a new connection sometimes got no answer and waited forever (2026-10-30), so
    each try gives up after 20 seconds and is tried up to 3 times. The schema is set with SET after connecting.
    """
    import time

    import psycopg
    from psycopg import sql

    if schema and (not schema.replace("_", "").isalnum() or not schema[0].isalpha()):
        raise SystemExit(f"Not a safe schema name: {schema!r}")
    kwargs.setdefault("connect_timeout", 20)
    autocommit = kwargs.pop("autocommit", False)
    for attempt in range(1, 4):
        try:
            conn = psycopg.connect(url, autocommit=True, **kwargs)
            break
        except psycopg.OperationalError as error:
            if attempt == 3:
                raise SystemExit(f"The database did not answer after 3 tries: {error}. Is Docker Desktop running?") from error
            print(f"  the database did not answer (try {attempt} of 3); trying again", flush=True)
            time.sleep(2)
    if schema:
        conn.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))  # kept for the whole session
    conn.autocommit = autocommit
    return conn


def database_url() -> str:
    """Address of the separate `forecast` database. Never the app database (F0 section 10)."""
    url = os.environ.get("FORECAST_DATABASE_URL", "").strip()
    if not url:
        raise SystemExit(
            "Set FORECAST_DATABASE_URL first, for example\n"
            "  postgresql://geoinfralens:YOUR_DB_PASSWORD@localhost:5432/forecast\n"
            "(same user and password as POSTGRES_USER / POSTGRES_PASSWORD in the project .env)."
        )
    url = url.replace("postgresql+psycopg://", "postgresql://")
    if url.rstrip("/").rsplit("/", 1)[-1].split("?")[0] in {"geoinfralens", "geoinfralens_test"}:
        raise SystemExit("FORECAST_DATABASE_URL points at the app database. Use a separate database named 'forecast'.")
    return url
