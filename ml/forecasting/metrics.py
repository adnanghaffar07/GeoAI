"""F0 section 6 measures for the forecast, with 95% bootstrap ranges over forecast Mondays.

Each model is scored Monday by Monday on every section (no sampling). `rank` orders sections (higher = riskier);
`prob` is the probability used for the Brier score. They are the same for B1 and M; B0 ranks by its rule.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score


def top_mask(rank: np.ndarray, fraction: float, rng: np.random.Generator) -> np.ndarray:
    """The top `fraction` of rows by rank (at least one row); ties broken at random with a fixed seed."""
    k = max(1, math.ceil(fraction * len(rank)))
    order = np.lexsort((rng.random(len(rank)), -rank))  # sort by rank (desc), then random
    mask = np.zeros(len(rank), dtype=bool)
    mask[order[:k]] = True
    return mask


def weekly_stats(rank: np.ndarray, prob: np.ndarray, label: np.ndarray, rng: np.random.Generator, top_p: float, top_r: float) -> dict:
    top1 = top_mask(rank, top_p, rng)
    top10 = top_mask(rank, top_r, rng)
    positives = int(label.sum())
    return {
        "precision_top": float(label[top1].mean()),
        "recall_top": float(label[top10].sum() / positives) if positives else np.nan,
        "brier_sum": float(np.sum((prob - label) ** 2)),
        "rows": len(label),
        "positives": positives,
    }


def ap_from_histograms(pos: np.ndarray, neg: np.ndarray) -> float:
    """Average precision from per-bin positive/negative counts (bins ordered from highest to lowest score)."""
    tp, fp = np.cumsum(pos), np.cumsum(neg)
    total = tp[-1] if len(tp) else 0
    if total == 0:
        return float("nan")
    precision = tp / np.maximum(tp + fp, 1)
    return float(np.sum(precision * pos) / total)


class Scorer:
    """Collects one model's scores Monday by Monday for one subset of sections, then summarises with bootstrap ranges."""

    def __init__(self, top_p: float, top_r: float, seed: int):
        self.top_p, self.top_r, self.seed = top_p, top_r, seed
        self.weeks: list[dict] = []
        self.ranks: list[np.ndarray] = []
        self.probs: list[np.ndarray] = []
        self.labels: list[np.ndarray] = []

    def add(self, week_number: int, rank: np.ndarray, prob: np.ndarray, label: np.ndarray, winter: bool) -> None:
        rng = np.random.default_rng(self.seed + week_number)
        stats = weekly_stats(rank, prob, label, rng, self.top_p, self.top_r)
        stats["winter"] = winter
        self.weeks.append(stats)
        self.ranks.append(rank.astype(np.float32))
        self.probs.append(prob.astype(np.float32))
        self.labels.append(label.astype(np.int8))

    def calibration(self, bins: int = 10) -> list[tuple[float, float, int]]:
        return calibration_table(np.concatenate(self.probs), np.concatenate(self.labels), bins) if self.probs else []

    def summary(self, subset: str, resamples: int, bins: int) -> dict[str, Any]:
        picks = [i for i, w in enumerate(self.weeks) if subset != "winter" or w["winter"]]
        if not picks:
            return {}
        weeks = [self.weeks[i] for i in picks]
        rank = np.concatenate([self.ranks[i] for i in picks])
        label = np.concatenate([self.labels[i] for i in picks])
        precision = np.array([w["precision_top"] for w in weeks])
        recall = np.array([w["recall_top"] for w in weeks])
        brier_sum = np.array([w["brier_sum"] for w in weeks])
        rows = np.array([w["rows"] for w in weeks])
        positives = np.array([w["positives"] for w in weeks])
        pr_auc = float(average_precision_score(label, rank)) if label.any() else float("nan")

        # bootstrap: resample Mondays; PR-AUC from per-Monday score histograms (shared bins), the rest from weekly sums
        edges = np.unique(np.quantile(rank, np.linspace(0, 1, bins + 1)))
        hist_pos, hist_neg = [], []
        for i in picks:
            b = np.clip(np.searchsorted(edges, self.ranks[i], side="right") - 1, 0, max(len(edges) - 2, 0))
            hist_pos.append(np.bincount(b, weights=self.labels[i], minlength=max(len(edges) - 1, 1))[::-1])
            hist_neg.append(np.bincount(b, weights=1 - self.labels[i], minlength=max(len(edges) - 1, 1))[::-1])
        hist_pos, hist_neg = np.array(hist_pos), np.array(hist_neg)
        # the binned AP is close to, but not exactly, the exact AP (ties, bins): shift the bootstrap by the difference
        ap_shift = pr_auc - ap_from_histograms(hist_pos.sum(axis=0), hist_neg.sum(axis=0))
        rng = np.random.default_rng(self.seed)
        samples = {"precision_top": [], "recall_top": [], "brier": [], "pr_auc": []}
        for _ in range(resamples):
            idx = rng.integers(0, len(weeks), len(weeks))
            samples["precision_top"].append(precision[idx].mean())
            samples["recall_top"].append(np.nanmean(recall[idx]) if np.any(~np.isnan(recall[idx])) else np.nan)
            samples["brier"].append(brier_sum[idx].sum() / rows[idx].sum())
            samples["pr_auc"].append(ap_from_histograms(hist_pos[idx].sum(axis=0), hist_neg[idx].sum(axis=0)) + ap_shift)

        def with_range(value: float, name: str) -> dict:
            values = np.array(samples[name], dtype=float)
            values = values[~np.isnan(values)]
            low, high = np.quantile(values, [0.025, 0.975]) if len(values) else (np.nan, np.nan)
            return {"value": round(float(value), 4), "low": round(float(low), 4), "high": round(float(high), 4)}

        return {
            "mondays": len(weeks),
            "rows": int(rows.sum()),
            "base_rate": round(float(positives.sum() / rows.sum()), 4),
            "precision_at_top_1pct": with_range(precision.mean(), "precision_top"),
            "recall_at_top_10pct": with_range(np.nanmean(recall) if np.any(~np.isnan(recall)) else np.nan, "recall_top"),
            "pr_auc": with_range(pr_auc, "pr_auc"),
            "brier": with_range(brier_sum.sum() / rows.sum(), "brier"),
        }


def calibration_table(prob: np.ndarray, label: np.ndarray, bins: int = 10) -> list[tuple[float, float, int]]:
    """(mean predicted, observed rate, rows) per equal-count bin: '30% risk' should happen about 30% of the time."""
    order = np.argsort(prob)
    rows = []
    for chunk in np.array_split(order, bins):
        if len(chunk):
            rows.append((round(float(prob[chunk].mean()), 4), round(float(label[chunk].mean()), 4), int(len(chunk))))
    return rows
