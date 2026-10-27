"""The trained road-damage model frcnn-rdd2022-0.1, run as a TRIAL model.

It was trained on the public RDD2022 photos (P8.4) and did NOT pass the final test on an
unseen country (P8.5, 2026-10-22: pothole recall 8%, surface cracking 17%, pavement
deterioration 34%). The owner chose to run it anyway as a labelled trial while it is being
improved (change request CR-003). So:

- It is off unless `ANALYSIS_MODEL_VERSION=frcnn-rdd2022-0.1` is set; the test detector stays
  the default, and switching back is the same one setting.
- Everything it suggests is shown as "TRIAL MODEL: accuracy not approved" and still needs a
  reviewer, like every AI suggestion.
- Only the exact file that took the final test is used (checked by its SHA-256 fingerprint).
- It reports only boxes above the per-class cut-offs chosen on the VALIDATION photos during
  training (stored in the file), never cut-offs tuned on the test set.

PyTorch is imported only when the first photo is analysed, so the API server never loads it.
The worker loads the model once and keeps it in memory (about 1-1.5 GB).
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image as PillowImage
from PIL import ImageOps

from app.core.config import get_settings

MODEL_VERSION = "frcnn-rdd2022-0.1"
MODEL_FILE_NAME = f"{MODEL_VERSION}.pt"
# Fingerprint of the best.pt that took the final test (ml/reports/test-report.json, 2026-10-22).
EXPECTED_SHA256 = "d18cedeffd726e90e1d69ddf29910f64b7e99c9c176a6109f4d644d0cfffc729"
CLASSES: tuple[str, ...] = ("pothole", "surface_cracking", "pavement_deterioration")
CLASS_IDS = {1: "pothole", 2: "surface_cracking", 3: "pavement_deterioration"}

PROBLEM_MISSING = (
    "The AI model file is missing on the server. An administrator must put "
    f"{MODEL_FILE_NAME} in the models folder, or switch back to the test detector."
)
PROBLEM_WRONG_FILE = (
    f"The AI model file {MODEL_FILE_NAME} on the server is not the tested model "
    "(its fingerprint does not match). An administrator must replace it with the tested file."
)
PROBLEM_UNREADABLE_MODEL = "The AI model file could not be opened. An administrator must check it."


class ModelUnavailableError(RuntimeError):
    """The model file is missing, wrong or damaged. The message is safe to show to users."""


@dataclass(frozen=True)
class _Loaded:
    model: Any
    cutoffs: dict[str, float]


_lock = threading.Lock()
_loaded: _Loaded | None = None


def model_path() -> Path:
    return get_settings().ai_models_dir / MODEL_FILE_NAME


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


_checked: tuple[str, int, int] | None = None  # (path, size, modified time) of a file that matched


def problem() -> str | None:
    """Why the model cannot run right now (None when it can).

    The fingerprint of a 165 MB file takes a moment, so a file that matched is not re-read
    until it is replaced (its size or modified time changes)."""
    global _checked
    if _loaded is not None:
        return None
    path = model_path()
    if not path.is_file():
        return PROBLEM_MISSING
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if _checked == key:
        return None
    if _sha256(path) != EXPECTED_SHA256:
        return PROBLEM_WRONG_FILE
    _checked = key
    return None


def _build(checkpoint: dict[str, Any], *, load_weights: bool = True) -> Any:
    """Rebuild the network exactly as training made it (same as ml/evaluation/evaluate_test.py).

    Training started from COCO weights, which makes torchvision use "frozen" batch-norm layers
    with eps 0; the file holds only the weights, so the layers are rebuilt the same way here.
    """
    import torch
    from torchvision.models.detection import FasterRCNN
    from torchvision.models.detection.backbone_utils import resnet_fpn_backbone
    from torchvision.ops.misc import FrozenBatchNorm2d

    config = checkpoint["config"]
    pretrained = bool(config["pretrained"])
    backbone = resnet_fpn_backbone(
        backbone_name="resnet50",
        weights=None,
        norm_layer=FrozenBatchNorm2d if pretrained else torch.nn.BatchNorm2d,
        trainable_layers=3 if pretrained else 5,
    )
    model = FasterRCNN(
        backbone,
        num_classes=len(CLASS_IDS) + 1,
        min_size=config["min_size"],
        max_size=config["max_size"],
    )
    if pretrained:
        for module in model.modules():
            if isinstance(module, FrozenBatchNorm2d):
                module.eps = 0.0
    if load_weights:
        model.load_state_dict(checkpoint["model"])
    model.eval()
    # Report nothing below the lowest class cut-off (each class is filtered again below).
    model.roi_heads.score_thresh = 0.0
    return model


def _load() -> _Loaded:
    global _loaded
    with _lock:
        if _loaded is not None:
            return _loaded
        found = problem()
        if found:
            raise ModelUnavailableError(found)
        import torch

        try:
            checkpoint = torch.load(model_path(), map_location="cpu", weights_only=True)
            categories = {int(key): value for key, value in checkpoint["categories"].items()}
            if categories != CLASS_IDS:
                raise ModelUnavailableError(PROBLEM_WRONG_FILE)
            classes = checkpoint["validation"]["classes"]
            cutoffs = {name: float(classes[name]["cutoff"]) for name in CLASSES}
            model = _build(checkpoint)
        except ModelUnavailableError:
            raise
        except Exception as exc:  # damaged file, wrong layout
            raise ModelUnavailableError(PROBLEM_UNREADABLE_MODEL) from exc
        model.roi_heads.score_thresh = min(cutoffs.values())
        _loaded = _Loaded(model=model, cutoffs=cutoffs)
        return _loaded


def detect(photo_path: Path, *, image_id: str) -> dict[str, Any]:
    """Return a contract v1 note for one photo (boxes in the upright photo's pixels)."""
    started = time.perf_counter()
    note: dict[str, Any] = {
        "contract_version": 1,
        "model_version": MODEL_VERSION,
        "image_id": image_id,
        "status": "ok",
        "failure_reason": None,
        "candidates": [],
    }
    with PillowImage.open(photo_path) as photo:
        # Screens draw boxes on the upright photo (phone photos often carry a "rotate" tag).
        upright = ImageOps.exif_transpose(photo).convert("RGB")
    width, height = upright.size
    note["image_width_px"], note["image_height_px"] = width, height
    try:
        loaded = _load()
    except ModelUnavailableError as exc:
        note.update(status="failed", failure_reason=str(exc))
        note["processing_ms"] = int((time.perf_counter() - started) * 1000)
        return note

    import numpy as np
    import torch

    pixels = torch.from_numpy(np.asarray(upright, dtype=np.uint8).copy())
    tensor = pixels.permute(2, 0, 1).float() / 255
    with torch.no_grad():
        output = loaded.model([tensor])[0]

    candidates: list[dict[str, Any]] = []
    for box, label, score in zip(
        output["boxes"].tolist(), output["labels"].tolist(), output["scores"].tolist(), strict=True
    ):
        class_key = CLASS_IDS.get(int(label))
        if class_key is None or score < loaded.cutoffs[class_key]:
            continue
        left = max(0, min(width - 1, int(box[0])))
        top = max(0, min(height - 1, int(box[1])))
        right = max(left + 1, min(width, round(box[2])))
        bottom = max(top + 1, min(height, round(box[3])))
        candidates.append(
            {
                "detection_index": len(candidates),
                "class_key": class_key,
                "confidence": round(float(score), 4),
                "bbox_px": [left, top, right, bottom],
            }
        )
    note["candidates"] = candidates
    note["processing_ms"] = int((time.perf_counter() - started) * 1000)
    return note
