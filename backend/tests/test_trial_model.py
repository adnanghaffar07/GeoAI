"""The trained model frcnn-rdd2022-0.1 running as a TRIAL model (CR-003).

The real file (165 MB) lives only on the owner's computer, so these tests build a model file
with the same layout (random weights, small images) and accept its fingerprint in place of
the tested file's.
"""

import hashlib
import io
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.ai import frcnn, registry
from app.core.config import get_settings
from tests.analysis_fixtures import Setup

torch = pytest.importorskip("torch")


def _write_model(path: Path, cutoffs: dict[str, float]) -> str:
    """A file laid out like training's best.pt: COCO-style frozen batch-norm, our 3 classes."""
    checkpoint = {
        "model": {},
        "model_version": frcnn.MODEL_VERSION,
        "categories": {1: "pothole", 2: "surface_cracking", 3: "pavement_deterioration"},
        "config": {"pretrained": True, "min_size": 128, "max_size": 128},
        "validation": {
            "epoch": 10,
            "classes": {name: {"cutoff": value} for name, value in cutoffs.items()},
        },
    }
    torch.manual_seed(0)
    checkpoint["model"] = frcnn._build(
        {**checkpoint, "model": None}, load_weights=False
    ).state_dict()
    torch.save(checkpoint, path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def trial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Path]:
    """Switch the app to the trial model, with a models folder in tmp_path."""
    monkeypatch.setattr(get_settings(), "ai_models_dir", tmp_path)
    monkeypatch.setattr(get_settings(), "analysis_model_version", frcnn.MODEL_VERSION)
    monkeypatch.setattr(frcnn, "_loaded", None)
    monkeypatch.setattr(frcnn, "_checked", None)

    def put_file(cutoffs: dict[str, float] | None = None, *, accept: bool = True) -> Path:
        path = tmp_path / frcnn.MODEL_FILE_NAME
        sha = _write_model(path, cutoffs or dict.fromkeys(frcnn.CLASSES, 0.0))
        if accept:
            monkeypatch.setattr(frcnn, "EXPECTED_SHA256", sha)
        return path

    return put_file


def test_the_test_detector_stays_the_default() -> None:
    assert get_settings().analysis_model_version == "stand-in-0.1"
    assert registry.get_model(frcnn.MODEL_VERSION).stage == "trial"
    assert registry.is_trial(frcnn.MODEL_VERSION) and not registry.is_stand_in(frcnn.MODEL_VERSION)
    assert not registry.is_trial("stand-in-0.1")


def test_missing_model_file_is_explained_when_analysis_starts(
    s: Setup, worker: list[str], trial: Any
) -> None:
    s.upload(s.admin)
    response = s.start(s.admin)
    assert response.status_code == 503
    assert "model file is missing" in response.json()["error"]["message"]
    assert worker == []  # nothing was queued


def test_a_file_that_is_not_the_tested_model_is_refused(
    s: Setup, worker: list[str], trial: Any
) -> None:
    trial(accept=False)  # a model file, but not the one that took the final test
    s.upload(s.admin)
    response = s.start(s.admin)
    assert response.status_code == 503
    assert "not the tested model" in response.json()["error"]["message"]


def test_trial_model_analyses_photos_and_its_results_are_labelled(
    s: Setup, worker: list[str], trial: Any
) -> None:
    trial()
    image_id = s.upload(s.admin)

    response = s.start(s.admin)

    assert response.status_code == 202, response.text
    job = s.admin.get(f"/api/v1/analysis-jobs/{worker[0]}").json()
    assert job["status"] == "completed", job
    assert job["is_trial_model"] is True and job["is_test_detector"] is False
    image = s.admin.get(f"/api/v1/images/{image_id}").json()
    assert image["analysis"]["is_trial_model"] is True
    findings = s.findings(s.admin).json()["items"]
    assert findings  # random weights with cut-offs of 0 still produce boxes: the whole path ran
    for finding in findings:  # every box passed the contract checks
        assert finding["model_version"] == frcnn.MODEL_VERSION
        assert finding["is_trial_model"] is True and finding["review_status"] == "ai_generated"
        left, top, right, bottom = finding["predicted_bbox"]
        assert 0 <= left < right <= 400 and 0 <= top < bottom <= 300


class _FakeModel:
    def __init__(self, boxes: list[list[float]], labels: list[int], scores: list[float]) -> None:
        self.output = {
            "boxes": torch.tensor(boxes),
            "labels": torch.tensor(labels),
            "scores": torch.tensor(scores),
        }
        self.seen: list[tuple[int, int]] = []

    def __call__(self, images: list[Any]) -> list[dict[str, Any]]:
        self.seen.append(tuple(images[0].shape[1:]))
        return [self.output]


def _photo(path: Path, size: tuple[int, int], orientation: int | None = None) -> Path:
    image = Image.new("RGB", size, (120, 120, 120))
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif.tobytes())
    path.write_bytes(buffer.getvalue())
    return path


def test_keeps_only_boxes_above_each_class_cutoff_and_inside_the_photo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModel(
        boxes=[[10.4, 20.6, 50.2, 60.9], [0, 0, 5, 5], [-3, 250, 500, 320], [30, 30, 40, 40]],
        labels=[1, 1, 2, 3],
        scores=[0.9, 0.5, 0.85, 0.79],
    )
    cutoffs = {"pothole": 0.78, "surface_cracking": 0.8, "pavement_deterioration": 0.8}
    monkeypatch.setattr(frcnn, "_loaded", frcnn._Loaded(model=fake, cutoffs=cutoffs))

    note = frcnn.detect(_photo(tmp_path / "p.jpg", (400, 300)), image_id="x")

    assert note["status"] == "ok" and note["model_version"] == frcnn.MODEL_VERSION
    assert [(c["class_key"], c["bbox_px"]) for c in note["candidates"]] == [
        (
            "pothole",
            [10, 20, 50, 61],
        ),  # 0.5 pothole and 0.79 deterioration are below their cut-offs
        ("surface_cracking", [0, 250, 400, 300]),  # clipped to the photo
    ]
    assert [c["detection_index"] for c in note["candidates"]] == [0, 1]


def test_rotated_phone_photos_are_analysed_upright(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModel(boxes=[], labels=[], scores=[])
    monkeypatch.setattr(
        frcnn, "_loaded", frcnn._Loaded(model=fake, cutoffs=dict.fromkeys(frcnn.CLASSES, 0.5))
    )

    note = frcnn.detect(
        _photo(tmp_path / "p.jpg", (400, 300), orientation=6), image_id="x"
    )  # "rotate 90°"

    assert (note["image_width_px"], note["image_height_px"]) == (300, 400)  # what the screens show
    assert fake.seen == [(400, 300)]  # the model saw the upright photo (height 400, width 300)
