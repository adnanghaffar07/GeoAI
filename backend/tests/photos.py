"""Generated test photos (no real photos are stored in the repository)."""

import io
from typing import Any

import numpy as np
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

# A small square survey area in San Francisco used by the project tests.
AREA: dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [
        [[-122.43, 37.77], [-122.41, 37.77], [-122.41, 37.79], [-122.43, 37.79], [-122.43, 37.77]]
    ],
}
INSIDE = (37.775, -122.42)  # (latitude, longitude)
OUTSIDE = (40.71, -74.0)  # New York


def _dms(value: float) -> tuple[IFDRational, IFDRational, IFDRational]:
    value = abs(value)
    degrees = int(value)
    minutes = int((value - degrees) * 60)
    seconds = round(((value - degrees) * 60 - minutes) * 60, 4)
    return IFDRational(degrees), IFDRational(minutes), IFDRational(seconds)


def make_photo(
    *,
    gps: tuple[float, float] | None = None,
    taken: str | None = "2026:10:01 10:00:00",
    offset: str | None = None,
    kind: str = "sharp",
    fmt: str = "JPEG",
    seed: int = 1,
    size: tuple[int, int] = (400, 300),
) -> bytes:
    """A photo with optional GPS and capture time.

    kind: "sharp" (random detail), "blurry" (flat grey), or "dark" (detail, very dim).
    Different seeds give different files (different fingerprints).
    """
    rng = np.random.default_rng(seed)
    width, height = size
    if kind == "blurry":
        pixels = np.full((height, width, 3), 128, dtype=np.uint8)
        pixels[0, 0] = seed % 255  # keep files distinct
    elif kind == "dark":
        pixels = (rng.random((height, width, 3)) * 25).astype(np.uint8)
    else:
        pixels = (rng.random((height, width, 3)) * 255).astype(np.uint8)
    image = Image.fromarray(pixels)
    exif = Image.Exif()
    if gps is not None:
        latitude, longitude = gps
        exif.get_ifd(0x8825).update(
            {
                1: "N" if latitude >= 0 else "S",
                2: _dms(latitude),
                3: "E" if longitude >= 0 else "W",
                4: _dms(longitude),
            }
        )
    if taken:
        exif.get_ifd(0x8769)[0x9003] = taken
        if offset:
            exif.get_ifd(0x8769)[0x9011] = offset
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, exif=exif)
    return buffer.getvalue()
