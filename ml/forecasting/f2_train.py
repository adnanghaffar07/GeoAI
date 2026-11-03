"""F2 step 2: train B0, B1 and M on the training period and score them on the validation period.

Settings are chosen on validation only. The locked test period is never read here (f2_test does that, once).
Saved in forecasting/models/: the models, the calibrators, and f2-models.json (settings, features, fingerprints).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import joblib
import lightgbm as lgb
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from forecasting.checkpoints import Checkpoints, Progress, save_array, stamp_of
from forecasting.f2_store import CATEGORICAL, FeatureStore, feature_names, is_winter, period_weeks
from forecasting.metrics import Scorer

B0_CAP = 10  # B0 probability table: one row per "reports in 90 days" value, 10 or more together


# ---------- rows ----------


def periods(store: FeatureStore, rules: dict[str, Any], purge_days: int) -> dict[str, np.ndarray]:
    p = rules["periods"]
    return {
        "train": period_weeks(store, p["train"], p["validation"]["start"], purge_days),
        "validation": period_weeks(store, p["validation"], p["test_locked"]["start"], purge_days),
    }


def training_rows(store: FeatureStore, weeks: np.ndarray, cfg: dict[str, Any], seed: int):
    """All positives and a share of negatives (held-out areas never included), with weights that undo the sampling."""
    eligible = ~store.held_out
    positives = sum(int(store.label(w)[eligible].sum()) for w in weeks)
    negatives = int(eligible.sum()) * len(weeks) - positives
    pos_frac, neg_frac = 1.0, float(cfg["negative_fraction"])
    expected = positives * pos_frac + negatives * neg_frac
    if expected > cfg["max_rows"]:
        scale = cfg["max_rows"] / expected
        pos_frac, neg_frac = pos_frac * scale, neg_frac * scale
    rng = np.random.default_rng(seed)
    xs, ys, ws = [], [], []
    progress = Progress("training Mondays sampled", len(weeks))
    for w in weeks:
        y = store.label(w)
        draw = rng.random(len(y))
        pick = eligible & (((y == 1) & (draw < pos_frac)) | ((y == 0) & (draw < neg_frac)))
        rows = np.flatnonzero(pick)
        xs.append(store.matrix(w, rows))
        ys.append(y[rows])
        ws.append(np.where(y[rows] == 1, 1 / pos_frac, 1 / neg_frac).astype(np.float32))
        progress.step()
    info = {"positives": positives, "negatives": negatives, "positive_fraction": pos_frac, "negative_fraction": neg_frac}
    return np.vstack(xs), np.concatenate(ys), np.concatenate(ws), info


# ---------- models ----------

FEATURE_INDEX = {name: i for i, name in enumerate(feature_names())}


def b0_rank(x: np.ndarray) -> np.ndarray:
    """F0 rule: reports in the last 90 days, ties broken by freeze-thaw days in the last 14 days."""
    return x[:, FEATURE_INDEX["reports_90d"]] + np.nan_to_num(x[:, FEATURE_INDEX["freeze_thaw_14d"]]) / 1000


def b0_table(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> list[float]:
    level = np.minimum(x[:, FEATURE_INDEX["reports_90d"]], B0_CAP).astype(int)
    overall = float(np.sum(w * y) / np.sum(w))
    table = []
    for value in range(B0_CAP + 1):
        mask = level == value
        table.append(float(np.sum(w[mask] * y[mask]) / np.sum(w[mask])) if mask.any() else overall)
    return table


def b0_prob(x: np.ndarray, table: list[float]) -> np.ndarray:
    return np.array(table)[np.minimum(x[:, FEATURE_INDEX["reports_90d"]], B0_CAP).astype(int)]


def make_b1(names: list[str]) -> Pipeline:
    numeric = [i for i, n in enumerate(names) if n not in CATEGORICAL]
    categorical = [i for i, n in enumerate(names) if n in CATEGORICAL]
    prepare = ColumnTransformer(
        [
            ("numbers", make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()), numeric),
            ("categories", OneHotEncoder(handle_unknown="ignore"), categorical),
        ]
    )
    return Pipeline([("prepare", prepare), ("model", LogisticRegression(max_iter=2000))])


def make_m(params: dict[str, Any], seed: int) -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(objective="binary", random_state=seed, n_jobs=-1, verbose=-1, **params)


def categorical_positions(names: list[str]) -> list[int]:
    return [i for i, n in enumerate(names) if n in CATEGORICAL]


# ---------- scoring ----------


def predict_weeks(store: FeatureStore, weeks: np.ndarray, predict, drop: list[str] | None = None):
    """Yield (w, rank, prob, label) for every section on every Monday in weeks."""
    for w in weeks:
        x = store.matrix(w, drop=drop)
        rank, prob = predict(x)
        yield w, rank, prob, store.label(w)


def score(store: FeatureStore, weeks: np.ndarray, predict, rules: dict[str, Any], seed: int, drop=None) -> dict[str, Scorer]:
    measures = rules["measures"]
    scorers = {
        "all": Scorer(measures["precision_at_top_fraction"], measures["recall_at_top_fraction"], seed),
        "held_out_areas": Scorer(measures["precision_at_top_fraction"], measures["recall_at_top_fraction"], seed),
    }
    held = store.held_out
    progress = Progress(f"{label_of(predict)} Mondays scored", len(weeks))
    for w, rank, prob, label in predict_weeks(store, weeks, predict, drop):
        progress.step()
        winter = is_winter(store.monday(w))
        scorers["all"].add(int(w), rank, prob, label, winter)
        if held.any():
            scorers["held_out_areas"].add(int(w), rank[held], prob[held], label[held], winter)
    return scorers


def summarise(scorers: dict[str, Scorer], rules: dict[str, Any], bins: int) -> dict[str, Any]:
    resamples = rules["measures"]["bootstrap"]["resamples"]
    return {
        "all": scorers["all"].summary("all", resamples, bins),
        "winter_nov_apr": scorers["all"].summary("winter", resamples, bins),
        "held_out_areas": scorers["held_out_areas"].summary("all", resamples, bins),
        "calibration": scorers["all"].calibration(),
    }


def label_of(predict) -> str:
    return getattr(predict, "__name__", "model")


def raw_scores(store: FeatureStore, weeks: np.ndarray, model, drop=None) -> tuple[np.ndarray, np.ndarray]:
    preds, labels = [], []
    progress = Progress("validation Mondays predicted", len(weeks))
    for w in weeks:
        progress.step()
        preds.append(model.predict_proba(store.matrix(w, drop=drop))[:, 1])
        labels.append(store.label(w))
    return np.concatenate(preds), np.concatenate(labels)


def make_predictors(table, b1, m, calibrator, m_nt, calibrator_nt, no_traffic: list[str]) -> dict[str, tuple[Any, list[str] | None]]:
    """name -> (function from feature rows to (rank, probability), features to drop)."""

    def b0(x):
        return b0_rank(x), b0_prob(x, table)

    b0.__name__ = "B0 rule"

    def logistic(x):
        p = b1.predict_proba(x)[:, 1]
        return p, p

    logistic.__name__ = "B1 statistics"

    # Rank by the model's raw score; calibrate only the probability. Calibration makes steps (many equal values),
    # which would turn part of the top-1% list into a random draw.
    def main(x):
        raw = m.predict_proba(x)[:, 1]
        return raw, calibrator.predict(raw)

    def main_without_traffic(x):
        raw = m_nt.predict_proba(x)[:, 1]
        return raw, calibrator_nt.predict(raw)

    main.__name__ = "main model"
    main_without_traffic.__name__ = "main model without traffic"

    return {
        "B0_rule": (b0, None),
        "B1_logistic": (logistic, None),
        "M_lightgbm": (main, None),
        "M_lightgbm_without_traffic": (main_without_traffic, no_traffic),
    }


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------- the whole training step (saved part by part; a re-run continues) ----------

TRAIN_VERSION = 2


class BoosterModel:
    """A saved LightGBM model with the predict_proba shape the predictors expect."""

    def __init__(self, path: Path):
        self.booster = lgb.Booster(model_file=str(path))

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        p = self.booster.predict(x)
        return np.column_stack([1 - p, p])


def train_and_validate(
    store: FeatureStore,
    rules: dict[str, Any],
    cfg: dict[str, Any],
    models_dir: Path,
    fresh: bool = False,
    version: str = "forecast-chicago-0.1",
) -> dict[str, Any]:
    seed = int(cfg["seed"])
    weeks = periods(store, rules, int(cfg["purge_days"]))
    if len(weeks["train"]) == 0 or len(weeks["validation"]) == 0:
        raise SystemExit("The learning table has no training or validation Mondays. Rebuild it with `forecasting.run f2-build`.")
    names = feature_names()
    no_traffic = list(cfg["traffic_features"])
    names_nt = feature_names(no_traffic)
    work = models_dir / "work"
    cp = Checkpoints(work, stamp_of(TRAIN_VERSION, store.meta.get("stamp"), names, cfg, rules["periods"], rules["measures"]), fresh)
    total_steps = 5 + len(cfg["lightgbm_grid"])
    step = iter(range(1, total_steps + 1))

    # 1. training rows
    if not cp.done("training_rows"):
        print(f"  step {next(step)}/{total_steps}: choosing training rows", flush=True)
        x, y, w, sample = training_rows(store, weeks["train"], cfg["training_sample"], seed)
        for name, values in (("x", x), ("y", y), ("w", w)):
            save_array(work, name, values)
        cp.mark("training_rows", sample)
    else:
        next(step)
    x, y, w = (np.load(work / f"{name}.npy") for name in ("x", "y", "w"))
    sample = cp.info("training_rows")
    print(f"  training rows: {len(y):,} ({int(y.sum()):,} positives)", flush=True)

    # 2. B0 table and B1
    if not cp.done("b0_b1"):
        print(f"  step {next(step)}/{total_steps}: B0 rule table and B1 statistics model (a few minutes)", flush=True)
        (work / "b0_table.json").write_text(json.dumps({"cap": B0_CAP, "rates": b0_table(x, y, w)}), encoding="utf-8")
        b1_rows = np.random.default_rng(seed).permutation(len(y))[: int(cfg["training_sample"].get("b1_max_rows", 1_000_000))]
        joblib.dump(make_b1(names).fit(x[b1_rows], y[b1_rows], model__sample_weight=w[b1_rows]), work / "b1_logistic.joblib")
        cp.mark("b0_b1")
    else:
        next(step)
    table = json.loads((work / "b0_table.json").read_text(encoding="utf-8"))["rates"]
    b1 = joblib.load(work / "b1_logistic.joblib")

    # 3. M: each setting of the small grid, scored on validation PR-AUC
    for k, params in enumerate(cfg["lightgbm_grid"]):
        if not cp.done(f"grid_{k}"):
            print(
                f"  step {next(step)}/{total_steps}: main model, setting {k + 1} of {len(cfg['lightgbm_grid'])} {params}",
                flush=True,
            )
            model = make_m(params, seed).fit(x, y, sample_weight=w, categorical_feature=categorical_positions(names))
            model.booster_.save_model(str(work / f"m_grid_{k}.txt"))
            raw, labels = raw_scores(store, weeks["validation"], BoosterModel(work / f"m_grid_{k}.txt"))
            save_array(work, f"val_raw_{k}", raw)
            save_array(work, "val_labels", labels)
            pr_auc = float(average_precision_score(labels, raw)) if labels.any() else float("nan")
            cp.mark(f"grid_{k}", {"params": params, "validation_pr_auc": round(pr_auc, 4)})
            print(f"  setting {k + 1}: validation PR-AUC {pr_auc:.4f}", flush=True)
        else:
            next(step)
    grid_results = [cp.info(f"grid_{k}") for k in range(len(cfg["lightgbm_grid"]))]
    best_k = max(range(len(grid_results)), key=lambda k: grid_results[k]["validation_pr_auc"])
    best_params = grid_results[best_k]["params"]
    val_labels = np.load(work / "val_labels.npy")

    # 4. calibration of the best setting
    if not cp.done("calibrator"):
        print(f"  step {next(step)}/{total_steps}: calibrating probabilities (best setting {best_k + 1})", flush=True)
        joblib.dump(
            IsotonicRegression(out_of_bounds="clip").fit(np.load(work / f"val_raw_{best_k}.npy"), val_labels), work / "m_calibrator.joblib"
        )
        cp.mark("calibrator", best_k)
    else:
        next(step)

    # 5. the same model without traffic (decision B check)
    if not cp.done("no_traffic"):
        print(f"  step {next(step)}/{total_steps}: main model WITHOUT traffic (a few minutes)", flush=True)
        keep_nt = [i for i, n in enumerate(names) if n not in no_traffic]
        model = make_m(best_params, seed).fit(x[:, keep_nt], y, sample_weight=w, categorical_feature=categorical_positions(names_nt))
        model.booster_.save_model(str(work / "m_lightgbm_without_traffic.txt"))
        raw, labels = raw_scores(store, weeks["validation"], BoosterModel(work / "m_lightgbm_without_traffic.txt"), drop=no_traffic)
        joblib.dump(IsotonicRegression(out_of_bounds="clip").fit(raw, labels), work / "m_calibrator_without_traffic.joblib")
        cp.mark("no_traffic")
    else:
        next(step)
    del x, y, w

    # 6. score all four models on every validation Monday (each model saved when done)
    print(f"  step {next(step)}/{total_steps}: scoring the four models on the validation year", flush=True)
    predictors = make_predictors(
        table,
        b1,
        BoosterModel(work / f"m_grid_{best_k}.txt"),
        joblib.load(work / "m_calibrator.joblib"),
        BoosterModel(work / "m_lightgbm_without_traffic.txt"),
        joblib.load(work / "m_calibrator_without_traffic.joblib"),
        no_traffic,
    )
    bins = int(cfg["bootstrap_ap_bins"])
    for name, (fn, drop) in predictors.items():
        if not cp.done(f"score_{name}"):
            cp.mark(f"score_{name}", summarise(score(store, weeks["validation"], fn, rules, seed, drop), rules, bins))
    results = {name: cp.info(f"score_{name}") for name in predictors}

    # finished: copy the final model files out of work/ and fingerprint them
    models_dir.mkdir(parents=True, exist_ok=True)
    finals = {
        "b0_table.json": "b0_table.json",
        "b1_logistic.joblib": "b1_logistic.joblib",
        f"m_grid_{best_k}.txt": "m_lightgbm.txt",
        "m_lightgbm_without_traffic.txt": "m_lightgbm_without_traffic.txt",
        "m_calibrator.joblib": "m_calibrator.joblib",
        "m_calibrator_without_traffic.joblib": "m_calibrator_without_traffic.joblib",
    }
    for source, target in finals.items():
        (models_dir / target).write_bytes((work / source).read_bytes())
    gains = lgb.Booster(model_file=str(models_dir / "m_lightgbm.txt")).feature_importance("gain").tolist()
    importance = sorted(zip(names, gains, strict=True), key=lambda t: -t[1])
    info = {
        "version": version,
        "trained_at": date.today().isoformat(),
        "features": names,
        "features_without_traffic": names_nt,
        "best_params": best_params,
        "grid": grid_results,
        "training_sample": sample,
        "train_mondays": [str(store.monday(int(weeks["train"][0]))), str(store.monday(int(weeks["train"][-1])))],
        "validation_mondays": [str(store.monday(int(weeks["validation"][0]))), str(store.monday(int(weeks["validation"][-1])))],
        "fingerprints": {target: fingerprint(models_dir / target) for target in finals.values()},
        "feature_importance_gain": [(n, round(g, 1)) for n, g in importance],
    }
    (models_dir / "f2-models.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return {"models": info, "validation": results, "base_rate_by_year": base_rate_by_year(store, np.concatenate(list(weeks.values())))}


def base_rate_by_year(store: FeatureStore, weeks: np.ndarray) -> list[tuple[str, float]]:
    totals: dict[int, list[float]] = {}
    for w in weeks:
        year = store.monday(int(w)).year
        totals.setdefault(year, []).append(float(store.label(w).mean()))
    return [(str(year), round(float(np.mean(values)), 4)) for year, values in sorted(totals.items())]
