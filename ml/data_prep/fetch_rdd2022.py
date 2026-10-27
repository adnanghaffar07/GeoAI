"""P8.1: download RDD2022, check it, unpack it WITHOUT the United States part, and count what is inside.

Runs on Google Colab (the dataset is 13.3 GB). Plan: documentation/04-design/ml-baseline-plan.md.

    python fetch_rdd2022.py --out /content/rdd2022

Steps:
1. Download the official zip from figshare (resumes if interrupted).
2. Check its size and MD5 fingerprint against the values figshare publishes, so a broken or
   changed file is never used.
3. Unpack it. Anything under a "United_States" folder is skipped and never written to disk:
   those photos are Google Street View images, and Google's terms forbid using them to train
   or test AI models (plan section 6). Zips inside the zip are handled the same way.
4. Count images, label files and boxes per country and per damage code, and save the counts
   to inventory.json (used to fill in the dataset card).

The dataset is outside data, so the label files are read with defusedxml (safe against
malicious XML), and every path inside the zip is checked before anything is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from defusedxml import ElementTree

# Official record: https://figshare.com/articles/dataset/21431547 (CC BY 4.0), checked 2026-10-16.
DATASET_URL = "https://ndownloader.figshare.com/files/38030910"
DATASET_FILE = "RDD2022_released_through_CRDDC2022.zip"
DATASET_SIZE = 13_264_172_619
DATASET_MD5 = "b62bd51d2ffcfaa76c60f234f0cc2bb3"

# Never used, in any form (plan section 6).
EXCLUDED = re.compile(r"united[\s_-]*states", re.IGNORECASE)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
CHUNK = 8 * 1024 * 1024
# The download site sometimes refuses or drops big downloads for a while (e.g. "403 Forbidden"
# from busy shared Colab addresses). Wait and try again, continuing the partial file.
RETRY_WAITS_SECONDS = (30, 90, 180, 300)
RETRY_STATUS = {403, 408, 429, 500, 502, 503, 504}
USER_AGENT = "GeoInfraLens-dataset-fetch/1.0 (one-time research download of RDD2022)"


class DatasetError(Exception):
    """A problem that must stop the run (wrong file, unsafe content)."""


# ---------------------------------------------------------------- download and check


def download(url: str, dest: Path, expected_size: int) -> None:
    """Download `url` to `dest`, continuing a partial file, and retrying when the site refuses for a while."""
    if not url.startswith(("https://", "http://127.0.0.1")):  # the official https URL (local address only in tests)
        raise DatasetError(f"Refusing to download from {url!r}")
    for attempt, wait in enumerate((*RETRY_WAITS_SECONDS, None), start=1):
        try:
            _download_once(url, dest, expected_size)
            return
        except urllib.error.HTTPError as error:
            if error.code not in RETRY_STATUS:
                raise DatasetError(f"The download site answered {error.code} {error.reason}.") from error
            problem = f"the download site answered {error.code} {error.reason}"
        except (urllib.error.URLError, ConnectionError, TimeoutError) as error:
            problem = f"the connection failed ({error})"
        if wait is None:
            raise DatasetError(
                f"Gave up after {attempt} tries: {problem}. The site may be limiting downloads for a while. "
                "Wait 15-30 minutes and run this cell again (it continues where it stopped), or in Colab use "
                "Runtime > Disconnect and delete runtime, then run all cells again (you get a new internet address)."
            )
        print(f"  Try {attempt} failed: {problem}. Waiting {wait} seconds, then continuing...")
        time.sleep(wait)


def _download_once(url: str, dest: Path, expected_size: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    have = dest.stat().st_size if dest.exists() else 0
    if have == expected_size:
        print(f"Already downloaded: {dest}")
        return
    if have > expected_size:
        raise DatasetError(f"{dest} is larger than expected; delete it and run again.")
    headers = {"User-Agent": USER_AGENT}
    if have:
        headers["Range"] = f"bytes={have}-"
    request = urllib.request.Request(url, headers=headers)  # noqa: S310 (scheme checked in download)
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (scheme checked in download)
        if have and response.status != 206:
            have = 0  # server ignored the resume request: start again
        mode = "ab" if have else "wb"
        done, next_report, started = have, have, time.monotonic()
        with dest.open(mode) as handle:
            while chunk := response.read(CHUNK):
                handle.write(chunk)
                done += len(chunk)
                if done >= next_report:
                    speed = (done - have) / max(time.monotonic() - started, 0.001) / 1e6
                    print(f"  {done / expected_size:6.1%}  ({done / 1e9:.2f} of {expected_size / 1e9:.2f} GB, {speed:.0f} MB/s)")
                    next_report = done + expected_size // 20
    if dest.stat().st_size != expected_size:
        raise ConnectionError(f"download stopped early ({dest.stat().st_size} of {expected_size} bytes)")


def check_md5(path: Path, expected: str) -> None:
    digest = hashlib.md5()  # noqa: S324 (file fingerprint published by figshare, not security)
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise DatasetError(
            f"MD5 mismatch for {path.name}: got {digest.hexdigest()}, expected {expected}. "
            "The file is damaged or not the official one; delete it and download again."
        )
    print(f"MD5 OK: {expected}")


# ---------------------------------------------------------------- unpack without the US part


def safe_relative_path(name: str) -> PurePosixPath:
    """The path of a zip entry, refusing anything that could write outside the output folder."""
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or (path.parts and ":" in path.parts[0]):
        raise DatasetError(f"Unsafe path inside the zip: {name!r}")
    return path


def is_excluded(path: PurePosixPath) -> bool:
    return any(EXCLUDED.search(part) for part in path.parts)


def extract(zip_path: Path, out_dir: Path, report: Counter[str], prefix: PurePosixPath | None = None) -> None:
    """Unpack `zip_path` into `out_dir`, skipping excluded parts. Zips inside are unpacked in place."""
    prefix = prefix or PurePosixPath()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            relative = prefix / safe_relative_path(member.filename)
            if is_excluded(relative):
                report["skipped_excluded"] += 1
                continue
            if member.is_dir():
                continue
            if relative.suffix.lower() == ".zip":
                # Unpack the inner zip into a folder named after it (without ".zip").
                with tempfile.TemporaryDirectory() as tmp:
                    inner = Path(tmp) / relative.name
                    with archive.open(member) as source, inner.open("wb") as target:
                        shutil.copyfileobj(source, target, CHUNK)
                    report["inner_zips"] += 1
                    extract(inner, out_dir, report, relative.parent / relative.stem)
                continue
            target = out_dir.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as handle:
                shutil.copyfileobj(source, handle, CHUNK)
            report["files_written"] += 1


# ---------------------------------------------------------------- count what is inside


def country_and_split(path: PurePosixPath) -> tuple[str, str]:
    """Country folder and split, from paths like <...>/Japan/train/images/x.jpg."""
    parts = [part.lower() for part in path.parts]
    for index, part in enumerate(parts):
        if part in {"train", "test"} and index > 0:
            return path.parts[index - 1], part
    return "unknown", "unknown"


def read_labels(xml_path: Path) -> tuple[list[str], tuple[int, int] | None]:
    """Box label names and the image size from one Pascal VOC label file."""
    root = ElementTree.parse(xml_path).getroot()
    names = [(obj.findtext("name") or "").strip() for obj in root.iter("object")]
    width, height = root.findtext("size/width"), root.findtext("size/height")
    size = (int(float(width)), int(float(height))) if width and height else None
    return names, size


def build_inventory(out_dir: Path) -> dict[str, Any]:
    countries: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"images": Counter(), "label_files": 0, "boxes": Counter(), "images_without_boxes": 0, "image_sizes": Counter()}
    )
    problems: list[str] = []
    for file in sorted(out_dir.rglob("*")):
        if not file.is_file():
            continue
        relative = PurePosixPath(file.relative_to(out_dir).as_posix())
        if is_excluded(relative):
            raise DatasetError(f"Excluded data found on disk: {relative}. Delete it before continuing.")
        country, split = country_and_split(relative)
        entry = countries[country]
        suffix = file.suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            entry["images"][split] += 1
        elif suffix == ".xml":
            entry["label_files"] += 1
            try:
                names, size = read_labels(file)
            except Exception as error:  # noqa: BLE001 (report every broken file, keep counting)
                problems.append(f"{relative}: {error}")
                continue
            entry["boxes"].update(names)
            if not names:
                entry["images_without_boxes"] += 1
            if size:
                entry["image_sizes"][f"{size[0]}x{size[1]}"] += 1
    result = {
        name: {
            "images": dict(data["images"]),
            "label_files": data["label_files"],
            "images_without_boxes": data["images_without_boxes"],
            "boxes_by_label": dict(sorted(data["boxes"].items())),
            "common_image_sizes": dict(data["image_sizes"].most_common(3)),
        }
        for name, data in sorted(countries.items())
    }
    return {"countries": result, "unreadable_label_files": problems[:50], "unreadable_label_file_count": len(problems)}


def print_summary(inventory: dict[str, Any]) -> None:
    labels = sorted({label for data in inventory["countries"].values() for label in data["boxes_by_label"]})
    print("\nCountry            train img  test img  " + "  ".join(f"{label:>6}" for label in labels))
    for name, data in inventory["countries"].items():
        boxes = "  ".join(f"{data['boxes_by_label'].get(label, 0):>6}" for label in labels)
        print(f"{name:<18} {data['images'].get('train', 0):>9}  {data['images'].get('test', 0):>8}  {boxes}")
    if inventory["unreadable_label_file_count"]:
        print(f"\n{inventory['unreadable_label_file_count']} label files could not be read (listed in inventory.json).")


# ---------------------------------------------------------------- command line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="Folder for the zip, the unpacked data and inventory.json")
    parser.add_argument("--keep-zip", action="store_true", help="Keep the 13 GB zip after unpacking (default: delete it to save disk)")
    args = parser.parse_args(argv)

    zip_path = args.out / DATASET_FILE
    data_dir = args.out / "data"
    try:
        print(f"1/4 Downloading {DATASET_FILE} ({DATASET_SIZE / 1e9:.1f} GB)")
        download(DATASET_URL, zip_path, DATASET_SIZE)
        print("2/4 Checking the file fingerprint (MD5)")
        check_md5(zip_path, DATASET_MD5)
        print("3/4 Unpacking (United States part skipped)")
        if data_dir.exists():
            shutil.rmtree(data_dir)  # always unpack fresh, so nothing excluded or stale survives
        report: Counter[str] = Counter()
        extract(zip_path, data_dir, report)
        print(
            f"   files written: {report['files_written']}, inner zips: {report['inner_zips']}, "
            f"US entries skipped: {report['skipped_excluded']}"
        )
        if not args.keep_zip:
            zip_path.unlink()
        print("4/4 Counting images and boxes")
        inventory = build_inventory(data_dir)
        inventory["source"] = {
            "url": DATASET_URL,
            "file": DATASET_FILE,
            "bytes": DATASET_SIZE,
            "md5": DATASET_MD5,
            "licence": "CC BY 4.0 (figshare record); authors' GitHub states CC BY-SA 4.0",
        }
        inventory["unpack_report"] = dict(report)
        inventory["created_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (args.out / "inventory.json").write_text(json.dumps(inventory, indent=2))
        print_summary(inventory)
        print(f"\nSaved {args.out / 'inventory.json'}")
    except DatasetError as error:
        print(f"STOPPED: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
