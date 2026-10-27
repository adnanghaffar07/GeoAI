"""Background task that runs one AI analysis job (FR-19).

The task only receives the job ID; everything else (photo, model version, status) is
read from PostgreSQL, which is the source of truth. Running the same job twice is safe.
"""

import uuid

from app.core.database import get_session_factory
from app.services import analysis
from app.workers.celery_app import celery_app

TASK_NAME = "analysis.run_job"


@celery_app.task(name=TASK_NAME)
def run_analysis_job(job_id: str) -> None:
    with get_session_factory()() as db:
        analysis.run_job(db, uuid.UUID(job_id))
