"""Job queue (Valkey) connectivity check."""

import logging
import uuid

import redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def check_queue() -> bool:
    """Return True if Valkey answers PING, False otherwise."""
    settings = get_settings()
    timeout = settings.dependency_check_timeout_seconds
    client = redis.Redis.from_url(
        settings.redis_url, socket_connect_timeout=timeout, socket_timeout=timeout
    )
    try:
        return bool(client.ping())
    except RedisError as exc:
        # One clear line (no traceback): expected while the queue is still starting.
        logger.warning("Queue (Valkey) not reachable: %s", exc)
        return False
    finally:
        client.close()


def send_analysis_job(job_id: uuid.UUID) -> None:
    """Ask the worker to run one analysis job. Raises if the queue cannot be reached."""
    from app.workers.celery_app import celery_app  # imported here: only needed when sending

    celery_app.send_task("analysis.run_job", args=[str(job_id)], retry=False)


def send_report_job(report_id: uuid.UUID) -> None:
    """Ask the worker to build one report. Raises if the queue cannot be reached."""
    from app.workers.celery_app import celery_app  # imported here: only needed when sending

    celery_app.send_task("reports.generate", args=[str(report_id)], retry=False)
