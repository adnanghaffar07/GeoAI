"""Private file storage for photos and exports.

Files live in a private folder (`STORAGE_DIR`) that is never served directly by a web
server: they are only sent through the API after a permission check.

This is the only module that touches the storage folder. Moving to S3-compatible
object storage later means rewriting only these functions (tech-stack.md).

Keys look like `org/<org_id>/project/<project_id>/image/<image_id>/original.jpg`.
"""

import os
import shutil
from pathlib import Path

from app.core.config import get_settings


class StorageKeyError(ValueError):
    """A key that would point outside the storage folder."""


def _root() -> Path:
    root = get_settings().storage_dir
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def path_for(key: str) -> Path:
    """Absolute path for a key, refusing anything that escapes the storage folder."""
    if not key or key.startswith(("/", "\\")) or ".." in Path(key).parts:
        raise StorageKeyError(f"Invalid storage key: {key!r}")
    root = _root()
    path = (root / key).resolve()
    if root != path and root not in path.parents:
        raise StorageKeyError(f"Invalid storage key: {key!r}")
    return path


def temp_dir() -> Path:
    """Folder for files that are still being received (same disk, so moves are instant)."""
    path = _root() / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_file(key: str, source: Path) -> None:
    """Move a finished temporary file into storage under `key` (atomic on one disk)."""
    target = path_for(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))


def save_bytes(key: str, data: bytes) -> None:
    """Write bytes under `key`. Written to a temporary name first, so a crash never
    leaves a half-written file under the real key."""
    target = path_for(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".partial")
    partial.write_bytes(data)
    os.replace(partial, target)


def exists(key: str) -> bool:
    return path_for(key).is_file()


def delete(key: str) -> None:
    """Remove a stored file. Only used to clean up files whose database record was never
    saved; real deletion of kept data follows the retention policy (PI-13)."""
    path_for(key).unlink(missing_ok=True)
