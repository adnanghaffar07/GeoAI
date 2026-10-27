"""Per-request context: a request ID shared by logs and error responses.

Each request gets an ID (taken from a valid incoming `X-Request-ID` header, or
newly generated). It is returned in the `X-Request-ID` response header, included
in error bodies, and added to every log line written while handling the request.
"""

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from fastapi import Request, Response

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
http_log = logging.getLogger("geoinfralens.http")

# One-time links carry a secret in the address; never print it.
_SECRET_IN_PATH = re.compile(r"(/auth/(?:invitations|password-resets)/)[^/]+")

# Accept only simple IDs from clients, so log lines cannot be forged or polluted.
_VALID_INCOMING_ID = re.compile(r"^[A-Za-z0-9\-]{8,64}$")


def get_request_id() -> str | None:
    """Return the current request's ID, or None outside a request."""
    return _request_id.get()


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Assign a request ID, expose it on the response, and reset it afterwards."""
    incoming = request.headers.get("X-Request-ID", "")
    request_id = incoming if _VALID_INCOMING_ID.match(incoming) else uuid.uuid4().hex
    token = _request_id.set(request_id)
    started = time.perf_counter()
    path = _SECRET_IN_PATH.sub(r"\1***", request.url.path)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        _log_request(request.method, path, response.status_code, started)
        return response
    except Exception:
        _log_request(request.method, path, 500, started)
        raise
    finally:
        _request_id.reset(token)


def _log_request(method: str, path: str, status_code: int, started: float) -> None:
    """One line per request, e.g. 'POST /api/v1/auth/login -> 200 (85 ms)'.

    Health checks are frequent and only shown at DEBUG level; failures stand out as warnings.
    """
    elapsed_ms = (time.perf_counter() - started) * 1000
    if status_code >= 500:
        level = logging.ERROR
    elif status_code == 401:
        level = logging.INFO  # "not signed in" is normal, e.g. when the app first opens
    elif status_code >= 400:
        level = logging.WARNING
    elif path.startswith("/api/health"):
        level = logging.DEBUG
    else:
        level = logging.INFO
    http_log.log(level, "%s %s -> %s (%.0f ms)", method, path, status_code, elapsed_ms)
