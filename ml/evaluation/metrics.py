"""How we mark the model (plan section 3). Used during training (pick the best epoch on the
validation set) and in P8.5 (the final, one-time score on the locked test set).

Rules:
- A detection is correct ("true positive") when it has the same class as a real box and overlaps
  it by at least 50% (IoU >= 0.5). Each real box can be found only once; extra detections of the
  same box are false alarms.
- Recall = correct detections / real boxes. Precision = correct detections / all detections.
- The confidence cut-off is chosen on validation as the best F1 (balance of recall and precision);
  on a tie the LOWER cut-off wins, so the model finds more.
- AP50 (average precision at IoU 0.5) summarises the whole precision/recall curve; used only to
  compare epochs during training.

Boxes are [x1, y1, x2, y2] in pixels. No severity, size or repair meaning: only "found / not found".
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

Box = Sequence[float]


@dataclass(frozen=True)
class Truth:
    class_id: int
    box: Box


@dataclass(frozen=True)
class Detection:
    class_id: int
    score: float
    box: Box


def iou(box: Box, boxes: np.ndarray) -> np.ndarray:
    """Overlap (intersection over union) between one box and many."""
    if len(boxes) == 0:
        return np.zeros(0)
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area = (box[2] - box[0]) * (box[3] - box[1])
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    union = area + areas - inter
    return np.where(union > 0, inter / np.where(union > 0, union, 1), 0.0)


@dataclass
class ClassMatches:
    """Every detection of one class across all images: its score and whether it was correct."""

    scores: np.ndarray
    correct: np.ndarray
    real_boxes: int


def match(truths: Iterable[Sequence[Truth]], detections: Iterable[Sequence[Detection]], iou_min: float = 0.5) -> dict[int, ClassMatches]:
    """Match detections to real boxes, image by image (same order in both lists)."""
    scores: dict[int, list[float]] = defaultdict(list)
    correct: dict[int, list[bool]] = defaultdict(list)
    real: dict[int, int] = defaultdict(int)
    for image_truths, image_detections in zip(truths, detections, strict=True):
        by_class: dict[int, list[Box]] = defaultdict(list)
        for truth in image_truths:
            by_class[truth.class_id].append(truth.box)
            real[truth.class_id] += 1
        found: dict[int, set[int]] = defaultdict(set)
        for detection in sorted(image_detections, key=lambda d: -d.score):
            candidates = np.asarray(by_class.get(detection.class_id, []), dtype=float).reshape(-1, 4)
            overlaps = iou(detection.box, candidates)
            best = int(np.argmax(overlaps)) if len(overlaps) else -1
            hit = best >= 0 and overlaps[best] >= iou_min and best not in found[detection.class_id]
            if hit:
                found[detection.class_id].add(best)
            scores[detection.class_id].append(detection.score)
            correct[detection.class_id].append(hit)
    classes = set(real) | set(scores)
    return {
        class_id: ClassMatches(np.asarray(scores[class_id], dtype=float), np.asarray(correct[class_id], dtype=bool), real[class_id])
        for class_id in sorted(classes)
    }


def _curve(matches: ClassMatches) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Precision and recall when the cut-off is set at each detection's score (highest first)."""
    order = np.argsort(-matches.scores, kind="stable")
    scores = matches.scores[order]
    true_positives = np.cumsum(matches.correct[order])
    detections = np.arange(1, len(scores) + 1)
    precision = true_positives / detections
    recall = true_positives / matches.real_boxes if matches.real_boxes else np.zeros(len(scores))
    return scores, precision, recall


def average_precision(matches: ClassMatches) -> float:
    """Area under the precision/recall curve (all-point interpolation, as in Pascal VOC 2010+)."""
    if matches.real_boxes == 0:
        return float("nan")
    _, precision, recall = _curve(matches)
    recall = np.concatenate([[0.0], recall, [recall[-1] if len(recall) else 0.0]])
    precision = np.concatenate([[1.0], precision, [0.0]])
    precision = np.maximum.accumulate(precision[::-1])[::-1]
    steps = np.nonzero(recall[1:] != recall[:-1])[0]
    return float(np.sum((recall[steps + 1] - recall[steps]) * precision[steps + 1]))


@dataclass(frozen=True)
class AtCutoff:
    cutoff: float
    recall: float
    precision: float
    f1: float
    found: int
    false_alarms: int
    real_boxes: int


def at_cutoff(matches: ClassMatches, cutoff: float) -> AtCutoff:
    """Recall, precision and F1 when only detections with score >= cutoff are reported."""
    keep = matches.scores >= cutoff
    found = int(np.sum(matches.correct & keep))
    reported = int(np.sum(keep))
    recall = found / matches.real_boxes if matches.real_boxes else 0.0
    precision = found / reported if reported else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return AtCutoff(cutoff, recall, precision, f1, found, reported - found, matches.real_boxes)


def best_f1_cutoff(matches: ClassMatches) -> AtCutoff:
    """The cut-off with the best F1; on a tie the lowest cut-off (plan section 3, rule 3)."""
    if len(matches.scores) == 0:
        return at_cutoff(matches, 1.0)
    candidates = sorted(set(matches.scores.tolist()))  # ascending, so ties keep the lowest
    best = at_cutoff(matches, candidates[0])
    for cutoff in candidates[1:]:
        result = at_cutoff(matches, cutoff)
        if result.f1 > best.f1 + 1e-12:
            best = result
    return best
