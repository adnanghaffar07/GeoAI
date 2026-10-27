"""P8.2: clean RDD2022 and split it into training, validation and test sets (test is then locked).

Runs on Google Colab right after fetch_rdd2022.py, on its output folder:

    python split_rdd2022.py --data /content/rdd2022/data --out /content/rdd2022/prepared

Rules (documentation/04-design/ml-baseline-plan.md, sections 2-3; decisions of 2026-10-16):
- Only labelled photos are used. RDD2022's own "test" photos have no labels and are ignored.
- Test set = every labelled Czech photo (a whole country the model never trains on).
- China_Drone is left out of model 0.1 (drone view from above, unlike phone photos).
- RDD2022 codes become the app's 3 classes; every other code is ignored.
- Boxes are clipped to the photo; boxes thinner than 2 pixels are dropped.
- Exact duplicate photos are kept once. Near-duplicates (almost the same photo, e.g. two
  frames a second apart) are grouped and always kept in the same set, so the model is never
  checked on a photo it has practically seen. Any training photo that is a near-duplicate of a
  test photo is removed.
- Validation = about 10% of each training country, picked by group with a fixed seed, so
  re-running gives exactly the same split.
- Big photos (Norway, about 3,650 pixels wide) are shrunk so the longest side is at most
  1,333 pixels (the size the model works at anyway); boxes are scaled with them.

Output (in --out):
- images/<country>/<name>.jpg          prepared photos
- annotations/{train,val,test}.json   boxes in COCO format (the format the evaluation reads)
- splits/{train,val,test}.txt          which original photo went where
- split-manifest.json                  counts, settings and fingerprints; the test set is
                                       "locked" by the SHA-256 of its list and annotations
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
from defusedxml import ElementTree
from PIL import Image

try:  # inside the repository
    from data_prep.fetch_rdd2022 import country_and_split, is_excluded
except ImportError:  # on Colab, both scripts sit in the same folder
    from fetch_rdd2022 import country_and_split, is_excluded  # type: ignore[no-redef]

SPLIT_VERSION = 1
SEED = 2026
TEST_COUNTRY = "Czech"
LEFT_OUT_COUNTRIES = {"China_Drone"}
VAL_FRACTION = 0.10
MAX_SIDE = 1333
MIN_BOX_SIDE = 2.0
HASH_SIZE = 16  # 16 x 16 = 256-bit difference hash
NEAR_DUPLICATE_BITS = 10  # at most 10 of 256 bits different = near-duplicate
JPEG_QUALITY = 92

# App class names in a fixed order: the model's class numbers depend on it. Never reorder.
CATEGORIES = [
    {"id": 1, "name": "pothole"},
    {"id": 2, "name": "surface_cracking"},
    {"id": 3, "name": "pavement_deterioration"},
]
CLASS_FROM_CODE = {"D40": "pothole", "D00": "surface_cracking", "D10": "surface_cracking", "D20": "pavement_deterioration"}
CATEGORY_ID = {category["name"]: category["id"] for category in CATEGORIES}
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")


@dataclass
class Box:
    code: str
    xmin: float
    ymin: float
    xmax: float
    ymax: float


@dataclass
class Photo:
    path: Path
    relative: str  # path inside the data folder, with forward slashes
    country: str
    width: int
    height: int
    boxes: list[Box] = field(default_factory=list)
    sha1: str = ""
    dhash: np.ndarray | None = None  # 4 x uint64 (256 bits)
    group: int = -1


# ---------------------------------------------------------------- reading


def read_boxes(xml_path: Path) -> tuple[tuple[int, int] | None, list[Box]]:
    """Image size (if given) and every box in one Pascal VOC label file."""
    root = ElementTree.parse(xml_path).getroot()
    width, height = root.findtext("size/width"), root.findtext("size/height")
    size = (int(float(width)), int(float(height))) if width and height and float(width) > 0 and float(height) > 0 else None
    boxes = []
    for obj in root.iter("object"):
        code = (obj.findtext("name") or "").strip()
        values = [obj.findtext(f"bndbox/{key}") for key in ("xmin", "ymin", "xmax", "ymax")]
        if code and all(values):
            boxes.append(Box(code, *(float(value) for value in values)))  # type: ignore[arg-type]
    return size, boxes


def find_photo(xml_path: Path) -> Path | None:
    """The photo for <...>/train/annotations/xmls/name.xml is <...>/train/images/name.jpg."""
    images = xml_path.parent.parent.parent / "images"
    for suffix in IMAGE_SUFFIXES:
        candidate = images / f"{xml_path.stem}{suffix}"
        if candidate.exists():
            return candidate
    return None


def collect_photos(data_dir: Path, report: Counter[str]) -> list[Photo]:
    photos = []
    for xml_path in sorted(data_dir.rglob("*.xml")):
        relative_xml = PurePosixPath(xml_path.relative_to(data_dir).as_posix())
        if is_excluded(relative_xml):
            raise SystemExit(f"STOPPED: excluded data found on disk: {relative_xml}")
        country, split = country_and_split(relative_xml)
        if split != "train":
            continue
        if country in LEFT_OUT_COUNTRIES:
            report[f"left_out_{country}"] += 1
            continue
        photo_path = find_photo(xml_path)
        if photo_path is None:
            report["label_without_photo"] += 1
            continue
        try:
            size, boxes = read_boxes(xml_path)
            with Image.open(photo_path) as image:
                real_size = image.size
        except Exception:  # noqa: BLE001 (count every unreadable pair; never crash on outside data)
            report["unreadable"] += 1
            continue
        if size and size != real_size:
            report["label_size_differs_from_photo"] += 1  # trust the photo
        photos.append(Photo(photo_path, photo_path.relative_to(data_dir).as_posix(), country, real_size[0], real_size[1], boxes))
    return photos


# ---------------------------------------------------------------- cleaning


def clean_boxes(photo: Photo, report: Counter[str]) -> list[tuple[str, Box]]:
    """Keep only our 3 classes; clip boxes to the photo; drop boxes that are too thin."""
    kept = []
    for box in photo.boxes:
        name = CLASS_FROM_CODE.get(box.code)
        if name is None:
            report[f"ignored_code_{box.code}"] += 1
            continue
        clipped = Box(
            box.code, max(0.0, box.xmin), max(0.0, box.ymin), min(float(photo.width), box.xmax), min(float(photo.height), box.ymax)
        )
        if (clipped.xmin, clipped.ymin, clipped.xmax, clipped.ymax) != (box.xmin, box.ymin, box.xmax, box.ymax):
            report["boxes_clipped"] += 1
        if clipped.xmax - clipped.xmin < MIN_BOX_SIDE or clipped.ymax - clipped.ymin < MIN_BOX_SIDE:
            report["boxes_dropped_too_small"] += 1
            continue
        kept.append((name, clipped))
    return kept


def difference_hash(path: Path) -> np.ndarray:
    """256-bit fingerprint of how a photo looks: nearly identical photos get nearly identical bits."""
    with Image.open(path) as image:
        image.draft("L", (HASH_SIZE * 8, HASH_SIZE * 8))  # JPEG: decode at reduced size, much faster
        pixels = np.asarray(image.convert("L").resize((HASH_SIZE + 1, HASH_SIZE), Image.Resampling.LANCZOS), dtype=np.int16)
    bits = (pixels[:, 1:] > pixels[:, :-1]).flatten()
    return np.packbits(bits).view(">u8").astype(np.uint64)


def popcount(values: np.ndarray) -> np.ndarray:
    """Number of 1-bits in each uint64 (vectorised)."""
    values = values - ((values >> np.uint64(1)) & np.uint64(0x5555555555555555))
    values = (values & np.uint64(0x3333333333333333)) + ((values >> np.uint64(2)) & np.uint64(0x3333333333333333))
    values = (values + (values >> np.uint64(4))) & np.uint64(0x0F0F0F0F0F0F0F0F)
    return (values * np.uint64(0x0101010101010101)) >> np.uint64(56)


def group_near_duplicates(photos: list[Photo], chunk: int = 64) -> None:
    """Put near-duplicate photos into the same group (union-find over all pairs, in chunks)."""
    parent = list(range(len(photos)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    hashes = np.stack([photo.dhash for photo in photos])  # type: ignore[misc]
    for start in range(0, len(photos), chunk):
        block = hashes[start : start + chunk]
        distance = popcount(block[:, None, :] ^ hashes[None, :, :]).sum(axis=2)
        rows, cols = np.nonzero(distance <= NEAR_DUPLICATE_BITS)
        for row, col in zip(rows.tolist(), cols.tolist(), strict=True):
            a, b = find(start + row), find(col)
            if a != b:
                parent[max(a, b)] = min(a, b)
    for index, photo in enumerate(photos):
        photo.group = find(index)


# ---------------------------------------------------------------- splitting


def assign_splits(photos: list[Photo], report: Counter[str]) -> dict[str, list[Photo]]:
    groups: dict[int, list[Photo]] = defaultdict(list)
    for photo in photos:
        groups[photo.group].append(photo)
    test_groups = {group for group, members in groups.items() if any(p.country == TEST_COUNTRY for p in members)}

    splits: dict[str, list[Photo]] = {"train": [], "val": [], "test": []}
    for group in test_groups:
        for photo in groups[group]:
            if photo.country == TEST_COUNTRY:
                splits["test"].append(photo)
            else:
                report["removed_near_duplicate_of_test_photo"] += 1  # would leak the test set into training

    rng = random.Random(SEED)  # noqa: S311 (repeatable data split, not security)
    by_country: dict[str, list[int]] = defaultdict(list)
    for group, members in sorted(groups.items()):
        if group not in test_groups:
            by_country[members[0].country].append(group)
    for _country, country_groups in sorted(by_country.items()):
        rng.shuffle(country_groups)
        total = sum(len(groups[group]) for group in country_groups)
        in_val = 0
        for group in country_groups:
            target = "val" if in_val < VAL_FRACTION * total else "train"
            splits[target].extend(groups[group])
            in_val += len(groups[group]) if target == "val" else 0
    for photos_in_split in splits.values():
        photos_in_split.sort(key=lambda photo: photo.relative)
    return splits


# ---------------------------------------------------------------- writing


def prepare_image(photo: Photo, images_dir: Path) -> tuple[str, int, int, float]:
    """Save the photo (shrunk if large) and return its new name, size and scale factor."""
    scale = min(1.0, MAX_SIDE / max(photo.width, photo.height))
    name = f"{photo.country}/{Path(photo.relative).stem}.jpg"
    target = images_dir / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(photo.path) as image:
        if scale < 1.0:
            image.draft("RGB", (round(photo.width * scale), round(photo.height * scale)))  # faster decode of big JPEGs
        image = image.convert("RGB")
        if scale < 1.0:
            image = image.resize((round(photo.width * scale), round(photo.height * scale)), Image.Resampling.LANCZOS)
        if (image.width, image.height) != (round(photo.width * scale), round(photo.height * scale)):
            raise SystemExit(f"STOPPED: unexpected size after resizing {photo.relative}")
        image.save(target, "JPEG", quality=JPEG_QUALITY)
        return name, image.width, image.height, scale


def write_split(split: str, photos: list[Photo], out_dir: Path, report: Counter[str]) -> dict[str, Any]:
    images, annotations = [], []
    class_counts: Counter[str] = Counter()
    started = time.monotonic()
    for image_id, photo in enumerate(photos, start=1):
        if image_id % 1000 == 0 or image_id == len(photos):
            elapsed = time.monotonic() - started
            left = elapsed / image_id * (len(photos) - image_id)
            print(
                f"   {split}: {image_id} of {len(photos)} photos saved ({elapsed / 60:.0f} min so far, about {left / 60:.0f} min left)",
                flush=True,
            )
        name, width, height, scale = prepare_image(photo, out_dir / "images")
        images.append(
            {"id": image_id, "file_name": name, "width": width, "height": height, "country": photo.country, "source": photo.relative}
        )
        for class_name, box in clean_boxes(photo, report):
            x, y = box.xmin * scale, box.ymin * scale
            w, h = (box.xmax - box.xmin) * scale, (box.ymax - box.ymin) * scale
            annotations.append(
                {
                    "id": len(annotations) + 1,
                    "image_id": image_id,
                    "category_id": CATEGORY_ID[class_name],
                    "bbox": [round(x, 2), round(y, 2), round(w, 2), round(h, 2)],
                    "area": round(w * h, 2),
                    "iscrowd": 0,
                    "rdd_code": box.code,
                }
            )
            class_counts[class_name] += 1
    coco = {"images": images, "annotations": annotations, "categories": CATEGORIES}
    annotation_path = out_dir / "annotations" / f"{split}.json"
    annotation_path.parent.mkdir(parents=True, exist_ok=True)
    annotation_path.write_text(json.dumps(coco, separators=(",", ":")))
    list_path = out_dir / "splits" / f"{split}.txt"
    list_path.parent.mkdir(parents=True, exist_ok=True)
    list_path.write_text("".join(f"{photo.relative}\n" for photo in photos))
    return {
        "photos": len(photos),
        "photos_without_boxes": len(images) - len({annotation["image_id"] for annotation in annotations}),
        "boxes_by_class": {category["name"]: class_counts[category["name"]] for category in CATEGORIES},
        "photos_by_country": dict(sorted(Counter(photo.country for photo in photos).items())),
        "sha256_list": sha256(list_path),
        "sha256_annotations": sha256(annotation_path),
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(data_dir: Path, out_dir: Path) -> dict[str, Any]:
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"STOPPED: {out_dir} is not empty. Use a new folder so old files never mix in.")
    report: Counter[str] = Counter()
    print("1/5 Reading labels and photos")
    photos = collect_photos(data_dir, report)
    if not photos:
        raise SystemExit(f"STOPPED: no labelled photos found in {data_dir}")
    print(f"   {len(photos)} labelled photos", flush=True)

    print("2/5 Removing exact duplicate photos")
    seen: dict[str, Photo] = {}
    unique = []
    for photo in photos:
        photo.sha1 = hashlib.sha1(photo.path.read_bytes()).hexdigest()  # noqa: S324 (duplicate check, not security)
        if photo.sha1 in seen:
            report["exact_duplicates_removed"] += 1
            continue
        seen[photo.sha1] = photo
        unique.append(photo)

    print("3/5 Finding near-duplicate photos")
    for index, photo in enumerate(unique, start=1):
        photo.dhash = difference_hash(photo.path)
        if index % 5000 == 0:
            print(f"   fingerprinted {index} of {len(unique)} photos", flush=True)
    group_near_duplicates(unique)
    group_sizes = Counter(photo.group for photo in unique)
    report["near_duplicate_groups_with_2_or_more"] = sum(1 for size in group_sizes.values() if size > 1)
    report["photos_in_near_duplicate_groups"] = sum(size for size in group_sizes.values() if size > 1)

    print("4/5 Splitting (test = Czech, validation = 10% of each other country)")
    splits = assign_splits(unique, report)

    print("5/5 Writing prepared photos and annotations")
    summary = {name: write_split(name, members, out_dir, report) for name, members in splits.items()}
    manifest = {
        "split_version": SPLIT_VERSION,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "settings": {
            "seed": SEED,
            "test_country": TEST_COUNTRY,
            "left_out_countries": sorted(LEFT_OUT_COUNTRIES),
            "excluded": "United States (never unpacked)",
            "val_fraction": VAL_FRACTION,
            "max_side_px": MAX_SIDE,
            "min_box_side_px": MIN_BOX_SIDE,
            "near_duplicate": f"dHash {HASH_SIZE}x{HASH_SIZE}, at most {NEAR_DUPLICATE_BITS} bits different",
            "class_from_code": CLASS_FROM_CODE,
            "categories": CATEGORIES,
        },
        "splits": summary,
        "largest_near_duplicate_group": max(group_sizes.values()),
        "cleaning_report": dict(sorted(report.items())),
        "test_set_locked": True,
    }
    (out_dir / "split-manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def print_summary(manifest: dict[str, Any]) -> None:
    print("\nSet     Photos  No damage   Pothole  Surface cracking  Pavement deterioration")
    for name, details in manifest["splits"].items():
        boxes = details["boxes_by_class"]
        print(
            f"{name:<6} {details['photos']:>7}  {details['photos_without_boxes']:>9}  {boxes['pothole']:>8}"
            f"  {boxes['surface_cracking']:>16}  {boxes['pavement_deterioration']:>22}"
        )
    print("\nCleaning:")
    for key, value in manifest["cleaning_report"].items():
        print(f"  {key}: {value}")
    print(f"  largest near-duplicate group: {manifest['largest_near_duplicate_group']} photos")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True, help="The 'data' folder made by fetch_rdd2022.py")
    parser.add_argument("--out", type=Path, required=True, help="A new, empty folder for the prepared dataset")
    args = parser.parse_args(argv)
    manifest = run(args.data, args.out)
    print_summary(manifest)
    print(f"\nSaved {args.out / 'split-manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
