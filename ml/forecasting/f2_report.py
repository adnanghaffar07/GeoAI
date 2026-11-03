"""F2 reports in plain words: validation (settings may be tuned here) and the locked test (run once)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from forecasting.report import table

MODEL_NAMES = {
    "B0_rule": "B0 simple rule",
    "B1_logistic": "B1 statistics (logistic regression)",
    "M_lightgbm": "M main model (LightGBM)",
    "M_lightgbm_without_traffic": "M without traffic",
}
SUBSETS = {"all": "All sections", "winter_nov_apr": "Winter (Nov–Apr)", "held_out_areas": "Held-out community areas (never trained on)"}


def measure(cell: dict[str, Any]) -> str:
    return f"{cell['value']:.3f} ({cell['low']:.3f}–{cell['high']:.3f})"


def results_tables(results: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    for key, title in SUBSETS.items():
        rows = []
        for model, label in MODEL_NAMES.items():
            r = results.get(model, {}).get(key)
            if r:
                rows.append(
                    (
                        label,
                        measure(r["precision_at_top_1pct"]),
                        measure(r["recall_at_top_10pct"]),
                        measure(r["pr_auc"]),
                        measure(r["brier"]),
                        r["base_rate"],
                    )
                )
        if rows:
            any_model = next(iter(results.values()))[key]
            parts += [
                f"### {title}",
                f"{any_model['mondays']} Mondays, {any_model['rows']:,} section-Mondays. Values with 95% ranges.",
                "",
                table(
                    ["Model", "Precision at top 1% (higher better)", "Recall at top 10%", "PR-AUC", "Brier (lower better)", "Base rate"],
                    rows,
                ),
                "",
            ]
    return parts


def validation_markdown(result: dict[str, Any]) -> str:
    info, val = result["models"], result["validation"]
    m, b = val["M_lightgbm"]["all"], {k: val[k]["all"] for k in ("B0_rule", "B1_logistic")}
    best_p = max(v["precision_at_top_1pct"]["value"] for v in b.values())
    best_a = max(v["pr_auc"]["value"] for v in b.values())
    nt = val["M_lightgbm_without_traffic"]["all"]
    parts = [
        "# F2 validation report (Chicago forecast, TRIAL)",
        "",
        f"Model version {info['version']}, trained {info['trained_at']}. Training Mondays {info['train_mondays'][0]} to "
        f"{info['train_mondays'][1]}; validation Mondays {info['validation_mondays'][0]} to {info['validation_mondays'][1]} "
        "(the last Mondays of each period are left out so a 30-day answer never reaches the next period).",
        "",
        "**This is the validation year. Settings were chosen and probabilities calibrated on it, so these numbers are a little "
        "optimistic. The locked test (July 2022 – June 2025) has not been touched.**",
        "",
        "## In plain words",
        f"- Of the 1% of road sections each model ranks riskiest every Monday, the main model is right "
        f"{m['precision_at_top_1pct']['value']:.0%} of the time; the best simple baseline is right {best_p:.0%} of the time "
        f"(ratio {m['precision_at_top_1pct']['value'] / best_p if best_p else float('nan'):.2f}; the pass mark asks for 1.15).",
        f"- Overall ranking quality (PR-AUC): main {m['pr_auc']['value']:.3f} vs best baseline {best_a:.3f} "
        f"(ratio {m['pr_auc']['value'] / best_a if best_a else float('nan'):.2f}; pass mark 1.15).",
        f"- Without traffic the main model scores precision {nt['precision_at_top_1pct']['value']:.3f} and PR-AUC "
        f"{nt['pr_auc']['value']:.3f} (with traffic: {m['precision_at_top_1pct']['value']:.3f} / {m['pr_auc']['value']:.3f}). "
        "A large gap would mean traffic matters a lot; decision B says we then check it is not leaking the future.",
        f"- Base rate: {m['base_rate']:.1%} of section-Mondays get a new pothole report within 30 days.",
        "",
        "## Results",
        *results_tables(val),
        "## Calibration of the main model (validation)",
        "Each row is a tenth of all section-Mondays: when the model says X%, how often did it happen?",
        "",
        table(["Predicted (mean)", "Happened", "Rows"], val["M_lightgbm"]["calibration"]),
        "",
        "## What the main model relies on most (top 15, LightGBM gain)",
        table(["Input", "Gain"], info["feature_importance_gain"][:15]),
        "",
        "## Settings tried (chosen by validation PR-AUC)",
        table(["Settings", "Validation PR-AUC"], [(json.dumps(g["params"]), g["validation_pr_auc"]) for g in info["grid"]]),
        "",
        f"Training rows: {info['training_sample']}",
        "",
        "## Base rate per year (training and validation Mondays)",
        table(["Year", "Share of section-Mondays with a new report in 30 days"], result["base_rate_by_year"]),
        "",
        "## Next",
        "The owner reads this with Claude and decides whether to run the locked test (once), and with or without traffic.",
        "",
    ]
    return "\n".join(parts)


def test_markdown(result: dict[str, Any]) -> str:
    v = result["verdict"]
    check_rows = [
        (
            name,
            c.get("main", c.get("main_low")),
            c.get("best_baseline"),
            c.get("ratio", ""),
            c.get("needed", ""),
            "yes" if c["passed"] else "NO",
        )
        for name, c in v["checks"].items()
    ]
    parts = [
        "# F2 locked test report (Chicago forecast, TRIAL)",
        "",
        f"Run once with the owner's go-ahead: {result['usage']['started_at']} – {result['usage'].get('finished_at')}. "
        f"Test Mondays {result['test_mondays'][0]} to {result['test_mondays'][1]}. Main model: **{v['main_model']}**.",
        "",
        f"## Outcome: **{v['outcome']}** (pass marks are PLACEHOLDER until the partner confirms them, PI-20)",
        "",
        table(["Check", "Main model", "Best baseline", "Ratio", "Needed", "Passed"], check_rows),
        "",
        "## Results",
        *results_tables(result["test"]),
        "## Calibration of the main model (test)",
        table(["Predicted (mean)", "Happened", "Rows"], result["test"][v["main_model"]]["calibration"]),
        "",
        "## Outside check: Cook County pavement condition 2025 (never an input)",
        "```",
        json.dumps(result["cook_county_check"], indent=2),
        "```",
        "",
        "## Honest limits",
        "- The answer is a **311 pothole report**, not an inspection: busy, active neighbourhoods report more.",
        "- Roads are today's OpenStreetMap for all years; two airport weather stations cover the whole city.",
        "- Traffic counts are mostly from 2022–2025 (decision B); the model was also scored without traffic.",
        "- A forecast is a **chance**, not a confirmed defect. Shown in the app only as a TRIAL forecast to help choose where to inspect.",
        "- The test period is now used. Any new attempt needs a new, later test period (F0 section 7).",
        "",
    ]
    return "\n".join(parts)


def write(result: dict[str, Any], out_dir: Path, name: str, markdown: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    path = out_dir / f"{name}.md"
    path.write_text(markdown, encoding="utf-8")
    return path
