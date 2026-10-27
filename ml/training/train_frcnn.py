"""P8.4: train the baseline road-damage model (Faster R-CNN, ResNet-50 FPN) on the P8.2 split.

Runs on a Google Colab GPU. Plan: documentation/04-design/ml-baseline-plan.md.

    python train_frcnn.py --data /content/prepared --run-dir "/content/drive/MyDrive/GeoInfraLens/runs/frcnn-rdd2022-0.1"

What it does:
- Starts from a model already trained on everyday photos (COCO), so it only has to learn road damage.
- Learns the app's 3 classes (pothole, surface cracking, pavement deterioration).
- Uses training photos only. After each round ("epoch") it checks itself on the VALIDATION photos
  and keeps the best round as best.pt. It never opens the locked test set (that is P8.5).
- Saves progress to Google Drive about every 20 minutes (checkpoint-eEE-bBBBBB.pt, a new file each
  time). If Colab disconnects, run the same command again: it continues from the newest save that
  Google Drive actually kept. Older saves are deleted only after a newer one has opened in a later
  session. If every save was lost, it continues after the epoch stored in best.pt; it never starts
  again from epoch 1 over existing results.
- Writes a log (log.jsonl) and validation scores (val-history.json) next to the checkpoints.

The model only suggests candidates; it never decides severity, size or repairs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pickle
import random
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image
from torchvision.models.detection import FasterRCNN_ResNet50_FPN_Weights, fasterrcnn_resnet50_fpn
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor

try:  # inside the repository
    from evaluation.metrics import Detection, Truth, average_precision, best_f1_cutoff, match
except ImportError:  # on Colab, the scripts sit in the same folder
    from metrics import Detection, Truth, average_precision, best_f1_cutoff, match  # type: ignore[no-redef]

MODEL_VERSION = "frcnn-rdd2022-0.1"
# Same order as split_rdd2022.CATEGORIES; 0 is "background" inside the model.
CLASS_NAMES = {1: "pothole", 2: "surface_cracking", 3: "pavement_deterioration"}


@dataclass
class Config:
    model_version: str = MODEL_VERSION
    epochs: int = 12
    batch_size: int = 4
    learning_rate: float = 0.01
    momentum: float = 0.9
    weight_decay: float = 1e-4
    warmup_steps: int = 500
    lr_drop_epochs: tuple[int, ...] = (8, 11)  # learning rate x0.1 after these epochs (a standard "1x" schedule)
    empty_fraction: float = 0.25  # share of "no damage" photos used per epoch (they are 44% of training)
    hflip: float = 0.5
    min_size: int = 800
    max_size: int = 1333
    pretrained: bool = True
    seed: int = 2026
    checkpoint_every: int = 2000  # batches (about every 20 minutes on a T4 GPU; fewer saves use less Drive space)
    log_every: int = 50  # batches
    val_score_floor: float = 0.01  # keep low-confidence detections when validating, to see the whole curve
    max_train_images: int = 0  # 0 = all (small values only for quick tests)
    max_val_images: int = 0


# ---------------------------------------------------------------- data


class CocoDetection(torch.utils.data.Dataset):
    """Photos and boxes from a COCO file made by split_rdd2022.py."""

    def __init__(self, data_dir: Path, split: str, limit: int = 0) -> None:
        if split not in {"train", "val"}:
            raise ValueError("Training only ever reads the train and val sets; the test set is locked for P8.5.")
        coco = json.loads((data_dir / "annotations" / f"{split}.json").read_text())
        self.images_dir = data_dir / "images"
        self.images = coco["images"][:limit] if limit else coco["images"]
        boxes: dict[int, list[tuple[list[float], int]]] = {image["id"]: [] for image in self.images}
        for annotation in coco["annotations"]:
            if annotation["image_id"] in boxes:
                x, y, w, h = annotation["bbox"]
                boxes[annotation["image_id"]].append(([x, y, x + w, y + h], annotation["category_id"]))
        self.boxes = [boxes[image["id"]] for image in self.images]
        self.flip_seed: dict[int, int] = {}
        self.flip_probability = 0.5

    def __len__(self) -> int:
        return len(self.images)

    def has_damage(self, index: int) -> bool:
        return bool(self.boxes[index])

    def __getitem__(self, index: int) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        with Image.open(self.images_dir / self.images[index]["file_name"]) as photo:
            pixels = np.asarray(photo.convert("RGB"), dtype=np.uint8)
        image = torch.from_numpy(pixels.copy()).permute(2, 0, 1).float() / 255
        items = self.boxes[index]
        boxes = torch.tensor([box for box, _ in items], dtype=torch.float32).reshape(-1, 4)
        labels = torch.tensor([label for _, label in items], dtype=torch.int64)
        flip_seed = self.flip_seed.get(index)
        if flip_seed is not None and random.Random(flip_seed).random() < self.flip_probability:  # noqa: S311 (augmentation, not security)
            image = image.flip(-1)
            width = image.shape[-1]
            boxes = torch.stack([width - boxes[:, 2], boxes[:, 1], width - boxes[:, 0], boxes[:, 3]], dim=1) if len(boxes) else boxes
        return image, {"boxes": boxes, "labels": labels, "image_id": torch.tensor(index)}


def collate(batch: list[Any]) -> tuple[Any, ...]:
    return tuple(zip(*batch, strict=True))


def epoch_order(dataset: CocoDetection, epoch: int, config: Config) -> list[int]:
    """Which photos are used in this epoch, in which order (same every time for the same epoch)."""
    rng = random.Random(config.seed * 1000 + epoch)  # noqa: S311 (repeatable order, not security)
    with_damage = [i for i in range(len(dataset)) if dataset.has_damage(i)]
    empty = [i for i in range(len(dataset)) if not dataset.has_damage(i)]
    chosen = with_damage + rng.sample(empty, round(len(empty) * config.empty_fraction))
    rng.shuffle(chosen)
    return chosen


def learning_rate(step: int, epoch: int, config: Config) -> float:
    rate = config.learning_rate * (0.1 ** sum(1 for drop in config.lr_drop_epochs if epoch > drop))
    if step < config.warmup_steps:
        rate *= 0.001 + (1 - 0.001) * step / config.warmup_steps
    return rate


# ---------------------------------------------------------------- model


def build_model(config: Config) -> torch.nn.Module:
    weights = FasterRCNN_ResNet50_FPN_Weights.DEFAULT if config.pretrained else None
    model = fasterrcnn_resnet50_fpn(
        weights=weights,
        weights_backbone=None,
        num_classes=None if weights else len(CLASS_NAMES) + 1,
        min_size=config.min_size,
        max_size=config.max_size,
    )
    if weights:  # replace the 91 everyday-object classes with background + our 3
        in_features = model.roi_heads.box_predictor.cls_score.in_features
        model.roi_heads.box_predictor = FastRCNNPredictor(in_features, len(CLASS_NAMES) + 1)
    return model


# ---------------------------------------------------------------- validation


@torch.no_grad()
def validate(model: torch.nn.Module, dataset: CocoDetection, device: torch.device, config: Config) -> dict[str, Any]:
    model.eval()
    model.roi_heads.score_thresh = config.val_score_floor
    loader = torch.utils.data.DataLoader(dataset, batch_size=config.batch_size, collate_fn=collate, num_workers=2)
    truths, detections = [], []
    for images, targets in loader:
        outputs = model([image.to(device) for image in images])
        for target, output in zip(targets, outputs, strict=True):
            truths.append([Truth(int(c), b.tolist()) for b, c in zip(target["boxes"], target["labels"], strict=True)])
            detections.append(
                [
                    Detection(int(c), float(s), b.tolist())
                    for b, c, s in zip(output["boxes"].cpu(), output["labels"].cpu(), output["scores"].cpu(), strict=True)
                ]
            )
    matches = match(truths, detections)
    per_class = {}
    for class_id, name in CLASS_NAMES.items():
        if class_id not in matches:
            per_class[name] = {"ap50": 0.0, "real_boxes": 0}
            continue
        best = best_f1_cutoff(matches[class_id])
        per_class[name] = {"ap50": average_precision(matches[class_id]), **asdict(best)}
    aps = [values["ap50"] for values in per_class.values() if not math.isnan(values["ap50"])]
    model.train()
    return {"mean_ap50": float(np.mean(aps)) if aps else 0.0, "classes": per_class, "photos": len(dataset)}


# ---------------------------------------------------------------- checkpoints


MIN_FREE_GB = 1.0  # room for the next save (about 0.33 GB) and a new best.pt (0.17 GB), with margin


def drive_free_gb(path: Path) -> float:
    """Free space where the run is saved. On Colab this is Google Drive's own free space (deleted files
    in Drive's Trash still count against it)."""
    return shutil.disk_usage(path).free / 1e9


def check_space(run_dir: Path) -> None:
    """A full Google Drive silently drops new files while Colab carries on (this lost every save on
    2026-10-19), so stop with a clear message instead of training into saves that will never arrive."""
    free = drive_free_gb(run_dir)
    if free < MIN_FREE_GB:
        raise SystemExit(
            f"STOPPED: Google Drive has only {free:.1f} GB free (needs at least {MIN_FREE_GB:.0f} GB), so saves would be lost. "
            "On drive.google.com open Trash and delete old checkpoint-*.pt files forever (files in Trash still use space), "
            "then run the notebook again. Training continues from the last save."
        )


# How often progress is saved or logged does not change the model, so these may change during a run.
BOOKKEEPING_SETTINGS = ("checkpoint_every", "log_every")


def settings_that_differ(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Names of the settings, data fingerprints or classes that differ from the run's stored config.json."""
    changed = []
    for section in sorted(set(previous) | set(current)):
        old, new = previous.get(section), current.get(section)
        if section == "config" and isinstance(old, dict) and isinstance(new, dict):
            for key in sorted(set(old) | set(new)):
                if key not in BOOKKEEPING_SETTINGS and old.get(key) != new.get(key):
                    changed.append(key)
        elif old != new:
            changed.append(section)
    return changed


def save_atomically(payload: dict[str, Any], path: Path) -> None:
    """Write to a temporary file, then rename, so a disconnect never leaves a half-written checkpoint."""
    temporary = path.with_suffix(".tmp")
    torch.save(payload, temporary)
    os.replace(temporary, path)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_data(data_dir: Path) -> dict[str, str]:
    """The prepared copy must match the locked split from P8.2 (fingerprints in split-manifest.json)."""
    manifest = json.loads((data_dir / "split-manifest.json").read_text())
    fingerprints = {}
    for split in ("train", "val"):
        actual = file_sha256(data_dir / "annotations" / f"{split}.json")
        if actual != manifest["splits"][split]["sha256_annotations"]:
            raise SystemExit(f"STOPPED: annotations/{split}.json does not match split-manifest.json (damaged or changed copy).")
        fingerprints[split] = actual
    fingerprints["test_locked"] = manifest["splits"]["test"]["sha256_annotations"]
    return fingerprints


SESSION_SAVES_KEPT = 2


def checkpoint_name(state: dict[str, Any]) -> str:
    """Zero-padded, so sorting the names sorts the saves from oldest to newest."""
    return f"checkpoint-e{state['epoch']:02d}-b{state['batches_done']:06d}.pt"


def load_newest_checkpoint(run_dir: Path, device: torch.device) -> tuple[Path, dict[str, Any]] | None:
    """The newest save that opens, and its file. Each save is a new file (never renamed over an old one),
    because on Google Drive a save that was cut off or not yet uploaded must leave the previous save usable.
    last.pt is the older single-file format, used only when no newer saves exist."""
    candidates = sorted(run_dir.glob("checkpoint-e*-b*.pt"), reverse=True) or [run_dir / "last.pt"]
    candidates = [path for path in candidates if path.exists()]
    for path in candidates:
        try:
            checkpoint = torch.load(path, map_location=device, weights_only=False)
        except (OSError, RuntimeError, EOFError, ValueError, pickle.UnpicklingError) as error:  # cut off half-way
            print(f"Skipping a damaged save {path.name} ({error}); trying the one before it.", flush=True)
            continue
        print(f"Continuing from {path.name}: epoch {checkpoint['state']['epoch']}, batch {checkpoint['state']['batches_done']}", flush=True)
        return path, checkpoint
    if candidates:  # never start again from zero over a run that has saves
        raise SystemExit(f"STOPPED: none of the saves in {run_dir} can be opened. Tell Claude; do not delete anything.")
    return None


def remove_saves_before(run_dir: Path, loaded: Path) -> None:
    """At the start of a session, after `loaded` opened: older saves are no longer needed.

    Only saves that survived into a new session are trusted. Google Drive can drop the newest files
    when Colab stops suddenly while still applying deletions, so nothing is deleted on the strength of
    a save that may never reach Drive (that lost every save once, on 2026-10-19)."""
    for old in sorted(run_dir.glob("checkpoint-e*-b*.pt")):
        if old.name < loaded.name:
            old.unlink(missing_ok=True)
    if loaded.name != "last.pt":
        (run_dir / "last.pt").unlink(missing_ok=True)


def remove_session_saves(made_this_session: list[Path]) -> None:
    """During a session, keep only the newest few saves made in this session (Drive space).
    Saves from before the session are never touched here, so the worst case is losing one session."""
    for old in made_this_session[:-SESSION_SAVES_KEPT]:
        old.unlink(missing_ok=True)
    del made_this_session[:-SESSION_SAVES_KEPT]


def batches_in_epoch(train_set: Any, epoch: int, config: Config) -> int:
    return math.ceil(len(epoch_order(train_set, epoch, config)) / config.batch_size)


def read_history(path: Path) -> list[dict[str, Any]]:
    """Every validation score, in order. An epoch appears twice if it had to be trained again
    (when Google Drive lost a save); both scores are kept as a true record."""
    return json.loads(path.read_text()) if path.exists() else []


def log(run_dir: Path, entry: dict[str, Any]) -> None:
    with (run_dir / "log.jsonl").open("a") as handle:
        handle.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------- training


def progress_report(run_dir: Path, total_epochs: int) -> str:
    """A short, plain summary of how far training has got (works at any time, even between sessions)."""
    history = read_history(run_dir / "val-history.json")
    if not history:
        return "No epoch finished yet."
    lines = [
        f"Finished {len({entry['epoch'] for entry in history})} of {total_epochs} epochs.",
        "",
        "Epoch  Mean AP50  Pothole  Surface cracking  Pavement deterioration",
    ]
    seen = set()
    for entry in history:
        classes = entry["classes"]
        lines.append(
            f"{entry['epoch']:>5}  {entry['mean_ap50']:>9.3f}  {classes['pothole']['ap50']:>7.3f}"
            f"  {classes['surface_cracking']['ap50']:>16.3f}  {classes['pavement_deterioration']['ap50']:>22.3f}"
            + ("  (trained again)" if entry["epoch"] in seen else "")
        )
        seen.add(entry["epoch"])
    best_file = run_dir / "best.json"  # what best.pt really holds (written with it)
    best = json.loads(best_file.read_text()) if best_file.exists() else max(history, key=lambda entry: entry["mean_ap50"])
    lines += [
        "",
        f"Best so far (best.pt): epoch {best['epoch']} (mean AP50 {best['mean_ap50']:.3f}). Higher is better; 1.0 would be perfect.",
    ]
    return "\n".join(lines)


def train(data_dir: Path, run_dir: Path, config: Config, device: torch.device, epochs_this_session: int = 0) -> dict[str, Any]:
    """Train until all epochs are done, or stop cleanly after `epochs_this_session` epochs (0 = no limit)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    check_space(run_dir)
    print(f"Google Drive free space: {drive_free_gb(run_dir):.1f} GB", flush=True)
    fingerprints = check_data(data_dir)
    config_path = run_dir / "config.json"
    saved_config = {"config": asdict(config), "data": fingerprints, "categories": CLASS_NAMES}
    if config_path.exists():
        previous = json.loads(config_path.read_text())
        changed = settings_that_differ(previous, json.loads(json.dumps(saved_config)))
        if changed:
            raise SystemExit(f"STOPPED: {run_dir} holds a run with different settings or data ({', '.join(changed)}). Use a new --run-dir.")
    else:
        config_path.write_text(json.dumps(saved_config, indent=2))

    torch.manual_seed(config.seed)
    train_set = CocoDetection(data_dir, "train", config.max_train_images)
    val_set = CocoDetection(data_dir, "val", config.max_val_images)
    model = build_model(config).to(device)
    parameters = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.SGD(parameters, lr=config.learning_rate, momentum=config.momentum, weight_decay=config.weight_decay)
    use_amp = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    state = {"epoch": 1, "batches_done": 0, "step": 0, "best_mean_ap50": -1.0, "best_epoch": 0}
    best_path, history_path = run_dir / "best.pt", run_dir / "val-history.json"
    history = read_history(history_path)  # kept even if every save was lost, so best.pt stays protected
    found = load_newest_checkpoint(run_dir, device)
    if found is not None:
        loaded_path, checkpoint = found
        model.load_state_dict(checkpoint["model"])
        optimizer.load_state_dict(checkpoint["optimizer"])
        scaler.load_state_dict(checkpoint["scaler"])
        state = checkpoint["state"]
        # The scores are also stored inside each save, in case Drive lost the newest val-history.json.
        if len(checkpoint.get("history", [])) > len(history):
            history = checkpoint["history"]
        remove_saves_before(run_dir, loaded_path)
    elif best_path.exists():
        # Every progress save was lost, but best.pt has the full model of its epoch: continue after it.
        best = torch.load(best_path, map_location=device, weights_only=False)
        best_epoch, scores = int(best["validation"]["epoch"]), best["validation"]
        model.load_state_dict(best["model"])
        state = {
            "epoch": best_epoch + 1,
            "batches_done": 0,
            "step": sum(batches_in_epoch(train_set, epoch, config) for epoch in range(1, best_epoch + 1)),
            "best_mean_ap50": float(scores["mean_ap50"]),
            "best_epoch": best_epoch,
        }
        if not any(entry["epoch"] == best_epoch and entry["mean_ap50"] == scores["mean_ap50"] for entry in history):
            history.append({**scores, "restored_from": "best.pt"})
            history_path.write_text(json.dumps(history, indent=2))
        last_finished = max(entry["epoch"] for entry in history)
        again = f" Epochs {best_epoch + 1}-{last_finished} are trained again." if last_finished > best_epoch else " Nothing is retrained."
        print(
            f"No progress save was found, so training continues from best.pt (epoch {best_epoch}, mean AP50 "
            f"{scores['mean_ap50']:.3f}) with epoch {best_epoch + 1}.{again}",
            flush=True,
        )
        log(run_dir, {"type": "resumed_from_best", "epoch": best_epoch, "note": "optimizer momentum restarts"})
    elif history or (run_dir / "log.jsonl").exists():
        raise SystemExit(
            f"STOPPED: {run_dir} already has training results but no save to continue from. "
            "Training will not start again from epoch 1 by itself. Tell Claude; do not delete anything."
        )
    made_this_session: list[Path] = []

    def save_last() -> None:
        check_space(run_dir)
        path = run_dir / checkpoint_name(state)
        save_atomically(
            {
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "scaler": scaler.state_dict(),
                "state": state,
                "history": history,
            },
            path,
        )
        made_this_session.append(path)
        remove_session_saves(made_this_session)

    model.train()
    finished_this_session = 0
    while state["epoch"] <= config.epochs:
        if epochs_this_session and finished_this_session >= epochs_this_session:
            print(f"\nSession finished: {finished_this_session} epoch(s) trained in this session. Progress is saved.", flush=True)
            print(progress_report(run_dir, config.epochs), flush=True)
            print(f"\nNext time: run the notebook again and it continues with epoch {state['epoch']} of {config.epochs}.", flush=True)
            return {"stopped_for_session": True, "next_epoch": state["epoch"]}
        epoch = state["epoch"]
        order = epoch_order(train_set, epoch, config)
        train_set.flip_probability = config.hflip
        train_set.flip_seed = {index: config.seed * 7919 + epoch * 100003 + index for index in order}
        batches = [order[i : i + config.batch_size] for i in range(0, len(order), config.batch_size)]
        loader = torch.utils.data.DataLoader(
            train_set, batch_sampler=batches[state["batches_done"] :], collate_fn=collate, num_workers=2, pin_memory=use_amp
        )
        started, losses = time.monotonic(), []
        for images, targets in loader:
            rate = learning_rate(state["step"], epoch, config)
            for group in optimizer.param_groups:
                group["lr"] = rate
            images = [image.to(device, non_blocking=True) for image in images]
            targets = [{key: value.to(device) for key, value in target.items()} for target in targets]
            with torch.autocast(device_type=device.type, enabled=use_amp):
                loss_parts = model(images, targets)
                loss = sum(loss_parts.values())
            if not torch.isfinite(loss):
                raise SystemExit(f"STOPPED: the training loss became {loss.item()} at epoch {epoch}. Tell Claude; do not keep this run.")
            optimizer.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            state["batches_done"] += 1
            state["step"] += 1
            losses.append(loss.item())

            done = state["batches_done"]
            if done % config.log_every == 0 or done == len(batches):
                seconds = (time.monotonic() - started) / max(len(losses), 1)
                left = seconds * (len(batches) - done) / 60
                average = float(np.mean(losses[-config.log_every :]))
                print(
                    f"Epoch {epoch}/{config.epochs} · batch {done}/{len(batches)} · loss {average:.3f} · "
                    f"{seconds:.2f} s/batch · about {left:.0f} min left in this epoch",
                    flush=True,
                )
                log(
                    run_dir,
                    {
                        "type": "train",
                        "epoch": epoch,
                        "batch": done,
                        "batches": len(batches),
                        "step": state["step"],
                        "lr": rate,
                        "loss": average,
                        **{k: v.item() for k, v in loss_parts.items()},
                    },
                )
            if done % config.checkpoint_every == 0:
                save_last()

        print(f"Epoch {epoch} finished. Checking on {len(val_set)} validation photos...", flush=True)
        scores = validate(model, val_set, device, config)
        scores["epoch"] = epoch
        # "Best so far" comes from every saved score, not only from the checkpoint, so resuming from an
        # older save can never let a weaker model replace a better best.pt.
        best_before = max([state["best_mean_ap50"], *(entry["mean_ap50"] for entry in history)])
        history.append(scores)
        history_path.write_text(json.dumps(history, indent=2))
        log(run_dir, {"type": "val", **scores})
        summary = ", ".join(f"{name} AP50 {values['ap50']:.3f}" for name, values in scores["classes"].items())
        print(f"   validation: mean AP50 {scores['mean_ap50']:.3f} ({summary})", flush=True)
        if scores["mean_ap50"] > best_before:
            state["best_mean_ap50"], state["best_epoch"] = scores["mean_ap50"], epoch
            save_atomically(
                {
                    "model": model.state_dict(),
                    "model_version": config.model_version,
                    "categories": CLASS_NAMES,
                    "config": asdict(config),
                    "validation": scores,
                },
                best_path,
            )
            (run_dir / "best.json").write_text(json.dumps({"epoch": epoch, "mean_ap50": scores["mean_ap50"]}))
            print(f"   best so far -> saved best.pt (epoch {epoch})", flush=True)
        state["epoch"], state["batches_done"] = epoch + 1, 0
        save_last()
        finished_this_session += 1

    result = {"best_epoch": state["best_epoch"], "best_mean_ap50": state["best_mean_ap50"], "epochs": config.epochs}
    (run_dir / "training-done.json").write_text(json.dumps(result, indent=2))
    print(
        f"\nTraining finished. Best epoch {result['best_epoch']} (validation mean AP50 {result['best_mean_ap50']:.3f}). Saved best.pt.",
        flush=True,
    )
    print(progress_report(run_dir, config.epochs), flush=True)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True, help="The prepared folder from P8.2")
    parser.add_argument("--run-dir", type=Path, required=True, help="Where checkpoints and logs go (on Google Drive)")
    parser.add_argument("--epochs", type=int, default=Config.epochs)
    parser.add_argument("--batch-size", type=int, default=Config.batch_size)
    parser.add_argument("--epochs-this-session", type=int, default=0, help="Stop cleanly after this many epochs (0 = train to the end)")
    parser.add_argument("--progress", action="store_true", help="Only print how far training has got, then stop")
    parser.add_argument("--allow-cpu", action="store_true", help="Only for tests: training on a CPU takes days")
    parser.add_argument("--quick-test", action="store_true", help="Tiny images, no download of pretrained weights (tests only)")
    args = parser.parse_args(argv)

    config = Config(epochs=args.epochs, batch_size=args.batch_size)
    if args.progress:
        print(progress_report(args.run_dir, config.epochs))
        return 0
    if args.quick_test:
        config = Config(
            epochs=args.epochs,
            batch_size=args.batch_size,
            pretrained=False,
            min_size=96,
            max_size=96,
            warmup_steps=2,
            checkpoint_every=1,
            log_every=1,
            empty_fraction=1.0,
        )
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif args.allow_cpu:
        device = torch.device("cpu")
    else:
        print("STOPPED: no GPU. In Colab: Runtime > Change runtime type > T4 GPU > Save, then run all cells again.", file=sys.stderr)
        return 1
    print(f"Training {config.model_version} on {device} ({torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU'})", flush=True)
    train(args.data, args.run_dir, config, device, args.epochs_this_session)
    return 0


if __name__ == "__main__":
    sys.exit(main())
