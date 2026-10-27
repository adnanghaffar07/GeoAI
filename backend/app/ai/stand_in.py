"""The test detector ("stand-in"), used until a real model passes its accuracy check (PI-17).

It does NOT look for real problems. It returns 0-2 made-up candidates, chosen from the
photo's fingerprint, so the same photo always gives the same answer (repeatable tests).
Everything it produces is labelled "TEST DETECTOR: not a real detection" on screen.
"""

import hashlib
import random
import time
from pathlib import Path
from typing import Any

from PIL import Image as PillowImage

MODEL_VERSION = "stand-in-0.1"
CLASSES: tuple[str, ...] = ("pothole", "surface_cracking", "pavement_deterioration")


def detect(photo_path: Path, *, image_id: str) -> dict[str, Any]:
    """Return a contract v1 note for one photo."""
    started = time.perf_counter()
    data = photo_path.read_bytes()
    with PillowImage.open(photo_path) as photo:
        width, height = photo.size
    rng = random.Random(hashlib.sha256(data).hexdigest())  # noqa: S311 (test data, not security)

    candidates = []
    for index in range(rng.randint(0, 2)):
        box_w = max(1, int(width * rng.uniform(0.12, 0.35)))
        box_h = max(1, int(height * rng.uniform(0.10, 0.30)))
        left = rng.randint(0, width - box_w)
        lowest_top = min(int(height * 0.35), height - box_h)  # road is usually the lower part
        top = rng.randint(lowest_top, height - box_h)
        candidates.append(
            {
                "detection_index": index,
                "class_key": rng.choice(CLASSES),
                "confidence": round(rng.uniform(0.30, 0.95), 2),
                "bbox_px": [left, top, left + box_w, top + box_h],
            }
        )

    return {
        "contract_version": 1,
        "model_version": MODEL_VERSION,
        "image_id": image_id,
        "status": "ok",
        "failure_reason": None,
        "image_width_px": width,
        "image_height_px": height,
        "candidates": candidates,
        "processing_ms": int((time.perf_counter() - started) * 1000),
    }
