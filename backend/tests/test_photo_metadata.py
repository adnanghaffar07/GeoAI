"""Reading GPS, capture time, and quality from photos (no database needed)."""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.photo_metadata import NotAPhotoError, PhotoInfo, read_photo
from tests.photos import make_photo


def _read(tmp_path: Path, data: bytes) -> PhotoInfo:
    path = tmp_path / "photo"
    path.write_bytes(data)
    return read_photo(path, blur_threshold=100.0, darkness_threshold=40.0)


def test_reads_gps_with_south_and_west_as_negative(tmp_path: Path) -> None:
    info = _read(tmp_path, make_photo(gps=(-33.8568, -70.6483)))

    assert info.latitude == pytest.approx(-33.8568, abs=1e-4)
    assert info.longitude == pytest.approx(-70.6483, abs=1e-4)
    assert info.quality_flags == ["capture_time_no_timezone"]


def test_zero_zero_gps_is_treated_as_invalid_not_as_a_location(tmp_path: Path) -> None:
    info = _read(tmp_path, make_photo(gps=(0.0, 0.0)))

    assert info.latitude is None and info.longitude is None
    assert "invalid_gps" in info.quality_flags


def test_capture_time_uses_offset_when_the_photo_has_one(tmp_path: Path) -> None:
    info = _read(tmp_path, make_photo(offset="-07:00"))

    expected = datetime(2026, 10, 1, 10, 0, tzinfo=timezone(timedelta(hours=-7)))
    assert info.captured_at == expected
    assert "capture_time_no_timezone" not in info.quality_flags


def test_missing_capture_time_is_flagged(tmp_path: Path) -> None:
    info = _read(tmp_path, make_photo(taken=None))

    assert info.captured_at is None
    assert "no_capture_time" in info.quality_flags


def test_capture_time_without_offset_is_stored_as_utc_and_flagged(tmp_path: Path) -> None:
    info = _read(tmp_path, make_photo())

    assert info.captured_at == datetime(2026, 10, 1, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize(("kind", "flag"), [("blurry", "blurry"), ("dark", "too_dark")])
def test_quality_flags(tmp_path: Path, kind: str, flag: str) -> None:
    info = _read(tmp_path, make_photo(kind=kind))

    assert flag in info.quality_flags


def test_png_is_supported(tmp_path: Path) -> None:
    info = _read(tmp_path, make_photo(fmt="PNG", taken=None))

    assert info.content_type == "image/png"


@pytest.mark.parametrize(
    "data",
    [b"just some text", b"\xff\xd8\xff\xe0broken jpeg", make_photo(fmt="GIF", taken=None)],
)
def test_non_photos_are_refused(tmp_path: Path, data: bytes) -> None:
    with pytest.raises(NotAPhotoError):
        _read(tmp_path, data)
