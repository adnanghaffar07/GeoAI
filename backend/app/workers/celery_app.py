"""Celery application.

Start a worker:
    celery -A app.workers.celery_app worker --loglevel=INFO

Rule: PostgreSQL is the source of truth for job status. Celery only runs the
work, so no result backend is configured.
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings
from app.core.logging import configure_logging

_settings = get_settings()
configure_logging(_settings.log_level)

# Every task module must be listed in `include` so the worker registers it.
celery_app = Celery(
    "geoinfralens",
    broker=_settings.redis_url,
    include=[
        "app.workers.system_tasks",
        "app.workers.analysis_tasks",
        "app.workers.report_tasks",
        "app.workers.forecast_tasks",
    ],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    # Acknowledge a task only after it finishes, so a crashed worker's task is retried.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    # Fail fast when the queue is down while the API hands over a job (the job is then
    # marked failed with a plain reason and can be retried).
    broker_connection_timeout=_settings.dependency_check_timeout_seconds,
    timezone="UTC",
    # Road-risk forecasting (F4b): one hourly check; each part runs when it is due (daily 06:00,
    # weekly Monday 07:00, Chicago time), so time missed while the computer was off is caught up.
    # Needs the `beat` container.
    beat_schedule={
        "forecast-tick": {"task": "forecast.tick", "schedule": crontab(minute=5)},
    },
)
