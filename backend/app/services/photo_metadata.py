"""Reading information out of a photo: format, size, capture time, GPS, and quality.

Pure functions (no database), so they are easy to test with small generated photos.

Rules from the spec:
- Photo GPS is where the **camera** was: an approximate observation point.
- Missing or broken GPS is flagged, never guessed.
- Quality checks (blur, darkness) give a reason; they cannot prove a defect is visible.
"""

import io
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image as PILImage
from PIL import ImageOps, UnidentifiedImageError

from app.models.image import (
    FLAG_BLURRY,
    FLAG_CAPTURE_TIME_NO_TIMEZONE,
    FLAG_INVALID_GPS,
    FLAG_NO_CAPTURE_TIME,
    FLAG_TOO_DARK,
)

SUPPORTED_FORMATS = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png")}

# Refuse absurdly large images (a "decompression bomb" can exhaust memory).
PILImage.MAX_IMAGE_PIXELS = 120_000_000

# EXIF tag numbers
_GPS_IFD = 0x8825
_EXIF_IFD = 0x8769
_TAG_DATETIME = 0x0132
_TAG_DATETIME_ORIGINAL = 0x9003
_TAG_OFFSET_TIME_ORIGINAL = 0x9011
_GPS_LAT_REF, _GPS_LAT, _GPS_LON_REF, _GPS_LON = 1, 2, 3, 4

# Quality checks run on a smaller copy, so results do not depend on camera resolution.
_ANALYSIS_MAX_PX = 1024


class NotAPhotoError(ValueError):
    """The file is not a readable JPEG or PNG photo."""


@dataclass
class PhotoInfo:
    content_type: str
    extension: str
    width_px: int
    height_px: int
    captured_at: datetime | None
    latitude: float | None
    longitude: float | None
    quality_flags: list[str] = field(default_factory=list)


def _to_degrees(value: object) -> float:
    """EXIF stores coordinates as (degrees, minutes, seconds) fractions."""
    degrees, minutes, seconds = (float(part) for part in value)  # type: ignore[attr-defined]
    return degrees + minutes / 60 + seconds / 3600


def _read_gps(exif: PILImage.Exif) -> tuple[float | None, float | None, bool]:
    """Return (latitude, longitude, invalid). Missing GPS gives (None, None, False)."""
    gps = exif.get_ifd(_GPS_IFD)
    if not gps or _GPS_LAT not in gps or _GPS_LON not in gps:
        return None, None, False
    try:
        latitude = _to_degrees(gps[_GPS_LAT])
        longitude = _to_degrees(gps[_GPS_LON])
    except (TypeError, ValueError, ZeroDivisionError):
        return None, None, True
    if str(gps.get(_GPS_LAT_REF, "N")).upper().startswith("S"):
        latitude = -latitude
    if str(gps.get(_GPS_LON_REF, "E")).upper().startswith("W"):
        longitude = -longitude
    out_of_range = not (-90 <= latitude <= 90 and -180 <= longitude <= 180)
    # (0, 0) is what many cameras write when they have no fix.
    null_island = abs(latitude) < 1e-6 and abs(longitude) < 1e-6
    if out_of_range or null_island:
        return None, None, True
    return latitude, longitude, False


def _read_capture_time(exif: PILImage.Exif) -> tuple[datetime | None, list[str]]:
    """Camera time. Without a time-zone offset in the photo, it is stored as if UTC and
    flagged, rather than guessing the zone."""
    exif_ifd = exif.get_ifd(_EXIF_IFD)
    raw = exif_ifd.get(_TAG_DATETIME_ORIGINAL) or exif.get(_TAG_DATETIME)
    if not raw:
        return None, [FLAG_NO_CAPTURE_TIME]
    try:
        naive = datetime.strptime(str(raw).strip("\x00 "), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None, [FLAG_NO_CAPTURE_TIME]
    offset = exif_ifd.get(_TAG_OFFSET_TIME_ORIGINAL)
    if offset:
        try:
            sign = -1 if str(offset).startswith("-") else 1
            hours, minutes = str(offset).lstrip("+-").split(":")
            zone = timezone(sign * timedelta(hours=int(hours), minutes=int(minutes)))
            return naive.replace(tzinfo=zone), []
        except ValueError:
            pass
    return naive.replace(tzinfo=UTC), [FLAG_CAPTURE_TIME_NO_TIMEZONE]


def _quality_flags(
    image: PILImage.Image, blur_threshold: float, darkness_threshold: float
) -> list[str]:
    small = image.copy()
    small.thumbnail((_ANALYSIS_MAX_PX, _ANALYSIS_MAX_PX))
    gray = np.asarray(small.convert("L"), dtype=np.uint8)
    flags = []
    if float(cv2.Laplacian(gray, cv2.CV_64F).var()) < blur_threshold:
        flags.append(FLAG_BLURRY)
    if float(gray.mean()) < darkness_threshold:
        flags.append(FLAG_TOO_DARK)
    return flags


def read_photo(path: Path, *, blur_threshold: float, darkness_threshold: float) -> PhotoInfo:
    """Read everything we need from a photo file.

    Raises:
        NotAPhotoError: not a JPEG/PNG, damaged, or too large to open safely.
    """
    try:
        with PILImage.open(path) as image:
            fmt = image.format or ""
            if fmt not in SUPPORTED_FORMATS:
                raise NotAPhotoError(
                    f"Only JPEG and PNG photos are supported (this is {fmt or 'unknown'})."
                )
            image.load()  # fully decode now, so damaged files fail here
            exif = image.getexif()
            latitude, longitude, gps_invalid = _read_gps(exif)
            captured_at, time_flags = _read_capture_time(exif)
            upright = ImageOps.exif_transpose(image)
            flags = _quality_flags(upright, blur_threshold, darkness_threshold) + time_flags
            if gps_invalid:
                flags.append(FLAG_INVALID_GPS)
            content_type, extension = SUPPORTED_FORMATS[fmt]
            width, height = upright.size
    except NotAPhotoError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, PILImage.DecompressionBombError) as exc:
        raise NotAPhotoError("The file could not be read as a photo. It may be damaged.") from exc
    return PhotoInfo(
        content_type=content_type,
        extension=extension,
        width_px=width,
        height_px=height,
        captured_at=captured_at,
        latitude=latitude,
        longitude=longitude,
        quality_flags=flags,
    )


def make_preview(path: Path, max_px: int) -> bytes:
    """A smaller, upright JPEG for screens. The original file is never changed."""
    with PILImage.open(path) as image:
        upright = ImageOps.exif_transpose(image).convert("RGB")
        upright.thumbnail((max_px, max_px))
        buffer = io.BytesIO()
        upright.save(buffer, format="JPEG", quality=82)
        return buffer.getvalue()
