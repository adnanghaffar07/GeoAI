"""The list of AI model versions the app knows (contract section 5).

A model version is never edited once used; a better model gets a new version name.
To add a real model later: write its `detect` function (same note format) and add an
entry here. Nothing else in the app changes.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from app.ai import frcnn, stand_in

# detect(photo_path, *, image_id) -> contract v1 note
Detector = Callable[..., dict[str, Any]]


# "test": the stand-in TEST DETECTOR (not real detections).
# "trial": a real model that has not passed its accuracy check; shown as TRIAL MODEL.
# "approved": passed the final test against the partner-confirmed pass marks (PI-17).
ModelStage = Literal["test", "trial", "approved"]


@dataclass(frozen=True)
class ModelSpec:
    model_version: str
    classes: frozenset[str]
    stage: ModelStage
    # Lowest confidence the model reports; chosen from validation results, never guessed.
    # (The trial model keeps its own per-class cut-offs inside its file.)
    reporting_threshold: float | None
    detect: Detector
    # Returns why the model cannot run right now (e.g. its file is missing), or None.
    problem: Callable[[], str | None] | None = None

    @property
    def is_stand_in(self) -> bool:
        return self.stage == "test"


MODELS: dict[str, ModelSpec] = {
    stand_in.MODEL_VERSION: ModelSpec(
        model_version=stand_in.MODEL_VERSION,
        classes=frozenset(stand_in.CLASSES),
        stage="test",
        reporting_threshold=None,
        detect=stand_in.detect,
    ),
    # Trial only (CR-003): failed the P8.5 final test; off unless ANALYSIS_MODEL_VERSION selects it.
    frcnn.MODEL_VERSION: ModelSpec(
        model_version=frcnn.MODEL_VERSION,
        classes=frozenset(frcnn.CLASSES),
        stage="trial",
        reporting_threshold=None,
        detect=frcnn.detect,
        problem=frcnn.problem,
    ),
}


class UnknownModelError(LookupError):
    pass


def get_model(model_version: str) -> ModelSpec:
    try:
        return MODELS[model_version]
    except KeyError as exc:
        raise UnknownModelError(f"Unknown AI model version '{model_version}'.") from exc


def is_stand_in(model_version: str) -> bool:
    spec = MODELS.get(model_version)
    return spec.is_stand_in if spec else False


def is_trial(model_version: str) -> bool:
    spec = MODELS.get(model_version)
    return spec.stage == "trial" if spec else False
