# ruff: noqa: E501
"""Private file storage for photos and exports (team lead plan, Phase 2: client-controlled, encrypted).

Files are never served directly: only through the API after a permission check.

Where a file lives (bring your own storage, tl-phase2): each organization chooses
- "app": the app's own private folder (STORAGE_DIR), the default;
- "s3": its own S3-type storage (Amazon S3, Wasabi, Backblaze B2, Cloudflare R2, or MinIO on its own computer/server).
Keys look like `org/<org_id>/project/<project_id>/image/<image_id>/original.jpg`; the organization in the key picks
the place. Files saved before a change of place stay readable from the app folder.

Every file is encrypted (AES-256-GCM) before it is saved; the key path is bound to the file, so a file cannot be
swapped for another. Files saved before encryption existed are still read as they are.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, urlsplit

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi.responses import Response

from app.core.config import get_settings

MAGIC = b"GIL1"  # encrypted file: MAGIC + 12-byte nonce + ciphertext (with tag)
_ORG = re.compile(r"^org/([0-9a-f-]{36})/")


class StorageKeyError(ValueError):
    """A key that would point outside the storage folder."""


class StorageUnavailableError(RuntimeError):
    """The organization's own storage did not answer (for example its computer is off)."""


# ------------------------------------------------------------------ the app's own folder


def _root() -> Path:
    root = get_settings().storage_dir
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def path_for(key: str) -> Path:
    """Absolute path in the app folder, refusing anything that escapes it."""
    if not key or key.startswith(("/", "\\")) or ".." in Path(key).parts:
        raise StorageKeyError(f"Invalid storage key: {key!r}")
    root = _root()
    path = (root / key).resolve()
    if root != path and root not in path.parents:
        raise StorageKeyError(f"Invalid storage key: {key!r}")
    return path


def temp_dir() -> Path:
    """Folder for files that are still being received (never encrypted, deleted after use)."""
    path = _root() / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


class Backend(Protocol):
    name: str

    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes | None: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...


class LocalBackend:
    name = "app"

    def put(self, key: str, data: bytes) -> None:
        target = path_for(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".partial")
        partial.write_bytes(data)
        os.replace(partial, target)  # a crash never leaves a half-written file under the real key

    def get(self, key: str) -> bytes | None:
        path = path_for(key)
        return path.read_bytes() if path.is_file() else None

    def exists(self, key: str) -> bool:
        return path_for(key).is_file()

    def delete(self, key: str) -> None:
        path_for(key).unlink(missing_ok=True)


# ------------------------------------------------------------------ S3-type storage (signature version 4)


class S3Backend:
    """Any S3-type storage, signed by hand (AWS signature version 4), so no extra library is needed."""

    name = "s3"

    def __init__(
        self,
        endpoint: str,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
        prefix: str = "",
    ):
        self.endpoint = endpoint.rstrip("/")
        self.bucket, self.region = bucket, region or "us-east-1"
        self.access_key, self.secret_key = access_key, secret_key
        self.prefix = prefix.strip("/")

    def _url(self, key: str) -> str:
        path = f"{self.prefix}/{key}" if self.prefix else key
        return f"{self.endpoint}/{quote(self.bucket)}/{quote(path)}"  # path style: works with every S3-type service

    def _request(self, method: str, key: str, data: bytes = b"") -> requests.Response:
        url = self._url(key)
        parts = urlsplit(url)
        now = datetime.now(UTC)
        amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(data).hexdigest()
        headers = {
            "host": parts.netloc,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        signed = ";".join(sorted(headers))
        canonical = "\n".join(
            [
                method,
                parts.path,
                "",
                "".join(f"{k}:{headers[k]}\n" for k in sorted(headers)),
                signed,
                payload_hash,
            ]
        )
        scope = f"{day}/{self.region}/s3/aws4_request"
        to_sign = "\n".join(
            ["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()]
        )
        key_ = f"AWS4{self.secret_key}".encode()
        for part in (day, self.region, "s3", "aws4_request"):
            key_ = hmac.new(key_, part.encode(), hashlib.sha256).digest()
        signature = hmac.new(key_, to_sign.encode(), hashlib.sha256).hexdigest()
        headers["Authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, SignedHeaders={signed}, Signature={signature}"
        )
        try:
            return requests.request(method, url, data=data or None, headers=headers, timeout=60)
        except requests.RequestException as error:
            raise StorageUnavailableError(
                f"The organization's storage did not answer ({type(error).__name__})."
            ) from error

    def _check(self, answer: requests.Response, allowed: tuple[int, ...]) -> None:
        if answer.status_code not in allowed:
            raise StorageUnavailableError(
                f"The organization's storage refused the request (HTTP {answer.status_code})."
            )

    def put(self, key: str, data: bytes) -> None:
        self._check(self._request("PUT", key, data), (200,))

    def get(self, key: str) -> bytes | None:
        answer = self._request("GET", key)
        if answer.status_code == 404:
            return None
        self._check(answer, (200,))
        return answer.content

    def exists(self, key: str) -> bool:
        answer = self._request("HEAD", key)
        if answer.status_code == 404:
            return False
        self._check(answer, (200,))
        return True

    def delete(self, key: str) -> None:
        self._check(self._request("DELETE", key), (200, 204, 404))


# ------------------------------------------------------------------ which place, per organization

_LOCAL = LocalBackend()
_cache: dict[uuid.UUID, tuple[float, Backend]] = {}
_lock = threading.Lock()
CACHE_SECONDS = 30


def forget_settings(organization_id: uuid.UUID | None = None) -> None:
    """Call after an organization changes its storage settings."""
    with _lock:
        if organization_id is None:
            _cache.clear()
        else:
            _cache.pop(organization_id, None)


def _load_backend(organization_id: uuid.UUID) -> Backend:
    from app.core.database import get_session_factory

    from app.services.data_storage import backend_for  # the settings live in the database

    with get_session_factory()() as db:
        return backend_for(db, organization_id) or _LOCAL


def _backend(key: str) -> Backend:
    match = _ORG.match(key)
    if not match:
        return _LOCAL
    organization_id = uuid.UUID(match.group(1))
    with _lock:
        cached = _cache.get(organization_id)
        if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1]
    backend = _load_backend(organization_id)
    with _lock:
        _cache[organization_id] = (time.monotonic(), backend)
    return backend


# ------------------------------------------------------------------ encryption


def _encryption_key() -> bytes:
    """STORAGE_ENCRYPTION_KEY (.env, base64 of 32 bytes). If it is not set, one is made once and kept next to the
    app folder (fine for the laptop; on a server it must be set in .env and backed up: without it no file opens)."""
    configured = get_settings().storage_encryption_key
    if configured:
        key = base64.b64decode(configured)
    else:
        path = _root() / ".storage-key"
        if not path.exists():
            path.write_text(base64.b64encode(secrets.token_bytes(32)).decode())
            with contextlib.suppress(OSError):
                path.chmod(0o600)
        key = base64.b64decode(path.read_text().strip())
    if len(key) != 32:
        raise RuntimeError("STORAGE_ENCRYPTION_KEY must be 32 bytes (base64).")
    return key


def encrypt(key: str, data: bytes) -> bytes:
    nonce = secrets.token_bytes(12)
    return MAGIC + nonce + AESGCM(_encryption_key()).encrypt(nonce, data, key.encode())


def decrypt(key: str, data: bytes) -> bytes:
    if not data.startswith(MAGIC):
        return data  # saved before encryption existed
    nonce, body = data[len(MAGIC) : len(MAGIC) + 12], data[len(MAGIC) + 12 :]
    return AESGCM(_encryption_key()).decrypt(nonce, body, key.encode())


# ------------------------------------------------------------------ what the rest of the app uses


def save_bytes(key: str, data: bytes) -> None:
    path_for(key)  # same key rules everywhere
    _backend(key).put(key, encrypt(key, data))


def save_file(key: str, source: Path) -> None:
    """Store a finished temporary file under `key`, then remove the temporary file."""
    save_bytes(key, source.read_bytes())
    source.unlink(missing_ok=True)


def read_bytes(key: str) -> bytes | None:
    backend = _backend(key)
    data = backend.get(key)
    if data is None and backend is not _LOCAL:
        data = _LOCAL.get(key)  # saved before the organization moved to its own storage
    return None if data is None else decrypt(key, data)


def exists(key: str) -> bool:
    backend = _backend(key)
    return backend.exists(key) or (backend is not _LOCAL and _LOCAL.exists(key))


def delete(key: str) -> None:
    """Remove a stored file. Only used to clean up files whose database record was never saved; real deletion of
    kept data follows the retention policy (PI-13)."""
    _backend(key).delete(key)
    _LOCAL.delete(key)


@contextlib.contextmanager
def local_copy(key: str) -> Iterator[Path]:
    """A temporary plain file for tools that need a path (the AI detector). Deleted afterwards."""
    data = read_bytes(key)
    if data is None:
        raise FileNotFoundError(key)
    path = temp_dir() / f"{uuid.uuid4().hex}{Path(key).suffix}"
    path.write_bytes(data)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def file_response(
    key: str,
    media_type: str,
    headers: dict[str, str],
    filename: str | None = None,
    inline: bool = True,
) -> Response | None:
    """The file as an HTTP answer (decrypted), or None when it is not there."""
    data = read_bytes(key)
    if data is None:
        return None
    all_headers = dict(headers)
    if filename:
        kind = "inline" if inline else "attachment"
        all_headers["Content-Disposition"] = f"{kind}; filename*=UTF-8''{quote(filename)}"
    return Response(content=data, media_type=media_type, headers=all_headers)


def check_backend(backend: Any) -> None:
    """Write, read and delete a small test file (the "Test connection" button)."""
    key = f"_geoinfralens-check/{uuid.uuid4().hex}.txt"
    backend.put(key, b"ok")
    if backend.get(key) != b"ok":
        raise StorageUnavailableError("The test file could not be read back.")
    backend.delete(key)
