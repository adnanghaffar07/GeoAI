# ruff: noqa: E501
"""Naperville plan N3: the transfer test. Does the Chicago model (forecast-chicago-0.2, used unchanged) pick out the
roads where another city's own pothole reports came, better than the simple F0 baseline (B0: reports in the last 90 days)?

- Nothing is trained or changed: the Chicago model file is only read (its fingerprint is checked, as in the app).
- The other city is never seen by the model, so this is a whole-city outside test.
- It is a locked test: it runs once (owner's go-ahead) and writes `transfer-test.json` / `.md` in the area's reports
  folder; a second run is refused. Pass marks: the same as Chicago's (config/acceptance-thresholds.yaml, PLACEHOLDER
  until PI-20). Only a PASS may switch the city to tested levels, and only with the owner's decision.
- Tables written: only `report_matches` / `report_match_log` in the city's own schema (rebuilt here).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import psycopg

from forecasting import weekly
from forecasting.f2_build import LABEL_WINDOW, day_number
from forecasting.f2_store import feature_names, is_winter
from forecasting.metrics import Scorer

RESULT_FILE = "transfer-test.json"


def mark_same_potholes(conn: psycopg.Connection, rule: dict[str, Any]) -> int:
    """A crew repair close to a residents' request made shortly before it is the same pothole (marked as a repeat)."""
    conn.execute(
        "UPDATE pothole_reports SET is_duplicate = false WHERE source = %(repairs)s",
        {"repairs": rule["system"]},
    )
    return conn.execute(
        """
        UPDATE pothole_reports r SET is_duplicate = true
        WHERE r.source = %(repairs)s AND r.geom IS NOT NULL AND EXISTS (
            SELECT 1 FROM pothole_reports q
            WHERE q.source = %(requests)s AND q.geom IS NOT NULL AND NOT q.is_duplicate
              AND q.created_at <= r.created_at AND q.created_at >= r.created_at - make_interval(days => %(days)s)
              AND ST_DWithin(q.geom::geography, r.geom::geography, %(metres)s))
        """,
        {"repairs": rule["system"], "requests": rule["of"], "days": rule["days"], "metres": rule["metres"]},
    ).rowcount


def test_mondays(first: date, newest_report: date) -> list[date]:
    """Every Monday from `first` whose 30-day answer window is complete."""
    last = newest_report - timedelta(days=-LABEL_WINDOW[1])
    monday = first + timedelta(days=(7 - first.weekday()) % 7)
    out = []
    while monday <= last:
        out.append(monday)
        monday += timedelta(days=7)
    return out


def labels(conn: psycopg.Connection, ids: list[str], monday: date) -> np.ndarray:
    """1 = at least one new (not repeat) report on the section in the Monday's 30 days."""
    start = day_number(monday)
    rows = conn.execute(
        "SELECT DISTINCT section_id FROM report_matches WHERE NOT is_duplicate AND day >= %s AND day < %s",
        (start, start - LABEL_WINDOW[1]),
    ).fetchall()
    found = {r[0] for r in rows}
    return np.array([1 if s in found else 0 for s in ids], dtype=np.int8)


def run(
    conn: psycopg.Connection,
    area,
    src: dict[str, Any],
    cfg: dict[str, Any],
    rules: dict[str, Any],
    models_dir: Path,
    first_monday: date,
    owner_go_ahead: bool,
) -> dict[str, Any]:
    from forecasting import live

    out_path = area.reports_dir / RESULT_FILE
    if out_path.exists():
        raise SystemExit(f"The transfer test for {area.name} has already run (locked test: once only). Result: {out_path}")
    if not owner_go_ahead:
        raise SystemExit("The transfer test is a locked test: run it only with the owner's go-ahead (--owner-go-ahead).")
    model, version = live.load_model(models_dir)  # fingerprint checked; never changed
    calibrator_path = models_dir / "b1_calibrator_v0.2.joblib"
    calibrator = joblib.load(calibrator_path) if calibrator_path.exists() else None
    b0 = json.loads((models_dir / "b0_table.json").read_text(encoding="utf-8"))
    names = feature_names()
    i90, ift = names.index("reports_90d"), names.index("freeze_thaw_14d")

    same = src.get("city_potholes", {}).get("same_pothole")
    repeats = mark_same_potholes(conn, same) if same else 0
    weekly.ensure_tables(conn)
    conn.execute("DELETE FROM report_matches")
    conn.execute("DELETE FROM report_match_log")
    matched = weekly.match_new_reports(conn, rules["target"]["match_distance_m"])
    conn.commit()
    newest = conn.execute("SELECT max(created_at)::date FROM pothole_reports").fetchone()[0]
    oldest = conn.execute("SELECT min(created_at)::date FROM pothole_reports").fetchone()[0]
    mondays = test_mondays(first_monday, newest)
    if not mondays:
        raise SystemExit("No Monday with a complete 30-day answer window yet.")

    measures, seed = rules["measures"], int(cfg.get("seed", 20261029))
    scorers = {name: Scorer(measures["precision_at_top_fraction"], measures["recall_at_top_fraction"], seed) for name in ("B1", "B0")}
    positives = 0
    sections = 0
    for number, monday in enumerate(mondays):
        store = weekly.monday_store(conn, monday, cfg, src["projected_crs"])
        x = store.matrix(0)
        y = labels(conn, store.meta["section_ids"], monday)
        sections, positives = len(y), positives + int(y.sum())
        raw = model.predict_proba(x)[:, 1]
        b1_prob = calibrator.predict(raw) if calibrator is not None else raw
        b0_rank = x[:, i90] + np.nan_to_num(x[:, ift]) / 1000
        b0_prob = np.array(b0["rates"])[np.minimum(x[:, i90], b0["cap"]).astype(int)]
        for name, rank, prob in (("B1", raw, b1_prob), ("B0", b0_rank, b0_prob)):
            scorers[name].add(number, rank, prob, y, is_winter(monday))
        print(f"  {monday}: {int(y.sum())} roads with a new report in the next 30 days", flush=True)

    resamples = int(measures.get("bootstrap", {}).get("resamples", 1000))
    results = {name: {"all": s.summary("all", resamples, 50), "winter": s.summary("winter", resamples, 50)} for name, s in scorers.items()}
    marks = rules["pass_marks"]

    def get(model_name: str, subset: str, measure: str) -> dict[str, float]:
        return results[model_name][subset].get(measure) or {"value": float("nan"), "low": float("nan")}

    def ratio(a: float, b: float) -> float:
        return a / b if b and b == b and b > 0 else float("inf") if a > 0 else float("nan")

    p1, p0 = get("B1", "all", "precision_at_top_1pct"), get("B0", "all", "precision_at_top_1pct")
    a1, a0 = get("B1", "all", "pr_auc"), get("B0", "all", "pr_auc")
    w1, w0 = get("B1", "winter", "precision_at_top_1pct"), get("B0", "winter", "precision_at_top_1pct")
    br1, br0 = results["B1"]["all"].get("brier", {}), results["B0"]["all"].get("brier", {})
    checks = {
        "1_precision_top_1pct_ratio": {
            "value": ratio(p1["value"], p0["value"]),
            "needed": f">= {marks['precision_at_top_1pct_ratio_min']}",
        },
        "2_precision_ci_low_above_baseline": {"value": p1["low"], "needed": f"> {p0['value']}"},
        "3_pr_auc_ratio": {"value": ratio(a1["value"], a0["value"]), "needed": f">= {marks['pr_auc_ratio_min']}"},
        "4_winter_precision_ratio": {
            "value": ratio(w1["value"], w0["value"]),
            "needed": f">= {marks['winter_precision_at_top_1pct_ratio_min']}",
        },
        "5_brier_better_than_baseline": {"value": (br1 or {}).get("value"), "needed": f"< {(br0 or {}).get('value')}"},
    }
    checks["1_precision_top_1pct_ratio"]["passed"] = (
        checks["1_precision_top_1pct_ratio"]["value"] >= marks["precision_at_top_1pct_ratio_min"]
    )
    checks["2_precision_ci_low_above_baseline"]["passed"] = (not marks["precision_at_top_1pct_ci_low_above_baseline"]) or p1["low"] > p0[
        "value"
    ]
    checks["3_pr_auc_ratio"]["passed"] = checks["3_pr_auc_ratio"]["value"] >= marks["pr_auc_ratio_min"]
    checks["4_winter_precision_ratio"]["passed"] = (
        checks["4_winter_precision_ratio"]["value"] >= marks["winter_precision_at_top_1pct_ratio_min"]
    )
    checks["5_brier_better_than_baseline"]["passed"] = bool(br1 and br0 and br1["value"] < br0["value"])
    passed = [bool(c["passed"]) for c in checks.values()]
    outcome = "PASS" if all(passed) else "FAIL" if not any(passed) else "PARTIAL"
    result = {
        "area": area.name,
        "model": version,
        "test_mondays": [str(mondays[0]), str(mondays[-1]), len(mondays)],
        "reports_from": str(oldest),
        "reports_to": str(newest),
        "sections": sections,
        "same_pothole_repeats_marked": repeats,
        "report_section_matches": matched,
        "section_mondays_with_a_new_report": positives,
        "results": results,
        "checks": {k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in checks.items()},
        "outcome": outcome,
        "pass_marks_note": "PLACEHOLDER pass marks until PI-20 (same as Chicago's).",
    }
    area.reports_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    (area.reports_dir / "transfer-test.md").write_text(markdown(result), encoding="utf-8")
    return result


def markdown(r: dict[str, Any]) -> str:
    def cell(model_name: str, subset: str, measure: str) -> str:
        m = r["results"][model_name][subset].get(measure)
        return "–" if not m else f"{m['value']} ({m['low']}–{m['high']})"

    lines = [
        f"# Transfer test: the Chicago model on {r['area']}",
        "",
        f"**Outcome: {r['outcome']}** ({r['pass_marks_note']})",
        "",
        f"Model `{r['model']}`, used unchanged. Test Mondays {r['test_mondays'][0]} to {r['test_mondays'][1]} "
        f"({r['test_mondays'][2]}). Reports {r['reports_from']} to {r['reports_to']}; {r['sections']:,} road sections; "
        f"{r['section_mondays_with_a_new_report']:,} section-Mondays with a new report in the next 30 days; "
        f"{r['same_pothole_repeats_marked']} crew repairs marked as the same pothole as a request.",
        "",
        "| Measure | Chicago model (B1) | Baseline B0 (reports in 90 days) |",
        "|---|---|---|",
    ]
    for measure, label in (("precision_at_top_1pct", "Precision, top 1% of roads"), ("recall_at_top_10pct", "Recall, top 10%"),
                           ("pr_auc", "PR-AUC"), ("brier", "Brier (lower is better)")):  # fmt: skip
        lines.append(f"| {label} | {cell('B1', 'all', measure)} | {cell('B0', 'all', measure)} |")
    lines.append(
        f"| Winter precision, top 1% | {cell('B1', 'winter', 'precision_at_top_1pct')} | {cell('B0', 'winter', 'precision_at_top_1pct')} |"
    )
    lines += ["", "| Check | Value | Needed | Passed |", "|---|---|---|---|"]
    for name, c in r["checks"].items():
        lines.append(f"| {name} | {c['value']} | {c['needed']} | {'yes' if c['passed'] else 'no'} |")
    lines += [
        "",
        "## Limits",
        "- The city's history starts in 2023, so the model's 3- and 5-year history inputs are shorter than in Chicago.",
        "- Few reports (about 150-190 a year): wide ranges; a FAIL can mean 'not enough data' as well as 'does not transfer'.",
        "- A report is a report, not an inspection; crew repairs are confirmed potholes.",
        "- Probabilities are Chicago's scale (much higher than here), so the Brier check mainly tests calibration.",
    ]
    return "\n".join(lines) + "\n"
