"""P8.5: the final, one-time exam of a trained model on the locked test set (all Czech photos).

Runs on a Google Colab GPU after training has finished. Plan: documentation/04-design/ml-baseline-plan.md.

    python evaluate_test.py --data /content/prepared --model "/content/drive/MyDrive/GeoInfraLens/runs/frcnn-rdd2022-0.1/best.pt"

What it does:
- Checks the test photos are exactly the locked P8.2 test set, and that the model was trained on
  this same split (fingerprints in split-manifest.json and the run's config.json).
- Uses the confidence cut-off per class that was chosen on the VALIDATION photos during training
  (stored in best.pt). Nothing is tuned on the test photos.
- Scores every test photo once: per class AP50, and recall / precision / F1 at the cut-off.
- Compares the result with the pass marks in acceptance-thresholds.yaml: PASS, FAIL or NOT ENOUGH
  EVIDENCE (fewer test boxes than the minimum) per class.
- Reports, without affecting the pass mark: recall on dark and on blurry photos (same rules as the
  app's upload checks), false alarms on clean roads, and seconds per photo on a CPU.
- Writes test-report.json and a plain-language test-report.md next to the model.

The test set may be used only ONCE per model. Every use is written to test-usage.jsonl in the
runs folder; a model that already finished its exam is refused, so results can't be "retried".

The model only suggests candidates; this exam says how often its suggestions are right, never
anything about severity, size or repairs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from PIL import Image
from torchvision.models.detection import FasterRCNN
from torchvision.models.detection.backbone_utils import resnet_fpn_backbone
from torchvision.ops.misc import FrozenBatchNorm2d

try:  # inside the repository
    from evaluation.metrics import ClassMatches, Detection, Truth, at_cutoff, average_precision, match
except ImportError:  # on Colab, the scripts sit in the same folder
    from metrics import ClassMatches, Detection, Truth, at_cutoff, average_precision, match  # type: ignore[no-redef]

CLASS_NAMES = {1: "pothole", 2: "surface_cracking", 3: "pavement_deterioration"}
SCORE_FLOOR = 0.01  # same as validation, so AP50 sees the whole curve
# Same rules as the app's upload checks (backend/app/services/photo_metadata.py and core/config.py).
QUALITY_MAX_PX = 1024
BLUR_THRESHOLD = 100.0
DARKNESS_THRESHOLD = 40.0
MIN_GROUP_BOXES = 30  # a photo group with fewer real boxes is reported but not judged "weak"

PASS, FAIL, NOT_ENOUGH = "PASS", "FAIL", "NOT ENOUGH EVIDENCE"


# ---------------------------------------------------------------- checks


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_test_data(data_dir: Path, run_dir: Path) -> str:
    """The test annotations must be the locked P8.2 file, and the model must have been trained on that split."""
    manifest = json.loads((data_dir / "split-manifest.json").read_text())
    locked = manifest["splits"]["test"]["sha256_annotations"]
    actual = file_sha256(data_dir / "annotations" / "test.json")
    if actual != locked:
        raise SystemExit("STOPPED: annotations/test.json does not match split-manifest.json (damaged or changed copy).")
    config_path = run_dir / "config.json"
    if not config_path.exists():
        raise SystemExit(f"STOPPED: {config_path} is missing, so we can't prove which data this model was trained on.")
    trained_on = json.loads(config_path.read_text()).get("data", {})
    if trained_on.get("test_locked") != locked:
        raise SystemExit("STOPPED: this model was trained with a different split. Its test score would not be fair.")
    return actual


def load_thresholds(path: Path) -> dict[str, Any]:
    thresholds = yaml.safe_load(path.read_text())
    missing = set(CLASS_NAMES.values()) - set(thresholds.get("classes", {}))
    if missing:
        raise SystemExit(f"STOPPED: {path.name} has no pass marks for {sorted(missing)}.")
    return thresholds


# ---------------------------------------------------------------- model


def load_model(path: Path) -> tuple[torch.nn.Module, dict[str, Any]]:
    """Rebuild the trained model exactly as training made it, without downloading anything.

    Training started from COCO weights (pretrained=True), which also switches torchvision to "frozen"
    batch-norm layers with eps 0; quick tests train from scratch with normal batch-norm. Both are rebuilt here.
    """
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    categories = {int(key): value for key, value in checkpoint["categories"].items()}
    if categories != CLASS_NAMES:
        raise SystemExit(f"STOPPED: the model's classes {categories} are not the app's classes {CLASS_NAMES}.")
    config = checkpoint["config"]
    pretrained = bool(config["pretrained"])
    backbone = resnet_fpn_backbone(
        backbone_name="resnet50",
        weights=None,
        norm_layer=FrozenBatchNorm2d if pretrained else torch.nn.BatchNorm2d,
        trainable_layers=3 if pretrained else 5,
    )
    model = FasterRCNN(backbone, num_classes=len(CLASS_NAMES) + 1, min_size=config["min_size"], max_size=config["max_size"])
    if pretrained:  # torchvision does the same after loading the COCO_V1 weights
        for module in model.modules():
            if isinstance(module, FrozenBatchNorm2d):
                module.eps = 0.0
    model.load_state_dict(checkpoint["model"])
    model.eval()
    model.roi_heads.score_thresh = SCORE_FLOOR
    return model, checkpoint


def validation_cutoffs(checkpoint: dict[str, Any]) -> dict[str, float]:
    """The cut-offs chosen on validation during training (never on the test set)."""
    classes = checkpoint["validation"]["classes"]
    cutoffs = {}
    for name in CLASS_NAMES.values():
        cutoff = classes.get(name, {}).get("cutoff")
        if cutoff is None:
            raise SystemExit(f"STOPPED: best.pt has no validation cut-off for {name}.")
        cutoffs[name] = float(cutoff)
    return cutoffs


# ---------------------------------------------------------------- data


class TestPhotos(torch.utils.data.Dataset):
    """The locked test photos and their real boxes (read only here, in P8.5)."""

    def __init__(self, data_dir: Path, limit: int = 0) -> None:
        coco = json.loads((data_dir / "annotations" / "test.json").read_text())
        self.images_dir = data_dir / "images"
        self.images = coco["images"][:limit] if limit else coco["images"]
        boxes: dict[int, list[Truth]] = {image["id"]: [] for image in self.images}
        for annotation in coco["annotations"]:
            if annotation["image_id"] in boxes:
                x, y, w, h = annotation["bbox"]
                boxes[annotation["image_id"]].append(Truth(int(annotation["category_id"]), [x, y, x + w, y + h]))
        self.truths = [boxes[image["id"]] for image in self.images]

    def __len__(self) -> int:
        return len(self.images)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, list[str]]:
        with Image.open(self.images_dir / self.images[index]["file_name"]) as photo:
            rgb = photo.convert("RGB")
            flags = quality_flags(rgb)
            pixels = np.asarray(rgb, dtype=np.uint8)
        return torch.from_numpy(pixels.copy()).permute(2, 0, 1).float() / 255, flags


def quality_flags(image: Image.Image) -> list[str]:
    """Same rules as the app's upload checks: 'blurry' and 'too_dark'."""
    import cv2  # only needed here; Colab has it

    small = image.copy()
    small.thumbnail((QUALITY_MAX_PX, QUALITY_MAX_PX))
    gray = np.asarray(small.convert("L"), dtype=np.uint8)
    flags = []
    if float(cv2.Laplacian(gray, cv2.CV_64F).var()) < BLUR_THRESHOLD:
        flags.append("blurry")
    if float(gray.mean()) < DARKNESS_THRESHOLD:
        flags.append("too_dark")
    return flags


def _collate(batch: list[Any]) -> tuple[Any, ...]:
    return tuple(zip(*batch, strict=True))


@torch.no_grad()
def detect_all(
    model: torch.nn.Module, photos: TestPhotos, device: torch.device, batch_size: int
) -> tuple[list[list[Detection]], list[list[str]]]:
    model.to(device)
    loader = torch.utils.data.DataLoader(photos, batch_size=batch_size, collate_fn=_collate, num_workers=2)
    detections: list[list[Detection]] = []
    flags: list[list[str]] = []
    started = time.monotonic()
    for images, image_flags in loader:
        outputs = model([image.to(device) for image in images])
        for output in outputs:
            detections.append(
                [
                    Detection(int(c), float(s), b.tolist())
                    for b, c, s in zip(output["boxes"].cpu(), output["labels"].cpu(), output["scores"].cpu(), strict=True)
                ]
            )
        flags.extend(image_flags)
        if len(detections) % 500 < batch_size:
            print(f"   {len(detections)}/{len(photos)} photos ({time.monotonic() - started:.0f} s)", flush=True)
    return detections, flags


@torch.no_grad()
def cpu_seconds_per_photo(model: torch.nn.Module, photos: TestPhotos, count: int) -> dict[str, Any] | None:
    """Time single photos on the CPU, like the app server would run them (first photo is a warm-up)."""
    if count <= 0 or len(photos) == 0:
        return None
    model.to("cpu")
    seconds = []
    for index in range(min(count + 1, len(photos))):
        image, _ = photos[index]
        started = time.perf_counter()
        model([image])
        seconds.append(time.perf_counter() - started)
    timed = seconds[1:] or seconds
    return {"photos": len(timed), "median": statistics.median(timed), "max": max(timed), "cpu_threads": torch.get_num_threads()}


# ---------------------------------------------------------------- scoring


def score_classes(matches: dict[int, ClassMatches], cutoffs: dict[str, float]) -> dict[str, dict[str, Any]]:
    result = {}
    for class_id, name in CLASS_NAMES.items():
        found = matches.get(class_id, ClassMatches(np.zeros(0), np.zeros(0, dtype=bool), 0))
        ap50 = average_precision(found)
        values = at_cutoff(found, cutoffs[name])
        result[name] = {
            "ap50": None if math.isnan(ap50) else ap50,
            "cutoff": values.cutoff,
            "recall": values.recall,
            "precision": values.precision,
            "f1": values.f1,
            "found": values.found,
            "false_alarms": values.false_alarms,
            "real_boxes": values.real_boxes,
        }
    return result


def decide(classes: dict[str, dict[str, Any]], thresholds: dict[str, Any]) -> dict[str, Any]:
    """PASS / FAIL / NOT ENOUGH EVIDENCE per class, against the frozen pass marks."""
    verdicts = {}
    for name, scores in classes.items():
        marks = thresholds["classes"][name]
        if scores["real_boxes"] < marks["min_test_boxes"]:
            verdict = NOT_ENOUGH
        elif scores["recall"] >= marks["min_recall"] and scores["precision"] >= marks["min_precision"]:
            verdict = PASS
        else:
            verdict = FAIL
        verdicts[name] = {"verdict": verdict, **marks}
    passed = [name for name, value in verdicts.items() if value["verdict"] == PASS]
    overall = "ALL PASS" if len(passed) == len(verdicts) else ("PARTIAL PASS" if passed else "NOT PASSED")
    return {"overall": overall, "passed_classes": passed, "classes": verdicts}


def robustness(
    truths: list[list[Truth]],
    detections: list[list[Detection]],
    flags: list[list[str]],
    cutoffs: dict[str, float],
    overall: dict[str, dict[str, Any]],
    gap: float,
) -> dict[str, Any]:
    """Recall on dark and on blurry photos, and false alarms on clean roads. Reported only, not a pass mark."""
    groups: dict[str, Any] = {}
    for flag in ("too_dark", "blurry"):
        chosen = [i for i, photo_flags in enumerate(flags) if flag in photo_flags]
        matches = match([truths[i] for i in chosen], [detections[i] for i in chosen])
        per_class = {}
        for class_id, name in CLASS_NAMES.items():
            found = matches.get(class_id)
            real = found.real_boxes if found else 0
            recall = at_cutoff(found, cutoffs[name]).recall if found and real else None
            judged = recall is not None and real >= MIN_GROUP_BOXES
            weak = bool(judged and recall < overall[name]["recall"] - gap)
            per_class[name] = {"recall": recall, "real_boxes": real, "weak_condition": weak, "judged": judged}
        groups[flag] = {"photos": len(chosen), "classes": per_class}

    clean = [i for i, photo_truths in enumerate(truths) if not photo_truths]
    alarms = sum(1 for i in clean for d in detections[i] if d.score >= cutoffs[CLASS_NAMES[d.class_id]])
    groups["clean_roads"] = {"photos": len(clean), "false_alarms": alarms, "per_photo": alarms / len(clean) if clean else None}
    return groups


# ---------------------------------------------------------------- one-time use


def previous_uses(usage_log: Path) -> list[dict[str, Any]]:
    if not usage_log.exists():
        return []
    return [json.loads(line) for line in usage_log.read_text().splitlines() if line.strip()]


def record_use(usage_log: Path, entry: dict[str, Any]) -> None:
    usage_log.parent.mkdir(parents=True, exist_ok=True)
    with usage_log.open("a") as handle:
        handle.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------- report


def _pct(value: float | None) -> str:
    return "–" if value is None else f"{value * 100:.0f}%"


def _ap(value: float | None) -> str:
    return "–" if value is None else f"{value:.3f}"


def markdown_report(report: dict[str, Any]) -> str:
    decision = report["decision"]
    lines = [
        f"# Final test: {report['model_version']}",
        "",
        f"Tested on {report['test_photos']} photos from the locked test set (all Czech, never seen in training) "
        f"on {report['tested_at'][:10]}.",
        "",
        f"**Result: {decision['overall']}**"
        + (f" (passed: {', '.join(decision['passed_classes'])})" if decision["passed_classes"] else ""),
        "",
    ]
    if report["thresholds"]["is_placeholder"]:
        lines += ["> The pass marks are PLACEHOLDERS set by the owner. The partner has not confirmed them (PI-17).", ""]
    lines += [
        "| Damage type | Real boxes | Found | False alarms | Recall (need) | Precision (need) | AP50 | Result |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, scores in report["classes"].items():
        verdict = decision["classes"][name]
        lines.append(
            f"| {name} | {scores['real_boxes']} | {scores['found']} | {scores['false_alarms']} | "
            f"{_pct(scores['recall'])} ({_pct(verdict['min_recall'])}) | {_pct(scores['precision'])} ({_pct(verdict['min_precision'])}) | "
            f"{_ap(scores['ap50'])} | {verdict['verdict']} |"
        )
    lines += [
        "",
        "*Recall* = share of real damage the model found. *Precision* = share of the model's suggestions that were real damage. "
        "A suggestion counts only with the right type and at least 50% box overlap. Cut-offs were chosen on validation photos.",
        "",
        "## Difficult photos (reported only, not part of the pass mark)",
        "",
        "| Group | Photos | " + " | ".join(f"{name} recall" for name in CLASS_NAMES.values()) + " |",
        "|---|---|" + "---|" * len(CLASS_NAMES),
    ]
    for flag, label in (("too_dark", "Dark"), ("blurry", "Blurry")):
        group = report["robustness"][flag]
        cells = []
        for name in CLASS_NAMES.values():
            values = group["classes"][name]
            note = " WEAK" if values["weak_condition"] else ("" if values["judged"] else " (too few)")
            cells.append(f"{_pct(values['recall'])} of {values['real_boxes']}{note}")
        lines.append(f"| {label} | {group['photos']} | " + " | ".join(cells) + " |")
    clean = report["robustness"]["clean_roads"]
    lines += [
        "",
        f"WEAK = recall more than {report['thresholds']['weak_gap'] * 100:.0f} points below the overall recall for that type "
        f"(judged only with at least {MIN_GROUP_BOXES} real boxes).",
        "",
        f"Roads with no damage: {clean['photos']} photos, {clean['false_alarms']} false alarms"
        + (f" ({clean['per_photo']:.2f} per photo)." if clean["per_photo"] is not None else "."),
        "",
    ]
    cpu = report["cpu_timing"]
    if cpu:
        target = report["thresholds"]["cpu_target"]
        verdict = "within" if cpu["median"] <= target else "OVER"
        lines += [
            "## Speed on a CPU",
            "",
            f"Median {cpu['median']:.1f} s per photo (slowest {cpu['max']:.1f} s) over {cpu['photos']} photos with "
            f"{cpu['cpu_threads']} CPU threads: {verdict} the {target:.0f} s target. The app server's CPU may be faster or slower.",
            "",
        ]
    lines += [
        "## What this does and does not mean",
        "",
        "- The model's findings are **candidates** for a person to review; they are never confirmed damage.",
        "- The model's confidence is **not** severity. Nothing here measures size, depth or repair cost.",
        "- The test photos are Czech roads from RDD2022. Results on the client's own roads may differ "
        "until the model is checked on their photos (P8.3).",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- main


def evaluate(
    data_dir: Path,
    model_path: Path,
    thresholds_path: Path,
    out_dir: Path,
    usage_log: Path,
    device: torch.device,
    batch_size: int = 4,
    cpu_photos: int = 20,
    limit: int = 0,
) -> dict[str, Any]:
    run_dir = model_path.parent
    if not (run_dir / "training-done.json").exists():
        raise SystemExit("STOPPED: training has not finished (no training-done.json). The test set is used once, on the final model only.")
    test_sha = check_test_data(data_dir, run_dir)
    thresholds = load_thresholds(thresholds_path)
    model_sha = file_sha256(model_path)

    uses = previous_uses(usage_log)
    if any(use["model_sha256"] == model_sha and use["event"] == "finished" for use in uses):
        raise SystemExit(
            f"STOPPED: this model already took the final test. The test set is used once per model; see {out_dir / 'test-report.md'}."
        )
    others = sorted({use["model_version"] for use in uses if use["event"] == "finished" and use["model_sha256"] != model_sha})
    if others:
        print(f"Note: the test set was already used for {', '.join(others)}. Each model gets one try; compare models fairly.", flush=True)

    model, checkpoint = load_model(model_path)
    cutoffs = validation_cutoffs(checkpoint)
    base = {"model_version": checkpoint["model_version"], "model_sha256": model_sha, "test_sha256": test_sha}
    record_use(usage_log, {**base, "event": "started", "at": datetime.now(UTC).isoformat()})

    photos = TestPhotos(data_dir, limit)
    print(f"Testing {checkpoint['model_version']} on {len(photos)} locked test photos ({device})...", flush=True)
    detections, flags = detect_all(model, photos, device, batch_size)
    matches = match(photos.truths, detections)
    classes = score_classes(matches, cutoffs)
    gap = float(thresholds["report_only"]["weak_condition_recall_gap"])
    print(f"Timing {cpu_photos} photos on the CPU...", flush=True)
    report = {
        **base,
        "tested_at": datetime.now(UTC).isoformat(),
        "test_photos": len(photos),
        "best_epoch_validation_mean_ap50": checkpoint["validation"]["mean_ap50"],
        "cutoffs_from_validation": cutoffs,
        "score_floor": SCORE_FLOOR,
        "classes": classes,
        "decision": decide(classes, thresholds),
        "robustness": robustness(photos.truths, detections, flags, cutoffs, classes, gap),
        "cpu_timing": cpu_seconds_per_photo(model, photos, cpu_photos),
        "thresholds": {
            "file_sha256": file_sha256(thresholds_path),
            "is_placeholder": bool(thresholds.get("is_placeholder", True)),
            "weak_gap": gap,
            "cpu_target": float(thresholds["report_only"]["cpu_seconds_per_photo_target"]),
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "test-report.json").write_text(json.dumps(report, indent=2))
    (out_dir / "test-report.md").write_text(markdown_report(report))
    record_use(usage_log, {**base, "event": "finished", "at": report["tested_at"], "overall": report["decision"]["overall"]})
    return report


def summary(report: dict[str, Any]) -> str:
    rows = [f"Result: {report['decision']['overall']}", "", f"{'Damage type':<24}{'Recall':>8}{'Precision':>11}{'Boxes':>7}  Result"]
    for name, scores in report["classes"].items():
        verdict = report["decision"]["classes"][name]["verdict"]
        rows.append(f"{name:<24}{_pct(scores['recall']):>8}{_pct(scores['precision']):>11}{scores['real_boxes']:>7}  {verdict}")
    if report["thresholds"]["is_placeholder"]:
        rows += ["", "Pass marks are PLACEHOLDERS (partner has not confirmed PI-17)."]
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True, help="The prepared folder from P8.2")
    parser.add_argument("--model", type=Path, required=True, help="best.pt from the finished training run")
    parser.add_argument("--thresholds", type=Path, default=Path("acceptance-thresholds.yaml"))
    parser.add_argument("--out", type=Path, help="Where the reports go (default: next to the model)")
    parser.add_argument("--usage-log", type=Path, help="Record of every test use (default: test-usage.jsonl in the runs folder)")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--cpu-photos", type=int, default=20, help="Photos to time on the CPU (0 = skip)")
    parser.add_argument("--allow-cpu", action="store_true", help="Run the whole test on a CPU (several hours)")
    parser.add_argument("--limit", type=int, default=0, help=argparse.SUPPRESS)  # tests only
    args = parser.parse_args(argv)

    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif args.allow_cpu:
        device = torch.device("cpu")
    else:
        print("STOPPED: no GPU. In Colab: Runtime > Change runtime type > T4 GPU > Save, then run all cells again.", file=sys.stderr)
        return 1
    run_dir = args.model.parent
    report = evaluate(
        args.data,
        args.model,
        args.thresholds,
        args.out or run_dir,
        args.usage_log or run_dir.parent / "test-usage.jsonl",
        device,
        args.batch_size,
        args.cpu_photos,
        args.limit,
    )
    print("\n" + summary(report))
    print(f"\nFull report: {(args.out or run_dir) / 'test-report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
