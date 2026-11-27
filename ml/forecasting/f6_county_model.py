# ruff: noqa: E501
"""F6 experiment: does a model that also learns from the counties' own pothole reports forecast them better than the
Chicago model (forecast-chicago-0.2, used unchanged)?

Areas (they already have tested levels): dupage_central, cook_suburbs, cook_northwest, naperville, aurora.
Method (fixed BEFORE looking at any result; development evidence only, never a pass/fail test):
- Leave one area out: a model is trained WITHOUT the area it is scored on, so the score is a whole-area outside check.
- Scored on the same Mondays each area's transfer test used (read from its transfer-test.json). No locked test is
  re-run and no tested level is changed. A real pass/fail test of any new model needs Mondays after 2026-11-24.
- Models: C   = Chicago B1 as in the app; B0 = simple rule (reports in the last 90 days);
          K1  = scorecard (same 41 inputs as B1, no old/new-311 switch) trained on the OTHER four counties only;
          K2  = the same scorecard trained on Chicago training years PLUS the other four counties, counties weighted
                to count as much as Chicago (weights otherwise undo the sampling of negatives).
- "Clear improvement" (decided now): K beats C on top-1% precision AND PR-AUC in at least 4 of the 5 areas, and the
  average top-1% precision ratio K / C is at least 1.10. Otherwise the Chicago model stays.

Run from the ml/ folder (needs the forecast database running):   python -m forecasting.f6_county_model
First run builds a cache of weekly input tables per area (about 20-60 minutes); it continues after a stop.
Result: forecasting/reports/counties/f6-county-model-report.md / .json
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from forecasting import areas, live, settings, transfer, weekly
from forecasting.f2_store import FeatureStore, feature_names, is_winter
from forecasting.f2_train import make_b1, periods, training_rows
from forecasting.metrics import Scorer

AREAS = ["dupage_central", "cook_suburbs", "cook_northwest", "naperville", "aurora"]
NEGATIVE_FRACTION = 0.10  # share of negative section-Mondays kept for training (weights undo it)
CHICAGO_ROWS = 500_000
DROP = ["new_311_system"]


def cache_dir(area) -> Path:
    return area.raw_dir.parent / "f6_cache"


def test_window(area) -> tuple[date, date]:
    """First and last Monday of the area's own transfer test (already run), so labels are complete."""
    result = json.loads((area.reports_dir / "transfer-test.json").read_text(encoding="utf-8"))
    first, last = result["test_mondays"][0], result["test_mondays"][1]
    return date.fromisoformat(str(first)), date.fromisoformat(str(last))


def mondays_of(area) -> list[date]:
    first, last = test_window(area)
    out, monday = [], first
    while monday <= last:
        out.append(monday)
        monday += timedelta(days=7)
    return out


def build_cache(key: str, cfg: dict, rules: dict) -> None:
    area = areas.load_area(key)
    src = areas.ready_sources(area)
    cfg = dict(cfg)
    cfg["snow_station"] = src.get("snow_station", cfg["snow_station"])
    folder = cache_dir(area)
    folder.mkdir(parents=True, exist_ok=True)
    mondays = mondays_of(area)
    todo = [m for m in mondays if not (folder / f"{m}.npz").exists()]
    print(f"{key}: {len(mondays)} Mondays, {len(todo)} still to build", flush=True)
    if not todo:
        return
    with settings.connect(settings.database_url(), area.schema) as conn:
        have = conn.execute("SELECT count(*) FROM report_matches").fetchone()[0]
        if not have:  # same rebuild as the transfer test does (only this area's report_matches tables are touched)
            print(f"  {key}: report_matches is empty, rebuilding it like the transfer test", flush=True)
            same = src.get("city_potholes", {}).get("same_pothole")
            if same:
                transfer.mark_same_potholes(conn, same)
            weekly.ensure_tables(conn)
            conn.execute("DELETE FROM report_matches")
            conn.execute("DELETE FROM report_match_log")
            weekly.match_new_reports(conn, rules["target"]["match_distance_m"])
            conn.commit()
            if not conn.execute("SELECT count(*) FROM report_matches").fetchone()[0]:
                raise SystemExit(f"{key}: no pothole reports could be matched to road sections. Run its prepare script first.")
        for number, monday in enumerate(todo):
            store = weekly.monday_store(conn, monday, cfg, src["projected_crs"])
            x = store.matrix(0).astype(np.float32)
            y = transfer.labels(conn, store.meta["section_ids"], monday)
            np.savez_compressed(folder / f"{monday}.npz", x=x, y=y)
            if number % 20 == 0:
                print(f"  {key}: {number + 1}/{len(todo)}", flush=True)


def load_week(area, monday: date) -> tuple[np.ndarray, np.ndarray]:
    with np.load(cache_dir(area) / f"{monday}.npz") as z:
        return z["x"], z["y"]


def county_sample(key: str, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """All positive rows and a share of negative rows of one area, with weights that undo the sampling."""
    area = areas.load_area(key)
    rng = np.random.default_rng(seed)
    xs, ys, ws = [], [], []
    for monday in mondays_of(area):
        x, y = load_week(area, monday)
        pick = (y == 1) | (rng.random(len(y)) < NEGATIVE_FRACTION)
        xs.append(x[pick])
        ys.append(y[pick])
        ws.append(np.where(y[pick] == 1, 1.0, 1 / NEGATIVE_FRACTION).astype(np.float32))
    return np.vstack(xs), np.concatenate(ys), np.concatenate(ws)


def fit(names: list[str], keep: list[int], x: np.ndarray, y: np.ndarray, w: np.ndarray):
    return make_b1(names).fit(x[:, keep], y, model__sample_weight=w)


def main() -> None:
    rules = settings.rules()
    cfg = settings.load_config("f2.yaml")
    seed = int(cfg["seed"])
    chicago = areas.load_area("chicago")
    names_full = feature_names()
    names = feature_names(DROP)
    keep = [i for i, n in enumerate(names_full) if n not in DROP]
    i90, ift = names_full.index("reports_90d"), names_full.index("freeze_thaw_14d")

    for key in AREAS:
        build_cache(key, cfg, rules)

    print("Sampling each county's training rows ...", flush=True)
    samples = {key: county_sample(key, seed) for key in AREAS}

    print("Chicago training rows (same rule as F2) ...", flush=True)
    store = FeatureStore.load(chicago.f2_dir)
    weeks = periods(store, rules, int(cfg["purge_days"]))
    cx, cy, cw, _info = training_rows(store, weeks["train"], cfg["training_sample"], seed)
    pick = np.random.default_rng(seed).permutation(len(cy))[:CHICAGO_ROWS]
    cx, cy, cw = cx[pick], cy[pick], cw[pick]
    del store

    model_c, version = live.load_model(chicago.models_dir)
    b0 = json.loads((chicago.models_dir / "b0_table.json").read_text(encoding="utf-8"))
    measures = rules["measures"]
    resamples = int(measures.get("bootstrap", {}).get("resamples", 1000))

    results: dict[str, dict] = {}
    for held in AREAS:
        others = [k for k in AREAS if k != held]
        print(f"Training K1 and K2 without {held} ...", flush=True)
        ox = np.vstack([samples[k][0] for k in others])
        oy = np.concatenate([samples[k][1] for k in others])
        ow = np.concatenate([samples[k][2] for k in others])
        k1 = fit(names, keep, ox, oy, ow)
        scale = float(cw.sum() / ow.sum())  # counties count as much as Chicago
        k2 = fit(
            names,
            keep,
            np.vstack([cx, ox]),
            np.concatenate([cy, oy]),
            np.concatenate([cw, ow * scale]),
        )
        area = areas.load_area(held)
        scorers = {n: Scorer(measures["precision_at_top_fraction"], measures["recall_at_top_fraction"], seed) for n in ("C", "B0", "K1", "K2")}
        for number, monday in enumerate(mondays_of(area)):
            x, y = load_week(area, monday)
            raw = model_c.predict_proba(x)[:, 1]
            b0_rank = x[:, i90] + np.nan_to_num(x[:, ift]) / 1000
            b0_prob = np.array(b0["rates"])[np.minimum(x[:, i90], b0["cap"]).astype(int)]
            p1 = k1.predict_proba(x[:, keep])[:, 1]
            p2 = k2.predict_proba(x[:, keep])[:, 1]
            winter = is_winter(monday)
            for n, rank, prob in (("C", raw, raw), ("B0", b0_rank, b0_prob), ("K1", p1, p1), ("K2", p2, p2)):
                scorers[n].add(number, rank, prob, y, winter)
        results[held] = {n: {"all": s.summary("all", resamples, 50)} for n, s in scorers.items()}
        print(f"  scored {held}", flush=True)

    out = chicago.reports_dir.parent / "counties"
    out.mkdir(parents=True, exist_ok=True)
    (out / "f6-county-model-report.json").write_text(json.dumps({"model_c": version, "results": results}, indent=2, default=str), encoding="utf-8")
    (out / "f6-county-model-report.md").write_text(report(results, version), encoding="utf-8")
    print(f"Report written: {out / 'f6-county-model-report.md'}", flush=True)


def value(summary: dict, key: str) -> float:
    item = summary.get(key) or {}
    v = item.get("value")
    return float("nan") if v is None else float(v)


def cell(summary: dict, key: str) -> str:
    item = summary.get(key) or {}
    if "value" not in item:
        return "n/a"
    low, high = item.get("low"), item.get("high")
    if low is None or high is None:
        return f"{item['value']:.4f}"
    return f"{item['value']:.4f} ({low:.4f}-{high:.4f})"


def report(results: dict, version: str) -> str:
    lines = [
        "# F6: county-trained models against the Chicago model (leave one area out)",
        "",
        f"Chicago model `{version}` as in the app (C). B0 = simple rule. K1 = scorecard trained on the other four counties. "
        "K2 = scorecard trained on Chicago plus the other four counties. Each area is scored on the Mondays of its own "
        "transfer test, without being in the training data of K1 and K2. **Development evidence only**: those Mondays "
        "were already used to test C, and no tested level changes. A new model needs a pass/fail test on Mondays after 2026-11-24.",
        "",
    ]
    wins = {"K1": 0, "K2": 0}
    ratios = {"K1": [], "K2": []}
    for area, models in results.items():
        lines += [f"## {area}", "", "| Model | Top-1% precision | Top-10% recall | PR-AUC |", "|---|---|---|---|"]
        for n in ("C", "B0", "K1", "K2"):
            s = models[n]["all"]
            lines.append(f"| {n} | {cell(s, 'precision_at_top_1pct')} | {cell(s, 'recall_at_top_10pct')} | {cell(s, 'pr_auc')} |")
        lines.append("")
        c = models["C"]["all"]
        for k in ("K1", "K2"):
            s = models[k]["all"]
            pc, pk = value(c, "precision_at_top_1pct"), value(s, "precision_at_top_1pct")
            ac, ak = value(c, "pr_auc"), value(s, "pr_auc")
            if pk > pc and ak > ac:
                wins[k] += 1
            if pc > 0:
                ratios[k].append(pk / pc)
    lines += ["## Verdict (rule fixed in advance)", "", "| Model | Areas better than C on precision and PR-AUC | Average precision ratio K / C |", "|---|---|---|"]
    for k in ("K1", "K2"):
        avg = sum(ratios[k]) / len(ratios[k]) if ratios[k] else float("nan")
        verdict = "CLEAR IMPROVEMENT" if wins[k] >= 4 and avg >= 1.10 else "not clear"
        lines.append(f"| {k} | {wins[k]} of {len(results)} | {avg:.2f}: {verdict} |")
    lines += [
        "",
        "Reading: if neither K1 nor K2 is a clear improvement, the Chicago model stays, and the next gains must come from new inputs "
        "or more months of county reports. If one is, the next step is a fresh pass/fail test on Mondays after 2026-11-24 "
        "(spring or summer 2027) before it replaces anything. Reports, not potholes; pass marks are placeholders (PI-20).",
        "",
        "Raw summaries: f6-county-model-report.json.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
