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
        forecasting.setup(db, uuid.UUID(settings_id))


@celery_app.task(name=TICK_TASK)
def tick() -> dict[str, Any]:
    with get_session_factory()() as db:
        return forecasting.tick(db)
