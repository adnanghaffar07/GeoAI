"""One-time move to the per-area layout (any-area plan, step FA1). Nothing is changed, only moved:

- files: data/raw -> data/chicago/raw, data/f2 -> data/chicago/f2, models/* -> models/chicago/, reports/* -> reports/chicago/
- tables: every forecast table in the database's `public` schema -> schema `chicago` (ALTER TABLE ... SET SCHEMA keeps
  the data, indexes and sequences exactly as they are)

Running it again does nothing. Model fingerprints and the locked-test lock stay valid because the files are not changed.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import psycopg
from psycopg import sql

from forecasting import load, settings

TABLES = [*load.TABLES_IN_LOAD_ORDER, "load_log"]


def move_files(forecast_dir: Path, key: str = "chicago") -> list[str]:
    """Move the old one-area folders into the area's folders. Returns what was moved (empty when already done)."""
    moved: list[str] = []

    def move(source: Path, target: Path) -> None:
        if not source.exists():
            return
        if target.exists():
            raise SystemExit(f"Both {source} and {target} exist. Nothing was moved; tell Claude.")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        moved.append(f"{source.relative_to(forecast_dir)} -> {target.relative_to(forecast_dir)}")

    data = forecast_dir / "data"
    for name in ("raw", "f2"):
        move(data / name, data / key / name)
    for folder in ("models", "reports"):
        base = forecast_dir / folder
        if not base.exists():
            continue
        area_names = {path.stem for path in (settings.CONFIG_DIR / "areas").glob("*.yaml")} | {key}
        for item in sorted(base.iterdir()):
            if item.name in area_names or item.name.startswith("."):
                continue  # already an area folder (or a hidden file such as .gitkeep)
            move(item, base / key / item.name)
    return moved


def move_tables(conn: psycopg.Connection, schema: str = "chicago", source: str = "public") -> list[str]:
    """Move the forecast tables from `public` into the area's schema, in one transaction. Returns the tables moved."""

    def tables_in(name: str) -> set[str]:
        rows = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = %s", (name,)).fetchall()
        return {r[0] for r in rows}

    in_public = [t for t in TABLES if t in tables_in(source)]
    if not in_public:
        return []
    clash = sorted(set(in_public) & tables_in(schema))
    if clash:
        raise SystemExit(f"Tables {clash} exist in both {source} and {schema}. Nothing was moved; tell Claude.")
    load.ensure_schema(conn, schema)
    for table in in_public:
        conn.execute(
            sql.SQL("ALTER TABLE {}.{} SET SCHEMA {}").format(sql.Identifier(source), sql.Identifier(table), sql.Identifier(schema))
        )
    return in_public


def run(url: str, forecast_dir: Path | None = None, key: str = "chicago", schema: str = "chicago") -> dict[str, list[str]]:
    with settings.connect(url) as conn:  # one transaction: all tables move, or none
        tables = move_tables(conn, schema)
    files = move_files(forecast_dir or settings.FORECAST_DIR, key)
    return {"tables": tables, "files": files}
