"""Request and response shapes for AI analysis jobs and findings."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

MAX_PHOTOS_PER_REQUEST = 1000


class StartAnalysisRequest(BaseModel):
    """`image_ids` empty/omitted means: every photo in the project not yet analysed."""

    image_ids: list[uuid.UUID] | None = Field(default=None, max_length=MAX_PHOTOS_PER_REQUEST)


class AnalysisJobOut(BaseModel):
    id: uuid.UUID
    image_id: uuid.UUID
    image_filename: str
    model_version: str
    # True for the stand-in: its results are labelled "TEST DETECTOR: not a real detection".
    is_test_detector: bool
    # True for a model that has not passed its accuracy check: labelled "TRIAL MODEL".
    is_trial_model: bool = False
    status: str  # queued / processing / completed / failed
    attempts: int
    failure_reason: str | None
    # Number of AI suggestions. Hidden (null) for people who may not see suggestions.
    candidate_count: int | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class StartAnalysisResult(BaseModel):
    created: int  # new jobs
    reused: int  # photos that already had a job for this model (never duplicated)
    jobs: list[AnalysisJobOut]


class AnalysisJobList(BaseModel):
    items: list[AnalysisJobOut]
    page: int
    page_size: int
    total: int
    status_counts: dict[str, int]
