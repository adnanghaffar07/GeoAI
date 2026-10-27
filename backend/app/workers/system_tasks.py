"""System tasks used to confirm the worker is running."""

import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="system.ping")
def ping() -> str:
    """Return "pong". Used to check the worker end to end."""
    logger.info("Worker received ping")
    return "pong"
