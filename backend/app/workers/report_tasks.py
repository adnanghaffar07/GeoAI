"""Background task that builds one report (FR-45). Running it twice is safe."""

import uuid

from app.core.database import get_session_factory
from app.services import reports
from app.workers.celery_app import celery_app

TASK_NAME = "reports.generate"


@celery_app.task(name=TASK_NAME)
def generate_report(report_id: str) -> None:
    with get_session_factory()() as db:
        reports.build(db, uuid.UUID(report_id))
