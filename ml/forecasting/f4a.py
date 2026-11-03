"""F4a: refresh the Chicago model before any percentage is shown in the app (plan: documentation/04-design/forecasting-f4-plan.md §2).

1. Learning table extended to the latest Monday whose 30-day answer is complete (data/chicago/f4a/, saved part by part).
   Its Mondays up to the locked test's end must match the F2 learning table exactly (checked).
2. Fresh check: the EXISTING models (forecast-chicago-0.1, fingerprints checked) on the months after the locked test,
   which no model has ever seen. An extra check, reported next to the locked test; not a new F0 pass/fail test.
3. Percentage check, honest: B1 trained only on Mondays before year Y1, calibrated on Y1, then judged on the latest year Y2
   (unseen by both). The owner decides from this whether the app shows percentages (F4-D2).
4. The new model forecast-chicago-0.2: B1 with the same settings on ALL Mondays, and a calibrator fitted on Y2 predictions
   of a B1 trained before Y2 (so the calibrator never saw its own training rows). Fingerprints in models/chicago/f4a-models.json.

Every finished part is saved (reports/chicago/f4a-work/); running again continues where it stopped.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.isotonic import IsotonicRegression

from forecasting.checkpoints import Checkpoints, stamp_of
from forecasting.f2_build import EPOCH, day_number
from forecasting.f2_store import FeatureStore, feature_names
from forecasting.f2_train import fingerprint, make_b1, score, summarise, training_rows
from forecasting.metrics import calibration_table

F4A_VERSION = 1
YEAR = 52  # Mondays


def last_complete_monday(last_report_day: date, horizon_days: int = 30) -> date:
    """The latest Monday whose answer window (the Monday and the next 29 days) ends on or before the last report day."""
    day = last_report_day - timedelta(days=horizon_days - 1)
    return day - timedelta(days=day.weekday())


def weeks_between(store: FeatureStore, first: date | None, last_plus_purge: date | None, purge_days: int) -> np.ndarray:
    """Mondays >= first whose answer window ends before last_plus_purge (the start of the next block)."""
    keep = np.ones(len(store.weeks), dtype=bool)
    if first is not None:
        keep &= store.weeks >= day_number(first)
    if last_plus_purge is not None:
        keep &= store.weeks + purge_days <= day_number(last_plus_purge)
    return np.flatnonzero(keep)


def monday_of(store: FeatureStore, w: int) -> date:
    return EPOCH + timedelta(days=int(store.weeks[w]))


def compare_overlap(old: FeatureStore, new: FeatureStore) -> dict[str, Any]:
    """The extended table must repeat the F2 table exactly on the Mondays both have."""
    n = len(old.weeks)
    same_weeks = bool(np.array_equal(old.weeks, new.weeks[:n]))
    checked, different = [], []
    for name in ("label", "reports_30d", "reports_365d", "reports_same_season_3y", "duplicate_reports_90d", "last_report_day"):
        checked.append(name)
        if not np.array_equal(np.asarray(old.a[name]), np.asarray(new.a[name][:n])):
            different.append(name)
    for name in [k for k in old.a if k.startswith("weather__")]:
        checked.append(name)
        if not np.array_equal(np.asarray(old.a[name]), np.asarray(new.a[name])[:, :n], equal_nan=True):
            different.append(name)
    for name in [k for k in old.a if k.startswith("static__")] + ["held_out", "station_of_section"]:
        checked.append(name)
        if not np.array_equal(np.asarray(old.a[name]), np.asarray(new.a[name]), equal_nan=True):
            different.append(name)
    same_sections = old.meta["section_ids"] == new.meta["section_ids"]
    return {"same": same_weeks and same_sections and not different, "items_checked": len(checked), "different": different}


def b1_predictor(model, calibrator=None, name: str = "B1"):
    def predict(x):
        p = model.predict_proba(x)[:, 1]
        return p, (calibrator.predict(p) if calibrator is not None else p)

    predict.__name__ = name
    return predict


def raw_predictions(store: FeatureStore, weeks: np.ndarray, model) -> tuple[np.ndarray, np.ndarray]:
    preds, labels = [], []
    for w in weeks:
        preds.append(model.predict_proba(store.matrix(int(w)))[:, 1])
        labels.append(np.asarray(store.label(int(w))))
    return np.concatenate(preds), np.concatenate(labels)


def fit_b1(store: FeatureStore, weeks: np.ndarray, cfg: dict[str, Any], seed: int):
    x, y, w, info = training_rows(store, weeks, cfg["training_sample"], seed)
    rows = np.random.default_rng(seed).permutation(len(y))[: int(cfg["training_sample"].get("b1_max_rows", 1_000_000))]
    model = make_b1(feature_names()).fit(x[rows], y[rows], model__sample_weight=w[rows])
    return model, info


def calibration_gap(table: list) -> float:
    """Largest difference (in points of probability) between predicted and observed, over the ten groups."""
    return round(max(abs(pred - seen) for pred, seen, _ in table), 4) if table else float("nan")


def run(
    store_new: FeatureStore,
    store_f2: FeatureStore,
    rules: dict[str, Any],
    cfg: dict[str, Any],
    models_dir: Path,
    reports_dir: Path,
) -> dict[str, Any]:
    from forecasting.f2_test import load_models

    seed, purge, bins = int(cfg["seed"]), int(cfg["purge_days"]), int(cfg["bootstrap_ap_bins"])
    work = reports_dir / "f4a-work"
    cp = Checkpoints(work, stamp_of(F4A_VERSION, store_new.meta.get("stamp"), cfg, rules["periods"], rules["measures"]))
    test_end = date.fromisoformat(str(rules["periods"]["test_locked"]["end"]))
    fresh_start = test_end + timedelta(days=purge + (7 - (test_end + timedelta(days=purge)).weekday()) % 7)  # first Monday after
    last_w = len(store_new.weeks) - 1
    y2_first_w = last_w - YEAR + 1
    y1_first_w = y2_first_w - YEAR
    y2_start, y1_start = monday_of(store_new, y2_first_w), monday_of(store_new, y1_first_w)
    periods = {
        "fresh_check": [str(fresh_start), str(monday_of(store_new, last_w))],
        "year_1_calibration": [str(y1_start), str(y2_start - timedelta(days=7))],
        "year_2_judging": [str(y2_start), str(monday_of(store_new, last_w))],
    }
    fc, y1, y2 = periods["fresh_check"], periods["year_1_calibration"], periods["year_2_judging"]
    print(f"  fresh check {fc}; percentage check: calibrate {y1}, judge {y2}", flush=True)

    # 1. the extended table repeats the F2 table
    if not cp.done("overlap"):
        print("  part 1/5: checking the extended learning table against the F2 table", flush=True)
        cp.mark("overlap", compare_overlap(store_f2, store_new))
    overlap = cp.info("overlap")

    # 2. fresh check of the existing models on the never-used months
    predictors, info_v01 = load_models(models_dir)
    fresh_weeks = weeks_between(store_new, fresh_start, None, purge)
    for name, (predict, drop) in predictors.items():
        if not cp.done(f"fresh_{name}"):
            print(f"  part 2/5: fresh check, {name}", flush=True)
            cp.mark(f"fresh_{name}", summarise(score(store_new, fresh_weeks, predict, rules, seed, drop), rules, bins))
    fresh = {name: cp.info(f"fresh_{name}") for name in predictors}

    # 3. honest percentage check: model A (before Y1) + calibrator on Y1, judged on Y2
    first_train = date.fromisoformat(str(rules["periods"]["train"]["start"]))
    if not cp.done("percentage_check"):
        print("  part 3/5: percentage check (train before year 1, calibrate on year 1, judge on year 2; about 10 minutes)", flush=True)
        model_a, _ = fit_b1(store_new, weeks_between(store_new, first_train, y1_start, purge), cfg, seed)
        p1, l1 = raw_predictions(store_new, weeks_between(store_new, y1_start, y2_start, purge), model_a)
        calibrator_a = IsotonicRegression(out_of_bounds="clip").fit(p1, l1)
        y2_weeks = np.arange(y2_first_w, last_w + 1)
        p2, l2 = raw_predictions(store_new, y2_weeks, model_a)
        raw_table, cal_table = calibration_table(p2, l2), calibration_table(calibrator_a.predict(p2), l2)
        judged = summarise(
            score(store_new, y2_weeks, b1_predictor(model_a, calibrator_a, "B1 (before year 1) + calibration"), rules, seed), rules, bins
        )
        cp.mark(
            "percentage_check",
            {
                "raw": {"table": raw_table, "largest_gap": calibration_gap(raw_table)},
                "calibrated": {"table": cal_table, "largest_gap": calibration_gap(cal_table)},
                "scores_year_2": judged,
            },
        )
    percentage = cp.info("percentage_check")

    # 4. the new model 0.2 and its calibrator
    if not cp.done("model_v02"):
        print("  part 4/5: training forecast-chicago-0.2 (B1 on all Mondays) and its calibrator (about 10 minutes)", flush=True)
        model_b, _ = fit_b1(store_new, weeks_between(store_new, first_train, y2_start, purge), cfg, seed)
        p2, l2 = raw_predictions(store_new, np.arange(y2_first_w, last_w + 1), model_b)
        calibrator = IsotonicRegression(out_of_bounds="clip").fit(p2, l2)
        final, sample = fit_b1(store_new, weeks_between(store_new, first_train, None, purge), cfg, seed)
        models_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(final, models_dir / "b1_logistic_v0.2.joblib")
        joblib.dump(calibrator, models_dir / "b1_calibrator_v0.2.joblib")
        cp.mark("model_v02", {"training_sample": sample})
    files = ["b1_logistic_v0.2.joblib", "b1_calibrator_v0.2.joblib"]
    models_info = {
        "version": "forecast-chicago-0.2",
        "made": date.today().isoformat(),
        "model": "B1 logistic regression, same settings and inputs as forecast-chicago-0.1",
        "trained_on_mondays": [str(monday_of(store_new, 0)), str(monday_of(store_new, last_w))],
        "calibrator": f"isotonic, fitted on {periods['year_2_judging']} predictions of a B1 trained before that year",
        "features": feature_names(),
        "training_sample": cp.info("model_v02")["training_sample"],
        "fingerprints": {name: fingerprint(models_dir / name) for name in files},
        "replaces_for_the_app": info_v01["version"],
    }
    (models_dir / "f4a-models.json").write_text(json.dumps(models_info, indent=2), encoding="utf-8")

    # 5. what the owner decides from (F4-D2)
    b0, b1 = fresh["B0_rule"]["all"]["precision_at_top_1pct"], fresh["B1_logistic"]["all"]["precision_at_top_1pct"]
    criteria = {
        "fresh_b1_beats_b0": bool(b1["low"] > b0["value"]),
        "fresh_b1_to_b0_ratio": round(b1["value"] / b0["value"], 3) if b0["value"] else None,
        "calibrated_largest_gap": percentage["calibrated"]["largest_gap"],
        "percentages_close": bool(percentage["calibrated"]["largest_gap"] <= 0.02),
    }
    criteria["suggestion"] = (
        "show percentages for Chicago (TRIAL)" if criteria["fresh_b1_beats_b0"] and criteria["percentages_close"] else "show levels only"
    )
    print("  part 5/5: report", flush=True)
    return {
        "periods": periods,
        "overlap_with_f2": overlap,
        "fresh_check": fresh,
        "percentage_check": percentage,
        "model_v02": models_info,
        "criteria": criteria,
    }


def markdown(r: dict[str, Any]) -> str:
    def pct(v: dict) -> str:
        return f"{v['value']:.3f} ({v['low']:.3f}-{v['high']:.3f})"

    c, p, fr, per = r["criteria"], r["percentage_check"], r["fresh_check"], r["periods"]
    b1_top = 100 * fr["B1_logistic"]["all"]["precision_at_top_1pct"]["value"]
    b0_top = 100 * fr["B0_rule"]["all"]["precision_at_top_1pct"]["value"]
    base = 100 * fr["B1_logistic"]["all"]["base_rate"]
    beats = "still clearly beats" if c["fresh_b1_beats_b0"] else "does NOT clearly beat"
    overlap = r["overlap_with_f2"]
    same = "yes" if overlap["same"] else "NO: " + ", ".join(overlap["different"])
    lines = [
        "# F4a: Chicago model refresh (TRIAL)",
        "",
        f"Fresh check on never-used Mondays {per['fresh_check'][0]} to {per['fresh_check'][1]} "
        "(after the locked test; an extra check, not a new F0 pass/fail test).",
        "",
        "## In plain words",
        f"- On the newest months, B1 is right {b1_top:.0f}% of the time in its riskiest 1% of roads "
        f"(simple rule: {b0_top:.0f}%; base rate {base:.1f}%). B1 {beats} the simple rule (ratio {c['fresh_b1_to_b0_ratio']}).",
        f"- Percentages after calibration are off by at most {100 * c['calibrated_largest_gap']:.1f} points in the latest year "
        f"(without calibration: {100 * p['raw']['largest_gap']:.1f} points). Rule for showing percentages: at most 2 points.",
        f"- **Suggestion (owner decides, F4-D2): {c['suggestion']}.**",
        f"- Extended learning table repeats the F2 table exactly: {same} ({overlap['items_checked']} items checked).",
        "",
        "## Fresh check (existing models, forecast-chicago-0.1)",
        "",
        "| Model | Precision at top 1% | Recall at top 10% | PR-AUC | Brier | Winter precision | Held-out areas precision |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, s in fr.items():
        a = s["all"]
        lines.append(
            f"| {name} | {pct(a['precision_at_top_1pct'])} | {a['recall_at_top_10pct']['value']:.3f} | {a['pr_auc']['value']:.3f} | "
            f"{a['brier']['value']:.4f} | {s['winter_nov_apr']['precision_at_top_1pct']['value']:.3f} | "
            f"{s['held_out_areas']['precision_at_top_1pct']['value']:.3f} |"
        )
    lines += [
        "",
        f"## Percentage check (B1 trained before {per['year_1_calibration'][0]}, calibrated on year 1, "
        f"judged on year 2: {per['year_2_judging'][0]} to {per['year_2_judging'][1]})",
        "",
        "| Group (low to high risk) | Raw: predicted | Raw: happened | Calibrated: predicted | Calibrated: happened |",
        "|---|---|---|---|---|",
    ]
    for k, (raw, cal) in enumerate(zip(p["raw"]["table"], p["calibrated"]["table"], strict=False), start=1):
        lines.append(f"| {k} | {100 * raw[0]:.1f}% | {100 * raw[1]:.1f}% | {100 * cal[0]:.1f}% | {100 * cal[1]:.1f}% |")
    m = r["model_v02"]
    lines += [
        "",
        f"## New model {m['version']}",
        f"{m['model']}; trained on Mondays {m['trained_on_mondays'][0]} to {m['trained_on_mondays'][1]}; calibrator: {m['calibrator']}.",
        "Files and fingerprints: `models/chicago/f4a-models.json`. The app uses it only after the owner's decision.",
        "",
        "Honest limit: after retraining on all data there is no unseen period left for this exact model; the percentage check above "
        "uses the same method on a model trained one year earlier, and the app will compare forecasts with real outcomes every month.",
        "",
    ]
    return "\n".join(lines)
