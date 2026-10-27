"""The AI result format (model output contract, version 1) and its strict checker.

A detector hands back one "note" per photo. Before anything is saved, the note is checked
against every rule. One broken rule rejects the whole note, so no partial or invalid data
reaches the database (contract section 4). Extra fields (severity, size, location...) are
ignored on purpose: the AI never decides those.
"""

from dataclasses import dataclass
from typing import Any

CONTRACT_VERSION = 1


class InvalidModelOutputError(ValueError):
    """The detector's note broke the contract. The job fails; nothing is saved."""


@dataclass(frozen=True)
class Candidate:
    detection_index: int
    class_key: str
    confidence: float
    bbox_px: tuple[int, int, int, int]  # left, top, right, bottom (photo pixels)


@dataclass(frozen=True)
class ModelOutput:
    model_version: str
    image_id: str
    status: str  # "ok" or "failed"
    failure_reason: str | None
    image_width_px: int
    image_height_px: int
    candidates: tuple[Candidate, ...]
    processing_ms: int | None


def _require(condition: bool, problem: str) -> None:
    if not condition:
        raise InvalidModelOutputError(problem)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_output(
    note: Any,
    *,
    expected_image_id: str,
    expected_model_version: str,
    allowed_classes: frozenset[str],
) -> ModelOutput:
    """Check a detector's note against contract v1 and return it in a safe, typed form."""
    _require(isinstance(note, dict), "the result is not an object")
    _require(note.get("contract_version") == CONTRACT_VERSION, "unknown contract version")
    _require(note.get("model_version") == expected_model_version, "model version does not match")
    _require(str(note.get("image_id")) == expected_image_id, "photo does not match")
    status = note.get("status")
    _require(status in ("ok", "failed"), "status must be 'ok' or 'failed'")
    failure_reason = note.get("failure_reason")
    if status == "failed":
        _require(
            isinstance(failure_reason, str) and bool(failure_reason.strip()),
            "a failed result needs a reason",
        )
    width, height = note.get("image_width_px"), note.get("image_height_px")
    _require(_is_int(width) and _is_int(height) and width > 0 and height > 0, "bad photo size")
    processing_ms = note.get("processing_ms")
    _require(processing_ms is None or (_is_int(processing_ms) and processing_ms >= 0), "bad time")

    raw_candidates = note.get("candidates")
    _require(isinstance(raw_candidates, list), "candidates must be a list")
    if status == "failed":
        _require(len(raw_candidates) == 0, "a failed result cannot have candidates")

    candidates: list[Candidate] = []
    seen_indexes: set[int] = set()
    for raw in raw_candidates:
        _require(isinstance(raw, dict), "a candidate is not an object")
        index = raw.get("detection_index")
        _require(_is_int(index) and index >= 0, "bad detection_index")
        _require(index not in seen_indexes, "detection_index repeated")
        seen_indexes.add(index)
        class_key = raw.get("class_key")
        _require(class_key in allowed_classes, f"unknown class '{class_key}'")
        confidence = raw.get("confidence")
        _require(
            isinstance(confidence, int | float)
            and not isinstance(confidence, bool)
            and 0 <= confidence <= 1,
            "confidence must be between 0 and 1",
        )
        box = raw.get("bbox_px")
        _require(
            isinstance(box, list | tuple) and len(box) == 4 and all(_is_int(v) for v in box),
            "bbox_px must be 4 whole numbers",
        )
        left, top, right, bottom = box
        _require(0 <= left < right <= width and 0 <= top < bottom <= height, "box outside photo")
        candidates.append(
            Candidate(
                detection_index=index,
                class_key=class_key,
                confidence=float(confidence),
                bbox_px=(left, top, right, bottom),
            )
        )

    return ModelOutput(
        model_version=expected_model_version,
        image_id=expected_image_id,
        status=status,
        failure_reason=failure_reason.strip() if status == "failed" else None,
        image_width_px=width,
        image_height_px=height,
        candidates=tuple(sorted(candidates, key=lambda c: c.detection_index)),
        processing_ms=processing_ms,
    )
