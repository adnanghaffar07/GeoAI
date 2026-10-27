"""Reject data-changing requests that come from other websites.

This protects against cross-site request forgery (CSRF): a malicious website making a
signed-in person's browser send a request to our API. Together with the
`SameSite=Lax` session cookie this gives two independent protections.

A request that changes data (POST, PUT, PATCH, DELETE) is refused when the browser says
it came from a different site (`Origin` header not our app address, or
`Sec-Fetch-Site: cross-site`). Requests without those headers (scripts, tests, tools)
are allowed; they cannot carry a victim's browser cookie.
"""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.core.config import get_settings
from app.core.errors import error_response

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def origin_check_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if request.method not in _SAFE_METHODS:
        allowed_origin = get_settings().public_app_url
        origin = request.headers.get("origin")
        fetch_site = request.headers.get("sec-fetch-site")
        if (origin is not None and origin != allowed_origin) or fetch_site == "cross-site":
            return error_response(
                403, "permission_denied", "This request came from another website and was refused."
            )
    return await call_next(request)
