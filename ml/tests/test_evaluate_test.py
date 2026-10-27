"""P8.5 final exam, tested on a tiny fake dataset and a tiny model trained on the CPU."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import torch
import torchvision
from PIL import Image
from torchvision.models.detection import FasterRCNN
from torchvision.models.detection.backbone_utils import resnet_fpn_backbone
from torchvision.ops.misc import FrozenBatchNorm2d

from evaluation import evaluate_test as exam
from evaluation.metrics import Detection, Truth
from tests.test_train_frcnn import make_prepared
from training import train_frcnn as train

THRESHOLDS = Path(__file__).resolve().parent.parent / "config" / "acceptance-thresholds.yaml"


@pytest.fixture(scope="module")
def trained(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """A prepared folder and a finished 1-epoch quick-test run."""
    root = tmp_path_factory.mktemp("exam")
    data = make_prepared(root)
    run = root / "runs" / "model-x"
    assert (
        train.main(["--data", str(data), "--run-dir", str(run), "--allow-cpu", "--quick-test", "--batch-size", "2", "--epochs", "1"]) == 0
    )
    return data, run


def copy_run(trained: tuple[Path, Path], tmp_path: Path) -> tuple[Path, Path]:
    data, run = trained
    new_run = tmp_path / "runs" / run.name
    shutil.copytree(run, new_run)
    return data, new_run


def run_exam(data: Path, run: Path) -> int:
    return exam.main(
        ["--data", str(data), "--model", str(run / "best.pt"), "--thresholds", str(THRESHOLDS), "--allow-cpu", "--cpu-photos", "1"]
    )


def test_takes_the_exam_once_and_writes_the_reports(trained: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data, run = copy_run(trained, tmp_path)
    assert run_exam(data, run) == 0
    output = capsys.readouterr().out
    assert "Result:" in output and "PLACEHOLDERS" in output

    report = json.loads((run / "test-report.json").read_text())
    assert report["model_version"] == train.MODEL_VERSION
    assert report["test_photos"] == 2
    assert set(report["classes"]) == set(exam.CLASS_NAMES.values())
    # Cut-offs come from validation (stored in best.pt), never from the test photos.
    best = torch.load(run / "best.pt", weights_only=True)
    assert report["cutoffs_from_validation"] == {name: best["validation"]["classes"][name]["cutoff"] for name in exam.CLASS_NAMES.values()}
    # The fake test set has only 1 box per class: far below the 100 needed for a verdict.
    assert {value["verdict"] for value in report["decision"]["classes"].values()} == {exam.NOT_ENOUGH}
    assert report["decision"]["overall"] == "NOT PASSED"
    assert report["cpu_timing"]["photos"] == 1
    markdown = (run / "test-report.md").read_text()
    assert "PLACEHOLDERS" in markdown and "candidates" in markdown and "not** severity" in markdown

    uses = [json.loads(line) for line in (run.parent / "test-usage.jsonl").read_text().splitlines()]
    assert [use["event"] for use in uses] == ["started", "finished"]

    with pytest.raises(SystemExit, match="already took the final test"):
        run_exam(data, run)


def test_a_crashed_exam_can_be_run_again(trained: tuple[Path, Path], tmp_path: Path) -> None:
    data, run = copy_run(trained, tmp_path)
    exam.record_use(
        run.parent / "test-usage.jsonl", {"model_sha256": exam.file_sha256(run / "best.pt"), "model_version": "x", "event": "started"}
    )
    assert run_exam(data, run) == 0  # no result was ever produced, so this is still the first real use


def test_refuses_before_training_has_finished(trained: tuple[Path, Path], tmp_path: Path) -> None:
    data, run = copy_run(trained, tmp_path)
    (run / "training-done.json").unlink()
    with pytest.raises(SystemExit, match="training has not finished"):
        run_exam(data, run)


def test_refuses_a_changed_test_set(trained: tuple[Path, Path], tmp_path: Path) -> None:
    _, run = copy_run(trained, tmp_path)
    data = make_prepared(tmp_path / "other")
    (data / "annotations" / "test.json").write_text("{}")
    with pytest.raises(SystemExit, match="does not match split-manifest"):
        run_exam(data, run)


def test_refuses_a_model_trained_on_another_split(trained: tuple[Path, Path], tmp_path: Path) -> None:
    data, run = copy_run(trained, tmp_path)
    config = json.loads((run / "config.json").read_text())
    config["data"]["test_locked"] = "0" * 64
    (run / "config.json").write_text(json.dumps(config))
    with pytest.raises(SystemExit, match="different split"):
        run_exam(data, run)


def test_stops_without_a_gpu_unless_allowed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    if torch.cuda.is_available():
        pytest.skip("machine has a GPU")
    assert exam.main(["--data", str(tmp_path), "--model", str(tmp_path / "best.pt")]) == 1
    assert "Change runtime type" in capsys.readouterr().err


def test_rebuilds_a_coco_started_model_exactly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The real model starts from COCO weights (frozen batch-norm, eps 0). Rebuild it without downloading them."""
    torch.manual_seed(0)
    coco_like = FasterRCNN(resnet_fpn_backbone(backbone_name="resnet50", weights=None, norm_layer=FrozenBatchNorm2d), num_classes=91)
    for name, buffer in coco_like.named_buffers():  # non-trivial batch-norm statistics, so eps matters
        if name.endswith("running_var"):
            buffer.uniform_(0.5, 2.0)
    monkeypatch.setattr(torchvision.models._api.WeightsEnum, "get_state_dict", lambda self, **_: coco_like.state_dict())

    config = train.Config(min_size=96, max_size=96)
    trained_model = train.build_model(config).eval()
    path = tmp_path / "best.pt"
    torch.save(
        {
            "model": trained_model.state_dict(),
            "model_version": config.model_version,
            "categories": train.CLASS_NAMES,
            "config": train.asdict(config),
            "validation": {},
        },
        path,
    )
    rebuilt, _ = exam.load_model(path)  # load_state_dict is strict: any structural difference fails here
    trained_model.roi_heads.score_thresh = exam.SCORE_FLOOR
    image = torch.rand(3, 96, 96)
    with torch.no_grad():
        features_trained = trained_model.backbone(image[None])
        features_rebuilt = rebuilt.backbone(image[None])
    for key in features_trained:
        assert torch.equal(features_trained[key], features_rebuilt[key])


def test_refuses_a_model_with_other_classes(trained: tuple[Path, Path], tmp_path: Path) -> None:
    _, run = trained
    checkpoint = torch.load(run / "best.pt", weights_only=True)
    checkpoint["categories"] = {1: "pothole"}
    torch.save(checkpoint, tmp_path / "best.pt")
    with pytest.raises(SystemExit, match="not the app's classes"):
        exam.load_model(tmp_path / "best.pt")


def scores(recall: float, precision: float, boxes: int) -> dict[str, float]:
    return {"recall": recall, "precision": precision, "real_boxes": boxes}


def test_pass_fail_and_not_enough_evidence() -> None:
    thresholds = exam.load_thresholds(THRESHOLDS)
    result = exam.decide(
        {
            "pothole": scores(0.70, 0.50, 100),  # exactly on the marks: pass
            "surface_cracking": scores(0.59, 0.90, 500),  # recall too low
            "pavement_deterioration": scores(0.95, 0.95, 99),  # great, but too few boxes to trust
        },
        thresholds,
    )
    assert {name: value["verdict"] for name, value in result["classes"].items()} == {
        "pothole": exam.PASS,
        "surface_cracking": exam.FAIL,
        "pavement_deterioration": exam.NOT_ENOUGH,
    }
    assert result["overall"] == "PARTIAL PASS" and result["passed_classes"] == ["pothole"]


def test_dark_photos_are_flagged_as_a_weak_condition() -> None:
    box = [0, 0, 10, 10]
    # 40 bright photos where the pothole is found, 40 dark photos where it is missed; one clean road with a false alarm.
    truths = [[Truth(1, box)] for _ in range(80)] + [[]]
    detections = (
        [[Detection(1, 0.9, box)] for _ in range(40)] + [[] for _ in range(40)] + [[Detection(2, 0.8, box), Detection(1, 0.1, box)]]
    )
    flags = [[] for _ in range(40)] + [["too_dark"] for _ in range(40)] + [[]]
    cutoffs = {"pothole": 0.5, "surface_cracking": 0.5, "pavement_deterioration": 0.5}
    overall = {name: {"recall": 0.5} for name in cutoffs}
    result = exam.robustness(truths, detections, flags, cutoffs, overall, gap=0.15)
    dark = result["too_dark"]["classes"]["pothole"]
    assert (dark["recall"], dark["real_boxes"], dark["weak_condition"]) == (0.0, 40, True)
    assert result["blurry"]["photos"] == 0 and result["blurry"]["classes"]["pothole"]["judged"] is False
    assert result["clean_roads"] == {"photos": 1, "false_alarms": 1, "per_photo": 1.0}  # the 0.1 detection is below its cut-off


def test_quality_flags_follow_the_app_rules() -> None:
    noise = np.random.default_rng(0).integers(0, 256, (200, 200, 3), dtype=np.uint8)
    assert exam.quality_flags(Image.fromarray(noise)) == []
    assert exam.quality_flags(Image.new("RGB", (200, 200), (128, 128, 128))) == ["blurry"]
    assert exam.quality_flags(Image.new("RGB", (200, 200), (10, 10, 10))) == ["blurry", "too_dark"]
