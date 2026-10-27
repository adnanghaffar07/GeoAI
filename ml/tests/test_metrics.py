"""The scoring rules (plan section 3) checked on small hand-made cases."""

import math

import numpy as np
import pytest

from evaluation.metrics import Detection, Truth, at_cutoff, average_precision, best_f1_cutoff, iou, match

POTHOLE, CRACK = 1, 2


def test_iou() -> None:
    boxes = np.array([[0, 0, 10, 10], [5, 0, 15, 10], [20, 20, 30, 30]], dtype=float)
    assert iou([0, 0, 10, 10], boxes).tolist() == pytest.approx([1.0, 50 / 150, 0.0])


def test_a_correct_find_needs_the_same_class_and_half_overlap() -> None:
    truths = [[Truth(POTHOLE, [0, 0, 10, 10])]]
    cases = {
        "same class, exact box": (Detection(POTHOLE, 0.9, [0, 0, 10, 10]), True),
        "same class, IoU 0.5": (Detection(POTHOLE, 0.9, [0, 0, 10, 5]), True),
        "same class, IoU 0.33": (Detection(POTHOLE, 0.9, [5, 0, 15, 10]), False),
        "wrong class": (Detection(CRACK, 0.9, [0, 0, 10, 10]), False),
    }
    for name, (detection, expected) in cases.items():
        result = match(truths, [[detection]])
        assert bool(result[detection.class_id].correct[0]) is expected, name


def test_each_real_box_is_found_only_once() -> None:
    truths = [[Truth(POTHOLE, [0, 0, 10, 10])]]
    detections = [[Detection(POTHOLE, 0.6, [0, 0, 10, 10]), Detection(POTHOLE, 0.9, [1, 1, 10, 10])]]
    result = match(truths, detections)[POTHOLE]
    # Highest score is matched first; the duplicate counts as a false alarm.
    assert dict(zip(result.scores.tolist(), result.correct.tolist(), strict=True)) == {0.9: True, 0.6: False}
    assert result.real_boxes == 1


def test_recall_precision_f1_at_a_cutoff() -> None:
    truths = [[Truth(POTHOLE, [0, 0, 10, 10]), Truth(POTHOLE, [20, 20, 30, 30])], [Truth(POTHOLE, [0, 0, 10, 10])], []]
    detections = [
        [Detection(POTHOLE, 0.9, [0, 0, 10, 10]), Detection(POTHOLE, 0.3, [20, 20, 30, 30])],
        [Detection(POTHOLE, 0.8, [50, 50, 60, 60])],  # false alarm
        [Detection(POTHOLE, 0.7, [0, 0, 5, 5])],  # false alarm on a clean road
    ]
    result = match(truths, detections)[POTHOLE]
    high = at_cutoff(result, 0.5)
    assert (high.found, high.false_alarms, high.real_boxes) == (1, 2, 3)
    assert high.recall == pytest.approx(1 / 3) and high.precision == pytest.approx(1 / 3)
    low = at_cutoff(result, 0.2)
    assert low.recall == pytest.approx(2 / 3) and low.precision == pytest.approx(2 / 4)
    assert low.f1 == pytest.approx(2 * (2 / 3) * 0.5 / (2 / 3 + 0.5))


def test_best_f1_prefers_the_lower_cutoff_on_a_tie() -> None:
    truths = [[Truth(POTHOLE, [0, 0, 10, 10])], [Truth(POTHOLE, [0, 0, 10, 10])]]
    # Cut-off 0.9: 1 of 2 found, no false alarm -> P=1, R=0.5, F1=0.667.
    # Cut-off 0.4: 2 of 2 found, 1 false alarm -> P=0.667, R=1, F1=0.8 (better).
    detections = [
        [Detection(POTHOLE, 0.9, [0, 0, 10, 10]), Detection(POTHOLE, 0.5, [50, 50, 60, 60])],
        [Detection(POTHOLE, 0.4, [0, 0, 10, 10])],
    ]
    best = best_f1_cutoff(match(truths, detections)[POTHOLE])
    assert best.cutoff == 0.4 and best.f1 == pytest.approx(0.8)

    tie_truths = [[Truth(POTHOLE, [0, 0, 10, 10])]]
    tie = [[Detection(POTHOLE, 0.9, [0, 0, 10, 10]), Detection(CRACK, 0.2, [0, 0, 1, 1])]]
    # Any cut-off up to 0.9 gives the same F1 for potholes; the lowest available (0.9 itself) wins.
    assert best_f1_cutoff(match(tie_truths, tie)[POTHOLE]).cutoff == 0.9


def test_average_precision() -> None:
    truths = [[Truth(POTHOLE, [0, 0, 10, 10]), Truth(POTHOLE, [20, 20, 30, 30])]]
    perfect = [[Detection(POTHOLE, 0.9, [0, 0, 10, 10]), Detection(POTHOLE, 0.8, [20, 20, 30, 30])]]
    assert average_precision(match(truths, perfect)[POTHOLE]) == pytest.approx(1.0)
    # Ranked: hit, miss, hit -> precision 1 at recall 0.5, 2/3 at recall 1 -> AP = 0.5*1 + 0.5*2/3.
    mixed = [
        [Detection(POTHOLE, 0.9, [0, 0, 10, 10]), Detection(POTHOLE, 0.8, [50, 50, 60, 60]), Detection(POTHOLE, 0.7, [20, 20, 30, 30])]
    ]
    assert average_precision(match(truths, mixed)[POTHOLE]) == pytest.approx(0.5 + 0.5 * 2 / 3)
    assert average_precision(match(truths, [[]])[POTHOLE]) == 0.0
    assert math.isnan(average_precision(match([[]], [[Detection(CRACK, 0.5, [0, 0, 1, 1])]])[CRACK]))
