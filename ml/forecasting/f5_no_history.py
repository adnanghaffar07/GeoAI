"""F5 experiment: can the Chicago model forecast WITHOUT a road's own report history?

Why: areas with no pothole reports (Kendall, Grundy, most of Lake, McHenry, Will and the other towns) have no
history inputs, so the Chicago model cannot be used there as it is. This trains the same B1 scorecard on the Chicago
TRAINING years using only inputs that exist everywhere (weather, road, elevation, flood, bus, season), then scores
it on the Chicago VALIDATION year next to the full B1 and the simple rule. The locked test period is never read.

Run from the ml/ folder:   python -m forecasting.f5_no_history
Result: forecasting/reports/chicago/f5-no-history-report.md (an exploratory check, not a pass/fail test).
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np

from forecasting import areas, settings
from forecasting.f2_build import HISTORY_WINDOWS
from forecasting.f2_store import EXTRA_HISTORY, NEIGHBOUR_WINDOWS, FeatureStore, feature_names
from forecasting.f2_train import (
    b0_prob,
    b0_rank,
    make_b1,
    periods,
    score,
    summarise,
    training_rows,
)

# Inputs built from a road's own (or its neighbours') pothole reports: not available in an area without reports.
HISTORY_INPUTS = (
    list(HISTORY_WINDOWS)
    + EXTRA_HISTORY
    + ["days_since_last_report"]
    + [f"neighbour_{name}" for name in NEIGHBOUR_WINDOWS]
)
# Chicago-only switch (old/new 311 system) and the traffic bands (only some states publish counts).
NOT_PORTABLE = ["new_311_system"]


def main() -> None:
    rules = settings.rules()
    cfg = settings.load_config("f2.yaml")
    area = areas.load_area("chicago")
    store = FeatureStore.load(area.f2_dir)
    seed = int(cfg["seed"])
    weeks = periods(store, rules, int(cfg["purge_days"]))
    bins = int(cfg["bootstrap_ap_bins"])
    drop = HISTORY_INPUTS + NOT_PORTABLE
    names_full = feature_names()
    names_free = feature_names(drop)
    print(f"Inputs: {len(names_full)} in the full model, {len(names_free)} without report history.", flush=True)

    print("Choosing training rows (same rule as F2) ...", flush=True)
    x, y, w, _sample = training_rows(store, weeks["train"], cfg["training_sample"], seed)
    keep = [i for i, n in enumerate(names_full) if n not in drop]
    rows = np.random.default_rng(seed).permutation(len(y))[: int(cfg["training_sample"].get("b1_max_rows", 1_000_000))]
    print("Training B1 without report history ...", flush=True)
    b1_free = make_b1(names_free).fit(x[rows][:, keep], y[rows], model__sample_weight=w[rows])
    del x, y, w

    b1_full = joblib.load(area.models_dir / "work" / "b1_logistic.joblib")
    table = json.loads((area.models_dir / "work" / "b0_table.json").read_text(encoding="utf-8"))["rates"]

    def b1_no_history(xm):
        p = b1_free.predict_proba(xm)[:, 1]
        return p, p

    def b1_with_history(xm):
        p = b1_full.predict_proba(xm)[:, 1]
        return p, p

    def b0_rule(xm):
        return b0_rank(xm), b0_prob(xm, table)

    models = {
        "B0 simple rule (needs history)": (b0_rule, None),
        "B1 full (needs history)": (b1_with_history, None),
        "B1 no history (works anywhere)": (b1_no_history, drop),
    }
    results = {}
    for name, (fn, dropped) in models.items():
        print(f"Scoring {name} on the validation year ...", flush=True)
        results[name] = summarise(score(store, weeks["validation"], fn, rules, seed, dropped), rules, bins)

    out = area.reports_dir / "f5-no-history-report.md"
    area.reports_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(report(results, names_free), encoding="utf-8")
    (area.reports_dir / "f5-no-history-report.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"Report written: {out}", flush=True)


def pick(summary: dict, key: str, field: str):
    value = summary.get(key, {}).get(field)
    return "n/a" if value is None else value


def report(results: dict, names_free: list[str]) -> str:
    lines = [
        "# F5: forecast without a road's own report history (Chicago validation year)",
        "",
        "Exploratory check on the validation year only. The locked test period was not read. "
        "Not a pass/fail test and not a reason to show tested levels anywhere.",
        "",
        f"Inputs used by the no-history model ({len(names_free)}): " + ", ".join(names_free) + ".",
        "",
        "| Model | Top-1% precision | PR-AUC | Winter top-1% | Held-out areas top-1% |",
        "|---|---|---|---|---|",
    ]
    for name, summary in results.items():
        row = [
            pick(summary, "all", "precision_at_top_1pct"),
            pick(summary, "all", "pr_auc"),
            pick(summary, "winter_nov_apr", "precision_at_top_1pct"),
            pick(summary, "held_out_areas", "precision_at_top_1pct"),
        ]
        lines.append(f"| {name} | " + " | ".join(_fmt(v) for v in row) + " |")
    lines += [
        "",
        "Read the first row as the bar to beat: it is the simple rule from the original F2. "
        "If the no-history model is clearly above chance but well below the full model, areas without reports can get "
        "a weaker, clearly labelled forecast. If it is close to chance, they should stay at Level 1.",
        "",
        "Raw summaries: f5-no-history-report.json.",
    ]
    return "\n".join(lines) + "\n"


def _fmt(value) -> str:
    if isinstance(value, dict):
        return f"{value['value']:.4f} ({value['low']:.4f}-{value['high']:.4f})"
    return str(value)


if __name__ == "__main__":
    main()
