"""Application errors and the standard API error format.

Every error response looks like:

    {"error": {"code": "...", "message": "...", "details": ..., "request_id": "..."}}

Route and service code raises the `AppError` subclasses below. The handlers
registered by `register_error_handlers` turn them (and framework errors) into
that format. Unexpected exceptions are logged with a traceback and returned as
a generic `internal_error`, so internal details never leak to users.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import get_request_id

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for expected, user-facing errors."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    default_message: str = "The request could not be processed."

    def __init__(self, message: str | None = None, *, details: Any = None) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)


class NotAuthenticatedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "not_authenticated"
    default_message = "Please sign in to continue."


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"
    default_message = "You do not have permission to do this."


class NotFoundError(AppError):
    """Also used when a record belongs to another organization, so its existence is not revealed."""

    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    default_message = "The requested item was not found."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    default_message = "This change conflicts with the current data. Reload and try again."


class ValidationFailedError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_error"
    default_message = "Some fields are invalid."


class PayloadTooLargeError(AppError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "payload_too_large"
    default_message = "The file is too large."


class UnsupportedMediaTypeError(AppError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "unsupported_media_type"
    default_message = "This type of file is not supported."


class LinkInvalidError(AppError):
    """An invitation or password-reset link that is expired, used, revoked, or unknown.

    `details.reason` is one of: "expired", "used", "revoked", "invalid".
    """

    status_code = status.HTTP_410_GONE
    code = "link_invalid"
    default_message = "This link is no longer valid."


class TooManyRequestsError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "too_many_requests"
    default_message = "Too many attempts. Please wait a few minutes and try again."


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"
    default_message = "A required service is temporarily unavailable. Try again shortly."


# Maps framework HTTP status codes to our stable error codes.
_STATUS_TO_CODE: dict[int, str] = {
    400: "bad_request",
    401: "not_authenticated",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "too_many_requests",
    503: "service_unavailable",
}


def error_response(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    """Build a JSON response in the standard error format."""
    request_id = get_request_id()
    body = {
        "error": {
            "code": code,
            "message": message,
            "details": jsonable_encoder(details),
            "request_id": request_id,
        }
    }
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(status_code=status_code, content=body, headers=headers)


async def _handle_app_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    if exc.status_code >= 500:
        logger.warning("%s: %s", exc.code, exc.message)
    else:
        # Expected refusals (no permission, bad input, ...): say why, without any user data.
        logger.info("Refused (%s %s): %s", exc.status_code, exc.code, exc.message)
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


async def _handle_validation_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    fields = [
        {
            "field": ".".join(str(part) for part in err.get("loc", ())),
            "message": err.get("msg", "Invalid value."),
        }
        for err in exc.errors()
    ]
    field_names = ", ".join(str(f["field"]) for f in fields)
    logger.info("Refused (422 validation_error): check fields %s", field_names)
    return error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "validation_error",
        ValidationFailedError.default_message,
        {"fields": fields},
    )


async def _handle_http_exception(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _STATUS_TO_CODE.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else "The request failed."
    return error_response(exc.status_code, code, message)


async def _handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
    # The one place where a broad catch is correct: log everything, reveal nothing.
    logger.exception("Unhandled error", exc_info=exc)
    return error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        "Something went wrong on our side. Please try again; if it continues, "
        "contact support with the request ID.",
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach all error handlers to the FastAPI app."""
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected_error)
