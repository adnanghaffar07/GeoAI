"""`same-results-check`: prove that Chicago gives exactly the same results with the any-area code (plan section 3.1).

1. Load Chicago's raw files again, with the new code, into a separate schema `chicago_check`, and compare every table
   with the `chicago` schema row by row (shapes compared exactly).
2. Build the learning table again into data/chicago_check/f2 and compare every array with data/chicago/f2.
3. Score the EXISTING trained models (B0, B1, LightGBM with and without traffic; fingerprints checked) on the validation
   year with the new learning table, and compare with reports/chicago/f2-validation-report.json.

The locked test is NOT run again. Nothing in schema `chicago` or in data/chicago is changed. When everything matches,
the check schema and folder are removed; when something differs they are kept for Claude to look at.
Each part is saved when it finishes (reload, learning table part by part, each model's scores): a re-run continues.
Writes reports/chicago/same-results-check.md (+ .json).
"""

from __future__ import annotations

import json
import shutil
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import psycopg
from psycopg import sql

from forecasting import areas, f2_build, load, settings

CHECK_SCHEMA = "chicago_check"
COMPARED_TABLES = [t for t in load.TABLES_IN_LOAD_ORDER]


def table_columns(conn: psycopg.Connection, schema: str, table: str) -> list[tuple[str, str]]:
    rows = conn.execute(
        "SELECT column_name, udt_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
        (schema, table),
    ).fetchall()
    return [(name, kind) for name, kind in rows if name != "id"]  # serial ids are numbering only


def compare_table(conn: psycopg.Connection, table: str, a: str = "chicago", b: str = CHECK_SCHEMA) -> dict[str, Any]:
    cols_a, cols_b = table_columns(conn, a, table), table_columns(conn, b, table)
    names_b = {name for name, _ in cols_b}
    cols = [(name, kind) for name, kind in cols_a if name in names_b]
    if not cols:
        return {"table": table, "same": False, "note": "table missing in one schema"}
    select = sql.SQL(", ").join(
        sql.SQL("ST_AsEWKB({})").format(sql.Identifier(n)) if k == "geometry" else sql.Identifier(n) for n, k in cols
    )

    def count(x: str, y: str) -> int:
        query = sql.SQL("SELECT count(*) FROM (SELECT {s} FROM {x}.{t} EXCEPT ALL SELECT {s} FROM {y}.{t}) d").format(
            s=select, x=sql.Identifier(x), y=sql.Identifier(y), t=sql.Identifier(table)
        )
        return conn.execute(query).fetchone()[0]

    rows_a = conn.execute(sql.SQL("SELECT count(*) FROM {}.{}").format(sql.Identifier(a), sql.Identifier(table))).fetchone()[0]
    only_a, only_b = count(a, b), count(b, a)
    return {"table": table, "rows": rows_a, "only_in_old": only_a, "only_in_new": only_b, "same": only_a == 0 and only_b == 0}


def same_array(x: np.ndarray, y: np.ndarray) -> bool:
    if x.shape != y.shape or x.dtype != y.dtype:
        return False
    if np.issubdtype(x.dtype, np.floating):
        return bool(np.array_equal(x, y, equal_nan=True))
    return bool(np.array_equal(x, y))


def compare_learning_tables(old: Path, new: Path) -> list[dict[str, Any]]:
    results = []
    for path in sorted(old.glob("*.npy")):
        other = new / path.name
        ok = other.exists() and same_array(np.load(path, mmap_mode="r"), np.load(other, mmap_mode="r"))
        results.append({"item": path.name, "same": ok})
    for kind in ("events", "duplicates"):  # matched reports per year: same pairs (the database may list them in another order)
        for path in sorted((old / kind).glob("*.npy")):
            other = new / kind / path.name
            if not other.exists():
                results.append({"item": f"{kind}/{path.name}", "same": False})
                continue
            x, y = np.load(path), np.load(other)
            sort = lambda a: a[np.lexsort(a.T[::-1])] if len(a) else a  # noqa: E731
            results.append({"item": f"{kind}/{path.name}", "same": x.shape == y.shape and bool(np.array_equal(sort(x), sort(y)))})
    sec_old = json.loads((old / "sections.json").read_text(encoding="utf-8"))
    sec_new = json.loads((new / "sections.json").read_text(encoding="utf-8"))
    results.append({"item": "sections.json", "same": sec_old == sec_new})
    meta_old = json.loads((old / "meta.json").read_text(encoding="utf-8"))
    meta_new = json.loads((new / "meta.json").read_text(encoding="utf-8"))
    keys = ["section_ids", "stations", "first_monday", "last_monday"]
    results.append({"item": "meta.json (sections, stations, Mondays)", "same": all(meta_old[k] == meta_new[k] for k in keys)})
    return results


def compare_validation_scores(
    store, rules: dict[str, Any], cfg: dict[str, Any], models_dir: Path, report_json: Path, saved_path: Path | None = None
) -> list[dict[str, Any]]:
    """Score each existing model on the validation year again; each finished model is saved (a re-run skips it)."""
    from forecasting.f2_test import load_models
    from forecasting.f2_train import periods, score, summarise

    stored = json.loads(report_json.read_text(encoding="utf-8"))["validation"]
    done = json.loads(saved_path.read_text(encoding="utf-8")) if saved_path and saved_path.exists() else {}
    predictors, _ = load_models(models_dir)  # stops if any model file changed since training (fingerprints)
    weeks = periods(store, rules, int(cfg["purge_days"]))["validation"]
    results = []
    for number, (name, (predict, drop)) in enumerate(predictors.items(), start=1):
        if name in done:
            print(f"  {clock()} model {number} of {len(predictors)} ({name}): already scored, skipped", flush=True)
            results.append(done[name])
            continue
        print(f"  {clock()} model {number} of {len(predictors)} ({name}): scoring the validation year", flush=True)
        summary = summarise(score(store, weeks, predict, rules, int(cfg["seed"]), drop), rules, int(cfg["bootstrap_ap_bins"]))
        new = json.loads(json.dumps(summary, default=str))
        row = {
            "model": name,
            "same": new == stored[name],
            "precision_top_1pct_old": stored[name]["all"]["precision_at_top_1pct"]["value"],
            "precision_top_1pct_new": new["all"]["precision_at_top_1pct"]["value"],
        }
        results.append(row)
        if saved_path:
            done[name] = row
            saved_path.write_text(json.dumps(done, indent=2), encoding="utf-8")
    return results


def clock() -> str:
    return datetime.now().strftime("%H:%M")


def already_loaded(conn: psycopg.Connection) -> str | None:
    """When the check schema holds a finished load (the load is all-or-nothing), the time it was loaded."""
    exists = conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = 'load_log'", (CHECK_SCHEMA,)
    ).fetchone()
    if not exists:
        return None
    row = conn.execute(sql.SQL("SELECT max(loaded_at)::text FROM {}.load_log").format(sql.Identifier(CHECK_SCHEMA))).fetchone()
    return row[0] if row else None


def run(url: str, area: areas.Area, rules: dict[str, Any], cfg: dict[str, Any]) -> tuple[Path, bool]:
    """Every part is saved when it finishes, so running again continues where it stopped."""
    from forecasting.f2_store import FeatureStore

    if area.key != "chicago":
        raise SystemExit("The same-results check is for Chicago (the area with saved results).")
    src = areas.ready_sources(area)
    check_dir = area.data_dir.parent / CHECK_SCHEMA / "f2"
    started = time.monotonic()
    with settings.connect(url) as conn:
        loaded = already_loaded(conn)
    if loaded:
        print(f"  {clock()} check 1/3: Chicago already reloaded into chicago_check ({loaded}), skipped", flush=True)
    else:
        print(
            f"  {clock()} check 1/3: reloading Chicago's raw files into chicago_check with the new code (about 10-25 minutes)", flush=True
        )
        load.run_load(url, area.raw_dir, src, rules, schema=CHECK_SCHEMA)
        print(f"  {clock()} reload finished", flush=True)
    with settings.connect(url) as conn:
        tables = [compare_table(conn, t) for t in COMPARED_TABLES]
    print(f"  {clock()} tables compared: {sum(t['same'] for t in tables)} of {len(tables)} identical", flush=True)
    print(f"  {clock()} check 2/3: building the learning table again (about 15-30 minutes; saved part by part)", flush=True)
    periods_cfg = rules["periods"]
    with settings.connect(url, CHECK_SCHEMA, autocommit=True) as conn:
        f2_build.build(
            conn,
            check_dir,
            date.fromisoformat(str(periods_cfg["train"]["start"])),
            date.fromisoformat(str(periods_cfg["test_locked"]["end"])),
            cfg,
            rules["target"]["match_distance_m"],
            fresh=False,  # continues after a stop; the saved parts belong to this exact reload (data stamp)
            crs=src["projected_crs"],
        )
    arrays = compare_learning_tables(area.f2_dir, check_dir)
    print(f"  {clock()} learning table compared: {sum(a['same'] for a in arrays)} of {len(arrays)} items identical", flush=True)
    print(f"  {clock()} check 3/3: scoring the existing models on the validation year (about 5 minutes)", flush=True)
    scores = compare_validation_scores(
        FeatureStore.load(check_dir),
        rules,
        cfg,
        area.models_dir,
        area.reports_dir / "f2-validation-report.json",
        saved_path=check_dir.parent / "scores-done.json",
    )
    passed = all(t["same"] for t in tables) and all(a["same"] for a in arrays) and all(s["same"] for s in scores)
    result = {
        "passed": passed,
        "tables": tables,
        "learning_table": arrays,
        "validation_scores": scores,
        "checked": date.today().isoformat(),
        "minutes_this_run": round((time.monotonic() - started) / 60, 1),
    }
    area.reports_dir.mkdir(parents=True, exist_ok=True)
    (area.reports_dir / "same-results-check.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    path = area.reports_dir / "same-results-check.md"
    path.write_text(markdown(result), encoding="utf-8")
    if passed:
        with settings.connect(url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(CHECK_SCHEMA)))
        shutil.rmtree(check_dir.parent, ignore_errors=True)
    print(f"  {clock()} done ({result['minutes_this_run']} minutes this run)", flush=True)
    return path, passed


def markdown(r: dict[str, Any]) -> str:
    def mark(ok: bool) -> str:
        return "same" if ok else "**DIFFERENT**"

    verdict = "PASSED: Chicago gives exactly the same results" if r["passed"] else "FAILED: see the rows marked DIFFERENT"
    lines = [
        "# Chicago same-results check (any-area code)",
        "",
        f"Checked {r['checked']}. Result: **{verdict}**.",
        "",
        "## 1. Database tables (reloaded from the same raw files)",
        "",
        "| Table | Rows | Only in old | Only in new | Result |",
        "|---|---|---|---|---|",
        *[
            f"| {t['table']} | {t.get('rows', '')} | {t.get('only_in_old', '')} | {t.get('only_in_new', '')} | {mark(t['same'])} |"
            for t in r["tables"]
        ],
        "",
        "## 2. Learning table (rebuilt)",
        "",
        f"{sum(a['same'] for a in r['learning_table'])} of {len(r['learning_table'])} items identical.",
        "",
        *[f"- {a['item']}: {mark(a['same'])}" for a in r["learning_table"] if not a["same"]],
        "",
        "## 3. Validation scores of the existing models",
        "",
        "| Model | Precision at top 1% before | Now | Result (all measures) |",
        "|---|---|---|---|",
        *[
            f"| {s['model']} | {s['precision_top_1pct_old']} | {s['precision_top_1pct_new']} | {mark(s['same'])} |"
            for s in r["validation_scores"]
        ],
        "",
        "The locked test was not run again (it is used up). Nothing in schema `chicago` or in data/chicago was changed.",
        "",
    ]
    return "\n".join(lines)
