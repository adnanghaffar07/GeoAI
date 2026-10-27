"""P8.4 training script, tested on a tiny fake dataset on the CPU (real training runs on a Colab GPU)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import torch
from PIL import Image

from training import train_frcnn as train


def make_prepared(root: Path, train_images: int = 6, val_images: int = 2) -> Path:
    """A folder laid out like split_rdd2022.py's output, with matching split-manifest.json."""
    data = root / "prepared"
    (data / "images" / "Japan").mkdir(parents=True)
    (data / "annotations").mkdir()
    manifest = {"splits": {}}
    for split, count in (("train", train_images), ("val", val_images), ("test", 2)):
        images, annotations = [], []
        for i in range(count):
            name = f"Japan/{split}_{i}.jpg"
            colour = (i * 30 % 255, 80, 160)
            Image.new("RGB", (96, 96), colour).save(data / "images" / name)
            images.append({"id": i + 1, "file_name": name, "width": 96, "height": 96, "country": "Japan"})
            if i % 3 != 2:  # every third photo has no damage
                annotations.append(
                    {
                        "id": len(annotations) + 1,
                        "image_id": i + 1,
                        "category_id": i % 3 + 1,
                        "bbox": [10, 10, 40, 30],
                        "area": 1200,
                        "iscrowd": 0,
                    }
                )
        path = data / "annotations" / f"{split}.json"
        path.write_text(json.dumps({"images": images, "annotations": annotations, "categories": []}))
        manifest["splits"][split] = {"sha256_annotations": hashlib.sha256(path.read_bytes()).hexdigest()}
    (data / "split-manifest.json").write_text(json.dumps(manifest))
    return data


def test_flip_moves_boxes_with_the_picture(tmp_path: Path) -> None:
    data = make_prepared(tmp_path)
    dataset = train.CocoDetection(data, "train")
    _, plain = dataset[0]
    dataset.flip_seed = {0: next(seed for seed in range(100) if __import__("random").Random(seed).random() < 0.5)}
    image, flipped = dataset[0]
    assert image.shape == (3, 96, 96)
    assert plain["boxes"].tolist() == [[10.0, 10.0, 50.0, 40.0]]
    assert flipped["boxes"].tolist() == [[46.0, 10.0, 86.0, 40.0]]


def test_never_reads_the_test_set(tmp_path: Path) -> None:
    data = make_prepared(tmp_path)
    with pytest.raises(ValueError, match="locked"):
        train.CocoDetection(data, "test")


def test_epoch_order_is_repeatable_and_samples_empty_photos(tmp_path: Path) -> None:
    dataset = train.CocoDetection(make_prepared(tmp_path, train_images=30), "train")
    config = train.Config(empty_fraction=0.5)
    first, again, other = (
        train.epoch_order(dataset, 1, config),
        train.epoch_order(dataset, 1, config),
        train.epoch_order(dataset, 2, config),
    )
    assert first == again and first != other
    assert sum(1 for i in first if dataset.has_damage(i)) == 20  # every photo with damage
    assert sum(1 for i in first if not dataset.has_damage(i)) == 5  # half of the 10 empty ones


def test_learning_rate_schedule() -> None:
    config = train.Config(learning_rate=0.01, warmup_steps=100, lr_drop_epochs=(8, 11))
    assert train.learning_rate(0, 1, config) == pytest.approx(0.01 * 0.001)
    assert train.learning_rate(100, 1, config) == pytest.approx(0.01)
    assert train.learning_rate(9999, 8, config) == pytest.approx(0.01)
    assert train.learning_rate(9999, 9, config) == pytest.approx(0.001)
    assert train.learning_rate(9999, 12, config) == pytest.approx(0.0001)


def test_refuses_a_damaged_data_copy(tmp_path: Path) -> None:
    data = make_prepared(tmp_path)
    (data / "annotations" / "train.json").write_text("{}")
    with pytest.raises(SystemExit, match="does not match"):
        train.check_data(data)


def test_stops_without_a_gpu_unless_allowed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    if torch.cuda.is_available():
        pytest.skip("machine has a GPU")
    assert train.main(["--data", str(tmp_path), "--run-dir", str(tmp_path / "run")]) == 1
    assert "Change runtime type" in capsys.readouterr().err


def test_trains_saves_and_continues_after_a_disconnect(tmp_path: Path) -> None:
    data = make_prepared(tmp_path)
    run = tmp_path / "run"
    common = ["--data", str(data), "--run-dir", str(run), "--allow-cpu", "--quick-test", "--batch-size", "2"]

    assert train.main([*common, "--epochs", "1"]) == 0  # like a session that ended after epoch 1
    assert sorted(p.name for p in run.glob("checkpoint-*.pt"))[-1] == "checkpoint-e02-b000000.pt" and (run / "best.pt").exists()
    first_history = json.loads((run / "val-history.json").read_text())
    assert [entry["epoch"] for entry in first_history] == [1]

    # A new session with the full plan continues from epoch 2 instead of starting again...
    # ...but only with the same settings: the stored config must match.
    with pytest.raises(SystemExit, match=r"different settings or data \(epochs\)"):
        train.main([*common, "--epochs", "2"])

    config = json.loads((run / "config.json").read_text())
    config["config"]["epochs"] = 2
    (run / "config.json").write_text(json.dumps(config, indent=2))
    assert train.main([*common, "--epochs", "2"]) == 0
    history = json.loads((run / "val-history.json").read_text())
    assert [entry["epoch"] for entry in history] == [1, 2]
    steps = [entry["step"] for entry in map(json.loads, (run / "log.jsonl").read_text().splitlines()) if entry["type"] == "train"]
    assert steps == sorted(steps) and steps[-1] == 6  # 3 batches per epoch x 2 epochs, no batch repeated

    best = torch.load(run / "best.pt", weights_only=False)
    assert best["model_version"] == train.MODEL_VERSION
    assert best["categories"] == {1: "pothole", 2: "surface_cracking", 3: "pavement_deterioration"}
    assert set(best["validation"]["classes"]) == {"pothole", "surface_cracking", "pavement_deterioration"}
    assert json.loads((run / "training-done.json").read_text())["epochs"] == 2


def test_resumes_in_the_middle_of_an_epoch(tmp_path: Path) -> None:
    data = make_prepared(tmp_path, train_images=8)
    run = tmp_path / "run"
    config = train.Config(
        epochs=1,
        batch_size=2,
        pretrained=False,
        min_size=96,
        max_size=96,
        warmup_steps=2,
        checkpoint_every=1,
        log_every=1,
        empty_fraction=1.0,
    )
    device = torch.device("cpu")
    # Simulate a disconnect: train 2 of 4 batches, then save last.pt as the checkpoint would be.
    torch.manual_seed(0)
    model = train.build_model(config)
    optimizer = torch.optim.SGD([p for p in model.parameters() if p.requires_grad], lr=0.01, momentum=0.9)
    run.mkdir()
    (run / "config.json").write_text(
        json.dumps(
            {"config": json.loads(json.dumps(train.asdict(config))), "data": train.check_data(data), "categories": train.CLASS_NAMES},
            indent=2,
        )
    )
    scaler = torch.amp.GradScaler("cuda", enabled=False)
    state = {"epoch": 1, "batches_done": 2, "step": 2, "best_mean_ap50": -1.0, "best_epoch": 0}
    train.save_atomically(
        {"model": model.state_dict(), "optimizer": optimizer.state_dict(), "scaler": scaler.state_dict(), "state": state}, run / "last.pt"
    )

    train.train(data, run, config, device)
    batches = [json.loads(line) for line in (run / "log.jsonl").read_text().splitlines() if json.loads(line)["type"] == "train"]
    assert [entry["batch"] for entry in batches] == [3, 4]  # only the remaining batches ran


def test_stops_after_the_epochs_for_this_session_and_continues_next_time(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = make_prepared(tmp_path)
    run = tmp_path / "run"
    common = ["--data", str(data), "--run-dir", str(run), "--allow-cpu", "--quick-test", "--batch-size", "2", "--epochs", "3"]

    assert train.main([*common, "--epochs-this-session", "1"]) == 0  # session 1: epoch 1 only
    output = capsys.readouterr().out
    assert "Session finished: 1 epoch(s)" in output and "continues with epoch 2 of 3" in output
    assert "Finished 1 of 3 epochs." in output
    assert not (run / "training-done.json").exists()

    assert train.main([*common, "--epochs-this-session", "1"]) == 0  # session 2: epoch 2
    assert "continues with epoch 3 of 3" in capsys.readouterr().out

    assert train.main([*common, "--epochs-this-session", "1"]) == 0  # session 3: epoch 3, then done
    output = capsys.readouterr().out
    assert "Training finished." in output and "Finished 3 of 3 epochs." in output
    assert [entry["epoch"] for entry in json.loads((run / "val-history.json").read_text())] == [1, 2, 3]

    assert train.main(["--data", str(data), "--run-dir", str(run), "--epochs", "3", "--progress"]) == 0  # check any time, no GPU needed
    assert "Best so far (best.pt): epoch" in capsys.readouterr().out


def test_progress_before_any_epoch(tmp_path: Path) -> None:
    assert train.progress_report(tmp_path, 12) == "No epoch finished yet."


QUICK = ["--allow-cpu", "--quick-test", "--batch-size", "2"]


def test_old_single_file_save_that_cannot_be_opened_stops_instead_of_starting_again(tmp_path: Path) -> None:
    data = make_prepared(tmp_path)
    run = tmp_path / "run"
    run.mkdir()
    (run / "last.pt").write_bytes(b"old single-file save, damaged")
    with pytest.raises(SystemExit, match="none of the saves"):  # never silently start again from zero
        train.main(["--data", str(data), "--run-dir", str(run), *QUICK, "--epochs", "1"])


def test_saves_from_before_a_session_are_never_deleted_during_it(tmp_path: Path) -> None:
    """2026-10-19: Colab stopped suddenly, Google Drive dropped the newest saves but applied the deletions
    of the older ones, so no save was left. Older saves are now removed only once a newer one has been
    opened in a later session (proof that it reached Drive)."""
    data = make_prepared(tmp_path)
    run = tmp_path / "run"
    common = ["--data", str(data), "--run-dir", str(run), *QUICK, "--epochs", "3", "--epochs-this-session", "1"]
    assert train.main(common) == 0
    # checkpoint_every=1 in quick tests: a save after every batch; this session keeps its newest two.
    assert sorted(p.name for p in run.glob("checkpoint-*.pt")) == ["checkpoint-e01-b000003.pt", "checkpoint-e02-b000000.pt"]
    (run / "last.pt").write_bytes(b"older format, no longer needed")

    assert train.main(common) == 0  # next session opens checkpoint-e02-b000000.pt
    saves = sorted(p.name for p in run.glob("checkpoint-*.pt"))
    assert "checkpoint-e02-b000000.pt" in saves  # the save this session started from is kept all session
    assert not any(name.startswith("checkpoint-e01") for name in saves)  # older ones went once it had opened
    assert not (run / "last.pt").exists()


def test_when_every_save_is_lost_training_continues_from_best_pt(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = make_prepared(tmp_path)
    run = tmp_path / "run"
    common = ["--data", str(data), "--run-dir", str(run), *QUICK, "--epochs", "3", "--epochs-this-session", "1"]
    assert train.main(common) == 0
    best_epoch = torch.load(run / "best.pt", weights_only=False)["validation"]["epoch"]
    assert best_epoch == 1
    # What Drive kept on 2026-10-20: best.pt, but no progress save and a val-history.json without the last epoch.
    for save in run.glob("checkpoint-*.pt"):
        save.unlink()
    (run / "val-history.json").write_text("[]")
    capsys.readouterr()

    assert train.main(common) == 0
    output = capsys.readouterr().out
    assert "continues from best.pt (epoch 1" in output and "with epoch 2. Nothing is retrained." in output
    history = json.loads((run / "val-history.json").read_text())
    assert [(entry["epoch"], entry.get("restored_from")) for entry in history] == [(1, "best.pt"), (2, None)]
    steps = [entry["step"] for entry in map(json.loads, (run / "log.jsonl").read_text().splitlines()) if entry["type"] == "train"]
    assert steps[-1] == 6  # the step count carries on (3 batches per epoch), so the learning-rate plan is unchanged


def test_never_starts_again_from_epoch_1_over_existing_results(tmp_path: Path) -> None:
    data = make_prepared(tmp_path)
    run = tmp_path / "run"
    common = ["--data", str(data), "--run-dir", str(run), *QUICK, "--epochs", "2", "--epochs-this-session", "1"]
    assert train.main(common) == 0
    for save in [*run.glob("checkpoint-*.pt"), run / "best.pt"]:
        save.unlink()
    with pytest.raises(SystemExit, match="will not start again from epoch 1"):
        train.main(common)


def test_a_save_lost_or_cut_off_on_drive_falls_back_to_the_one_before(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = make_prepared(tmp_path)
    run = tmp_path / "run"
    common = ["--data", str(data), "--run-dir", str(run), *QUICK]
    assert train.main([*common, "--epochs", "1"]) == 0
    config = json.loads((run / "config.json").read_text())
    config["config"]["epochs"] = 2
    (run / "config.json").write_text(json.dumps(config, indent=2))
    newest = run / "checkpoint-e02-b000000.pt"
    newest.write_bytes(newest.read_bytes()[:1000])  # cut off half-way, as when Colab stops during an upload
    capsys.readouterr()

    assert train.main([*common, "--epochs", "2"]) == 0
    output = capsys.readouterr().out
    assert "Skipping a damaged save checkpoint-e02-b000000.pt" in output
    assert "Continuing from checkpoint-e01-b000003.pt: epoch 1, batch 3" in output  # nothing worse than one batch lost


def test_training_an_epoch_again_never_replaces_a_better_best_model(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = make_prepared(tmp_path)
    run = tmp_path / "run"
    common = ["--data", str(data), "--run-dir", str(run), *QUICK, "--epochs", "1"]
    assert train.main(common) == 0
    best_before = (run / "best.pt").read_bytes()
    # Pretend the first try of epoch 1 scored very well, then Drive lost every save made after it.
    history = json.loads((run / "val-history.json").read_text())
    history[0]["mean_ap50"] = 0.99
    (run / "val-history.json").write_text(json.dumps(history))
    (run / "checkpoint-e02-b000000.pt").unlink()  # only the save from before epoch 1 was scored is left
    (run / "training-done.json").unlink()
    capsys.readouterr()

    assert train.main(common) == 0  # the rest of epoch 1 is trained again
    assert (run / "best.pt").read_bytes() == best_before  # the weaker retrained model did not replace it
    report = train.progress_report(run, 1)
    assert "Finished 1 of 1 epochs." in report and "(trained again)" in report
    assert [entry["epoch"] for entry in json.loads((run / "val-history.json").read_text())] == [1, 1]


def test_stops_with_a_clear_message_when_google_drive_is_nearly_full(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = make_prepared(tmp_path)
    run = tmp_path / "run"
    common = ["--data", str(data), "--run-dir", str(run), *QUICK, "--epochs", "1"]
    monkeypatch.setattr(train, "drive_free_gb", lambda path: 0.4)
    with pytest.raises(SystemExit, match="Google Drive has only 0.4 GB free"):
        train.main(common)

    # Space running out during a session also stops it before a save that would be lost.
    free = iter([50.0, 50.0, 0.4])
    monkeypatch.setattr(train, "drive_free_gb", lambda path: next(free, 0.4))
    with pytest.raises(SystemExit, match="Trash"):
        train.main(common)


def test_how_often_progress_is_saved_may_change_during_a_run() -> None:
    stored = {"config": {"epochs": 12, "checkpoint_every": 1000, "log_every": 50}, "data": {"train": "abc"}}
    assert train.settings_that_differ(stored, {**stored, "config": {"epochs": 12, "checkpoint_every": 2000, "log_every": 50}}) == []
    assert train.settings_that_differ(stored, {**stored, "config": {"epochs": 10, "checkpoint_every": 2000, "log_every": 50}}) == ["epochs"]
    assert train.settings_that_differ(stored, {**stored, "data": {"train": "changed"}}) == ["data"]
