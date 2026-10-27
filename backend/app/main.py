"""FastAPI application entry point.

Run locally (inside Docker this is done for you):
    uvicorn app.main:app --reload
"""

import logging

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.origin_check import origin_check_middleware
from app.core.request_context import request_id_middleware


def create_app() -> FastAPI:
    """Build and configure the application."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        # Interactive API docs only outside production.
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
    )
    # Middleware runs outermost-last: the request ID is assigned first, then the Origin check.
    app.middleware("http")(origin_check_middleware)
    app.middleware("http")(request_id_middleware)
    register_error_handlers(app)
    app.include_router(api_router)
    logging.getLogger("geoinfralens").info(
        "GeoInfraLens API ready (environment=%s, log level=%s, API docs: %s)",
        settings.app_env.value,
        settings.log_level,
        "off in production" if settings.is_production else "/api/docs",
    )
    return app


app = create_app()
