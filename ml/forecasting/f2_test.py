"""F2 step 3: the locked test, run ONCE, only with the owner's go-ahead (F0 section 5; plan section 2).

A usage file (reports/f2-test-usage.json) blocks a second run once the test has FINISHED. If a run stops part-way
(crash, power cut), the file says "started": running again continues where it stopped (each model's scores are saved in
reports/f2-test-work/); no result has been shown yet, so this is still one test.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import psycopg
from scipy.stats import spearmanr

from forecasting.checkpoints import Checkpoints, save_array, stamp_of
from forecasting.f2_store import FeatureStore, period_weeks
from forecasting.f2_train import BoosterModel, fingerprint, make_predictors, score, summarise

UTC_TZ = timezone.utc  # noqa: UP017 (also runs on Python 3.10)
MAIN_MODELS = {"with_traffic": "M_lightgbm", "without_traffic": "M_lightgbm_without_traffic"}
BASELINES = ["B0_rule", "B1_logistic"]


def load_models(models_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    info = json.loads((models_dir / "f2-models.json").read_text(encoding="utf-8"))
    for name, expected in info["fingerprints"].items():
        if fingerprint(models_dir / name) != expected:
            raise SystemExit(f"{name} changed since training (fingerprint mismatch). The locked test needs the trained models.")
    table = json.loads((models_dir / "b0_table.json").read_text(encoding="utf-8"))["rates"]
    no_traffic = [n for n in info["features"] if n not in info["features_without_traffic"]]
    predictors = make_predictors(
        table,
        joblib.load(models_dir / "b1_logistic.joblib"),
        BoosterModel(models_dir / "m_lightgbm.txt"),
        joblib.load(models_dir / "m_calibrator.joblib"),
        BoosterModel(models_dir / "m_lightgbm_without_traffic.txt"),
        joblib.load(models_dir / "m_calibrator_without_traffic.joblib"),
        no_traffic,
    )
    return predictors, info


def check_pass_marks(results: dict[str, Any], main: str, marks: dict[str, Any]) -> dict[str, Any]:
    """F0 section 7: the main model against the BEST baseline. Lower Brier is better."""

    def value(model: str, subset: str, measure: str) -> float:
        return results[model][subset][measure]["value"]

    def best(subset: str, measure: str) -> float:
        return max(value(b, subset, measure) for b in BASELINES)

    def ratio(a: float, b: float) -> float:
        return a / b if b > 0 else float("inf")

    p_main, p_base = value(main, "all", "precision_at_top_1pct"), best("all", "precision_at_top_1pct")
    checks = {
        "1_precision_top_1pct_ratio": {
            "main": p_main,
            "best_baseline": p_base,
            "ratio": round(ratio(p_main, p_base), 3),
            "needed": f">= {marks['precision_at_top_1pct_ratio_min']}",
            "passed": ratio(p_main, p_base) >= marks["precision_at_top_1pct_ratio_min"],
        },
        "1b_precision_range_above_baseline": {
            "main_low": results[main]["all"]["precision_at_top_1pct"]["low"],
            "best_baseline": p_base,
            "passed": (not marks["precision_at_top_1pct_ci_low_above_baseline"])
            or results[main]["all"]["precision_at_top_1pct"]["low"] > p_base,
        },
    }
    a_main, a_base = value(main, "all", "pr_auc"), best("all", "pr_auc")
    checks["2_pr_auc_ratio"] = {
        "main": a_main,
        "best_baseline": a_base,
        "ratio": round(ratio(a_main, a_base), 3),
        "needed": f">= {marks['pr_auc_ratio_min']}",
        "passed": ratio(a_main, a_base) >= marks["pr_auc_ratio_min"],
    }
    b_main = value(main, "all", "brier")
    b_base = min(value(b, "all", "brier") for b in BASELINES)
    checks["3_brier_better_than_both"] = {"main": b_main, "best_baseline": b_base, "passed": b_main < b_base}
    for key, subset, mark in (
        ("4_winter_precision_ratio", "winter_nov_apr", "winter_precision_at_top_1pct_ratio_min"),
        ("5_held_out_areas_precision_ratio", "held_out_areas", "held_out_areas_precision_at_top_1pct_ratio_min"),
    ):
        m_val, b_val = value(main, subset, "precision_at_top_1pct"), best(subset, "precision_at_top_1pct")
        checks[key] = {
            "main": m_val,
            "best_baseline": b_val,
            "ratio": round(ratio(m_val, b_val), 3),
            "needed": f">= {marks[mark]}",
            "passed": ratio(m_val, b_val) >= marks[mark],
        }
    passed = [c["passed"] for c in checks.values()]
    outcome = "PASS" if all(passed) else "FAIL" if not any(passed) else "PARTIAL"
    return {"main_model": main, "checks": checks, "outcome": outcome}


def cook_county_check(conn: psycopg.Connection, store: FeatureStore, mean_risk: np.ndarray) -> dict[str, Any]:
    """Outside check (never an input): do sections the model finds riskier have lower Cook County PCI (2025)?"""
    # Exact-distance sort, not the KNN operator <->: KNN on the geography index raised
    # "index returned tuples in wrong order" on the laptop (2026-10-29). ST_DWithin still uses the index.
    rows = conn.execute(
        "SELECT s.section_id, (SELECT p.pci FROM pavement_condition_cook p WHERE p.pci IS NOT NULL "
        " AND ST_DWithin(p.geom::geography, ST_LineInterpolatePoint(s.geom, 0.5)::geography, 15) "
        " ORDER BY ST_Distance(p.geom::geography, ST_LineInterpolatePoint(s.geom, 0.5)::geography) LIMIT 1) "
        "FROM road_sections s"
    ).fetchall()
    position = {sid: i for i, sid in enumerate(store.meta["section_ids"])}
    pairs = [(mean_risk[position[sid]], pci) for sid, pci in rows if pci is not None and sid in position]
    if len(pairs) < 30:
        return {"matched_sections": len(pairs), "note": "too few sections with a Cook County PCI score for a check"}
    risk, pci = np.array(pairs).T
    top = risk >= np.quantile(risk, 0.9)
    rho, p_value = spearmanr(risk, pci)
    return {
        "matched_sections": len(pairs),
        "spearman_risk_vs_pci": round(float(rho), 3),
        "p_value": float(p_value),
        "mean_pci_riskiest_10pct": round(float(pci[top].mean()), 1),
        "mean_pci_other_90pct": round(float(pci[~top].mean()), 1),
        "reading": "a negative correlation (riskier sections have lower PCI) supports the forecast; PCI is from 2025, one survey",
    }


def run_locked_test(
    store: FeatureStore, rules: dict[str, Any], cfg: dict[str, Any], models_dir: Path, reports_dir: Path, main_model: str, conn=None
) -> dict[str, Any]:
    usage_path = reports_dir / "f2-test-usage.json"
    if usage_path.exists() and json.loads(usage_path.read_text(encoding="utf-8")).get("status") == "finished":
        raise SystemExit(
            "The locked test has already been run (reports/f2-test-usage.json). It is never run twice: a new test period is "
            "needed for another try (F0 section 7). Talk to Claude and record any decision in project-decisions.md."
        )
    if main_model not in MAIN_MODELS:
        raise SystemExit(f"main model must be one of {list(MAIN_MODELS)}")
    predictors, info = load_models(models_dir)
    p = rules["periods"]
    weeks = period_weeks(store, p["test_locked"], None, 0)
    if len(weeks) == 0:
        raise SystemExit("The learning table has no test Mondays.")
    reports_dir.mkdir(parents=True, exist_ok=True)
    started = json.loads(usage_path.read_text(encoding="utf-8")) if usage_path.exists() else None
    if started and started.get("main_model") != main_model:
        raise SystemExit(f"A test with the {started.get('main_model')} main model was started; continue it with that choice.")
    usage = started or {"status": "started", "started_at": datetime.now(UTC_TZ).isoformat(timespec="seconds"), "main_model": main_model}
    usage_path.write_text(json.dumps(usage, indent=2), encoding="utf-8")

    seed = int(cfg["seed"])
    bins = int(cfg["bootstrap_ap_bins"])
    work = reports_dir / "f2-test-work"
    cp = Checkpoints(work, stamp_of(info["fingerprints"], main_model, store.meta.get("stamp"), rules["measures"]))
    main_name = MAIN_MODELS[main_model]
    for number, (name, (predict, drop)) in enumerate(predictors.items(), start=1):
        if cp.done(name):
            continue
        print(f"  model {number} of {len(predictors)}: {name}", flush=True)
        if name == main_name:
            total = np.zeros(store.n_sections)

            def tracked(x, predict=predict, total=total):
                rank, prob = predict(x)
                total[:] += prob
                return rank, prob

            tracked.__name__ = name
            summary = summarise(score(store, weeks, tracked, rules, seed, drop), rules, bins)
            save_array(work, "main_mean_risk", total / len(weeks))
        else:
            summary = summarise(score(store, weeks, predict, rules, seed, drop), rules, bins)
        cp.mark(name, summary)
    results = {name: cp.info(name) for name in predictors}
    mean_risk = np.load(work / "main_mean_risk.npy")

    verdict = check_pass_marks(results, MAIN_MODELS[main_model], rules["pass_marks"])
    outside = cook_county_check(conn, store, mean_risk) if conn is not None else {"note": "no database connection"}
    usage.update({"status": "finished", "finished_at": datetime.now(UTC_TZ).isoformat(timespec="seconds"), "outcome": verdict["outcome"]})
    usage_path.write_text(json.dumps(usage, indent=2), encoding="utf-8")
    test_mondays = [str(store.monday(int(weeks[0]))), str(store.monday(int(weeks[-1])))]
    return {"models": info, "test": results, "verdict": verdict, "cook_county_check": outside, "test_mondays": test_mondays, "usage": usage}
