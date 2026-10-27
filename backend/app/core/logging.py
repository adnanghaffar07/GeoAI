"""Logging setup: one consistent format, with the request ID on every line."""

import logging

from app.core.request_context import get_request_id

_HANDLER_NAME = "geoinfralens-console"
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [request_id=%(request_id)s] %(message)s"


class _RequestIdFilter(logging.Filter):
    """Adds `request_id` to each log record ("-" outside a request)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


def configure_logging(level: str) -> None:
    """Configure the root logger. Safe to call more than once."""
    handler = logging.StreamHandler()
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    handler.addFilter(_RequestIdFilter())

    root = logging.getLogger()
    # Replace only our own handler, so other listeners (e.g. test log capture) keep working.
    for existing in [h for h in root.handlers if h.get_name() == _HANDLER_NAME]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)
