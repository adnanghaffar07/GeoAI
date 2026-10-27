"""The AI result checker (model output contract v1) and the test detector.

No database needed. Covers AC-20 (a result that breaks the contract is rejected whole).
"""

import copy
from pathlib import Path
from typing import Any

import pytest

from app.ai import stand_in
from app.ai.contract import InvalidModelOutputError, validate_output
from app.ai.registry import UnknownModelError, get_model, is_stand_in
from tests.photos import make_photo

CLASSES = frozenset({"pothole", "surface_cracking"})
IMAGE_ID = "11111111-1111-1111-1111-111111111111"


def _note(**changes: Any) -> dict[str, Any]:
    note: dict[str, Any] = {
        "contract_version": 1,
        "model_version": "m-1",
        "image_id": IMAGE_ID,
        "status": "ok",
        "failure_reason": None,
        "image_width_px": 400,
        "image_height_px": 300,
        "candidates": [
            {
                "detection_index": 0,
                "class_key": "pothole",
                "confidence": 0.8,
                "bbox_px": [10, 20, 110, 120],
            }
        ],
        "processing_ms": 5,
    }
    note.update(changes)
    return note


def _check(note: Any) -> Any:
    return validate_output(
        note, expected_image_id=IMAGE_ID, expected_model_version="m-1", allowed_classes=CLASSES
    )


def test_a_valid_note_is_accepted() -> None:
    output = _check(_note())

    assert output.status == "ok"
    assert len(output.candidates) == 1
    assert output.candidates[0].bbox_px == (10, 20, 110, 120)
    assert output.candidates[0].confidence == 0.8


def test_an_empty_result_is_valid() -> None:
    """Empty means "no candidates found", not "the road is fine"."""
    assert _check(_note(candidates=[])).candidates == ()


def _candidate(**changes: Any) -> dict[str, Any]:
    candidate: dict[str, Any] = copy.deepcopy(_note()["candidates"][0])
    candidate.update(changes)
    return candidate


@pytest.mark.parametrize(
    "note",
    [
        "not an object",
        _note(contract_version=2),
        _note(model_version="other"),
        _note(image_id="22222222-2222-2222-2222-222222222222"),
        _note(status="maybe"),
        _note(status="failed", failure_reason="", candidates=[]),
        _note(status="failed", failure_reason="broken"),  # failed but has candidates
        _note(image_width_px=0),
        _note(image_height_px=True),
        _note(processing_ms=-1),
        _note(candidates="none"),
        _note(candidates=[_candidate(), _candidate()]),  # repeated index
        _note(candidates=[_candidate(detection_index=-1)]),
        _note(candidates=[_candidate(class_key="unicorn")]),
        _note(candidates=[_candidate(confidence=1.5)]),
        _note(candidates=[_candidate(confidence=True)]),
        _note(candidates=[_candidate(bbox_px=[1, 2, 3])]),
        _note(candidates=[_candidate(bbox_px=[1.0, 2, 3, 4])]),
        _note(candidates=[_candidate(bbox_px=[50, 20, 10, 120])]),  # right before left
        _note(candidates=[_candidate(bbox_px=[10, 20, 401, 120])]),  # outside the photo
    ],
)
def test_broken_notes_are_rejected(note: Any) -> None:
    with pytest.raises(InvalidModelOutputError):
        _check(note)


def test_a_failed_note_with_a_reason_is_valid() -> None:
    output = _check(_note(status="failed", failure_reason="Photo too dark", candidates=[]))

    assert output.status == "failed" and output.failure_reason == "Photo too dark"


def test_stand_in_gives_the_same_answer_for_the_same_photo(tmp_path: Path) -> None:
    for seed in range(1, 8):
        path = tmp_path / f"{seed}.jpg"
        path.write_bytes(make_photo(seed=seed))
        first = stand_in.detect(path, image_id=IMAGE_ID)
        second = stand_in.detect(path, image_id=IMAGE_ID)
        first.pop("processing_ms"), second.pop("processing_ms")

        assert first == second
        assert len(first["candidates"]) <= 2
        # Its notes always pass the checker.
        validate_output(
            {**first, "processing_ms": 1},
            expected_image_id=IMAGE_ID,
            expected_model_version=stand_in.MODEL_VERSION,
            allowed_classes=frozenset(stand_in.CLASSES),
        )


def test_registry() -> None:
    assert get_model(stand_in.MODEL_VERSION).is_stand_in
    assert is_stand_in(stand_in.MODEL_VERSION)
    assert not is_stand_in("unknown")
    with pytest.raises(UnknownModelError):
        get_model("unknown")
