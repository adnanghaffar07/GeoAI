"""Background tasks for road-risk forecasting (F4b). Celery Beat runs `forecast.tick` every hour."""

import uuid
from typing import Any

from app.core.database import get_session_factory
from app.services import forecasting
from app.workers.celery_app import celery_app

SETUP_TASK = "forecast.setup_area"
TICK_TASK = "forecast.tick"


@celery_app.task(name=SETUP_TASK)
def setup_area(settings_id: str) -> None:
    with get_session_factory()() as db:
        row = forecasting.setup(db, uuid.UUID(settings_id))
        if row.status == "ready":
            # Work out the first results now instead of waiting for the next hourly check, so the
            # Road risk page fills in a few minutes after set-up (owner feedback 2026-11-04).
            forecasting.tick(db)


@celery_app.task(name=TICK_TASK)
def tick() -> dict[str, Any]:
    with get_session_factory()() as db:
        return forecasting.tick(db)
