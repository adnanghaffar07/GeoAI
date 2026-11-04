"""Security headers on every API answer (P9 hardening, 2026-11-03).

- nosniff: browsers never guess a file type (an uploaded file can't run as a script).
- DENY: the app can't be shown inside another site's frame (no click-jacking).
- no referrer to other sites; no camera or microphone; location only for the app itself.
- API answers are not stored by browsers or proxies (they hold private data). Downloads that set
  their own Cache-Control (photos, evidence) keep it.
"""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response

HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(self)",
    "Cross-Origin-Opener-Policy": "same-origin",
}


async def security_headers_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    for name, value in HEADERS.items():
        response.headers.setdefault(name, value)
    if request.url.path.startswith("/api/") and "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"
    return response
