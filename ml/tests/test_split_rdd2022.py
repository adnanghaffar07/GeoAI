"""Tests for P8.2 split_rdd2022.py on a small fake dataset laid out like the unpacked RDD2022."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from data_prep import split_rdd2022 as split


def picture(seed: int, size: tuple[int, int] = (200, 200), jitter: int = 0) -> Image.Image:
    """A smooth random picture; the same seed gives the same picture (jitter = tiny changes)."""
    rng = np.random.default_rng(seed)
    base = Image.fromarray(rng.integers(0, 256, (16, 17), dtype=np.uint8)).resize(size, Image.Resampling.BILINEAR)
    pixels = np.asarray(base, dtype=np.int16)
    if jitter:
        pixels = pixels + np.random.default_rng(seed + 10_000).integers(-jitter, jitter + 1, pixels.shape)
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8)).convert("RGB")


def voc(boxes: list[tuple[str, float, float, float, float]], size: tuple[int, int]) -> str:
    objects = "".join(
        f"<object><name>{code}</name><bndbox><xmin>{x1}</xmin><ymin>{y1}</ymin><xmax>{x2}</xmax><ymax>{y2}</ymax></bndbox></object>"
        for code, x1, y1, x2, y2 in boxes
    )
    return f"<annotation><size><width>{size[0]}</width><height>{size[1]}</height><depth>3</depth></size>{objects}</annotation>"


def add(
    data: Path, country: str, name: str, image: Image.Image, boxes: list[tuple[str, float, float, float, float]], split_name: str = "train"
) -> None:
    images = data / "RDD2022" / country / split_name / "images"
    images.mkdir(parents=True, exist_ok=True)
    image.save(images / f"{name}.jpg", quality=95)
    if split_name == "train":
        labels = data / "RDD2022" / country / "train" / "annotations" / "xmls"
        labels.mkdir(parents=True, exist_ok=True)
        (labels / f"{name}.xml").write_text(voc(boxes, image.size))


@pytest.fixture
def data(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    pothole = [("D40", 10, 10, 60, 60)]
    for i in range(40):  # 40 distinct Japan photos -> about 4 go to validation
        add(root, "Japan", f"Japan_{i:03}", picture(i), pothole if i % 2 else [])
    for i in range(10):
        add(root, "Czech", f"Czech_{i:03}", picture(1000 + i), [("D20", 5, 5, 50, 50), ("D00", 0, 0, 30, 100)])
    add(root, "Czech", "Czech_unlabelled", picture(1500), [], split_name="test")  # official test photo: no labels, ignored
    for i in range(5):
        add(root, "China_Drone", f"China_Drone_{i:03}", picture(2000 + i), pothole)
    # Near-duplicate pairs inside India (e.g. frames a second apart).
    for i in range(6):
        add(root, "India", f"India_{i:03}_a", picture(3000 + i), [("D10", 1, 1, 40, 40)])
        add(root, "India", f"India_{i:03}_b", picture(3000 + i, jitter=2), [("D10", 1, 1, 40, 40)])
    # An India photo that is practically a Czech test photo -> must be removed from training.
    add(root, "India", "India_copy_of_czech", picture(1003, jitter=2), pothole)
    # An exact duplicate file under another name.
    (root / "RDD2022/Japan/train/images/Japan_dup.jpg").write_bytes((root / "RDD2022/Japan/train/images/Japan_001.jpg").read_bytes())
    (root / "RDD2022/Japan/train/annotations/xmls/Japan_dup.xml").write_text(voc(pothole, (200, 200)))
    # Box problems and ignored codes.
    add(
        root,
        "Norway",
        "Norway_big",
        picture(4000, size=(3650, 2044)),
        [("D40", 3650 / 2, 1000, 3700, 2100), ("D00", 100, 100, 101, 900), ("D44", 0, 0, 50, 50)],
    )
    return root


def run(data: Path, out: Path) -> dict:
    return split.run(data, out)


def coco(out: Path, name: str) -> dict:
    return json.loads((out / "annotations" / f"{name}.json").read_text())


def test_test_set_is_every_labelled_czech_photo_and_drone_is_left_out(data: Path, tmp_path: Path) -> None:
    manifest = run(data, tmp_path / "out")
    test = coco(tmp_path / "out", "test")
    assert {image["country"] for image in test["images"]} == {"Czech"}
    assert len(test["images"]) == 10  # the unlabelled official test photo is not used
    everything = [image["country"] for name in ("train", "val") for image in coco(tmp_path / "out", name)["images"]]
    assert "Czech" not in everything and "China_Drone" not in everything
    assert manifest["cleaning_report"]["left_out_China_Drone"] == 5
    assert manifest["splits"]["test"]["boxes_by_class"] == {"pothole": 0, "surface_cracking": 10, "pavement_deterioration": 10}


def test_near_duplicates_stay_together_and_test_lookalikes_are_removed(data: Path, tmp_path: Path) -> None:
    manifest = run(data, tmp_path / "out")
    where = {Path(image["source"]).stem: name for name in ("train", "val", "test") for image in coco(tmp_path / "out", name)["images"]}
    for i in range(6):
        assert where[f"India_{i:03}_a"] == where[f"India_{i:03}_b"]
    assert "India_copy_of_czech" not in where
    assert manifest["cleaning_report"]["removed_near_duplicate_of_test_photo"] == 1
    assert manifest["cleaning_report"]["near_duplicate_groups_with_2_or_more"] >= 7


def test_exact_duplicates_are_kept_once(data: Path, tmp_path: Path) -> None:
    manifest = run(data, tmp_path / "out")
    names = [Path(image["source"]).stem for name in ("train", "val") for image in coco(tmp_path / "out", name)["images"]]
    assert ("Japan_dup" in names) != ("Japan_001" in names)
    assert manifest["cleaning_report"]["exact_duplicates_removed"] == 1


def test_big_photos_are_shrunk_and_boxes_cleaned(data: Path, tmp_path: Path) -> None:
    manifest = run(data, tmp_path / "out")
    for name in ("train", "val"):
        data_split = coco(tmp_path / "out", name)
        for image in data_split["images"]:
            if image["country"] == "Norway":
                assert max(image["width"], image["height"]) == split.MAX_SIDE
                with Image.open(tmp_path / "out" / "images" / image["file_name"]) as saved:
                    assert saved.size == (image["width"], image["height"])
                boxes = [a for a in data_split["annotations"] if a["image_id"] == image["id"]]
                assert len(boxes) == 1  # 1-pixel-wide box dropped, D44 ignored
                x, y, w, h = boxes[0]["bbox"]
                scale = split.MAX_SIDE / 3650
                assert x == pytest.approx(3650 / 2 * scale, abs=0.01)
                assert x + w == pytest.approx(3650 * scale, abs=0.01)  # clipped to the photo edge
                assert y + h == pytest.approx(2044 * scale, abs=0.01)
                assert boxes[0]["category_id"] == 1 and boxes[0]["rdd_code"] == "D40"
    report = manifest["cleaning_report"]
    assert report["boxes_clipped"] == 1 and report["boxes_dropped_too_small"] == 1 and report["ignored_code_D44"] == 1


def test_validation_is_about_ten_percent_per_country(data: Path, tmp_path: Path) -> None:
    run(data, tmp_path / "out")
    val = coco(tmp_path / "out", "val")["images"]
    japan_val = sum(1 for image in val if image["country"] == "Japan")
    assert 4 <= japan_val <= 5  # 10% of 40 unique Japan photos, whole groups only
    assert any(image["country"] == "India" for image in val)


def test_same_input_gives_exactly_the_same_split(data: Path, tmp_path: Path) -> None:
    first = run(data, tmp_path / "one")
    second = run(data, tmp_path / "two")
    for name in ("train", "val", "test"):
        assert first["splits"][name]["sha256_list"] == second["splits"][name]["sha256_list"]
        assert first["splits"][name]["sha256_annotations"] == second["splits"][name]["sha256_annotations"]


def test_refuses_a_folder_that_is_not_empty(data: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "old.txt").write_text("old")
    with pytest.raises(SystemExit, match="not empty"):
        run(data, out)


def test_popcount_counts_bits() -> None:
    values = np.array([0, 1, 0xFF, 0xFFFFFFFFFFFFFFFF, 0x8000000000000001], dtype=np.uint64)
    assert split.popcount(values).tolist() == [0, 1, 8, 64, 2]


def test_categories_never_change_order() -> None:
    # The trained model's class numbers depend on this order (the app maps them back to names).
    assert [c["name"] for c in split.CATEGORIES] == ["pothole", "surface_cracking", "pavement_deterioration"]
    assert [c["id"] for c in split.CATEGORIES] == [1, 2, 3]
