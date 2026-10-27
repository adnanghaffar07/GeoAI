"""Request and response shapes for findings, review and manual observations (P5-P6)."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.images import LatLon

MAX_NOTES = 2000


class FindingPhoto(BaseModel):
    id: uuid.UUID
    original_filename: str
    width_px: int
    height_px: int


class FindingOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    origin: str  # ai / manual
    review_status: str
    inspection_status: str
    # The AI's original answer (never changed). Confidence is an AI score, NOT severity.
    predicted_type_key: str | None
    predicted_confidence: float | None
    predicted_bbox: list[int] | None
    model_version: str | None
    is_test_detector: bool
    is_trial_model: bool = False  # "TRIAL MODEL: accuracy not approved"
    analysis_job_id: uuid.UUID | None
    # The reviewer's version (or the type chosen by the person who added a manual finding).
    type_key: str | None
    severity_key: str | None
    severity_rubric_id: uuid.UUID | None
    severity_rubric_version: int | None
    notes: str | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    created_by_name: str | None
    # `location` is the one to show: the reviewer's corrected point if set, otherwise the
    # original. Both are also given separately; the original is never changed.
    location: LatLon | None
    original_location: LatLon | None
    corrected_location: LatLon | None
    location_source: str
    location_quality: str
    photo: FindingPhoto | None
    version: int
    created_at: datetime
    updated_at: datetime


class FindingFilters(BaseModel):
    """Filters shared by the list and the map, so both always show the same findings."""

    review_status: list[str] = Field(default_factory=list)
    type_key: list[str] = Field(default_factory=list)
    severity_key: list[str] = Field(default_factory=list)
    created_from: date | None = None
    created_to: date | None = None
    has_location: bool | None = None
    include_rejected: bool = False
    image_id: uuid.UUID | None = None


ReviewAction = Literal["verify", "reject", "needs_field_check", "edit"]


class ReviewRequest(BaseModel):
    """One review action. Only fields that are sent are changed.

    `version` must be the finding's current version; if someone else saved first, the
    request is refused with 409 so nobody's work is silently overwritten (FR-35).
    `corrected_location: null` removes an earlier correction (the original is untouched).
    """

    action: ReviewAction
    version: int = Field(ge=1)
    type_key: str | None = Field(default=None, max_length=60)
    severity_key: str | None = Field(default=None, max_length=60)
    corrected_location: LatLon | None = None
    notes: str | None = Field(default=None, max_length=MAX_NOTES)
    # Why this decision was made (stored in the history, e.g. the reason for rejecting).
    reason: str | None = Field(default=None, max_length=MAX_NOTES)


class ManualFindingCreate(BaseModel):
    """A problem added by a person (e.g. a sidewalk observation). Starts "awaiting review"."""

    type_key: str = Field(min_length=1, max_length=60)
    notes: str = Field(max_length=MAX_NOTES)
    location: LatLon | None = None
    image_id: uuid.UUID | None = None

    @field_validator("notes")
    @classmethod
    def notes_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Describe what you saw.")
        return value


class ReviewEventOut(BaseModel):
    id: uuid.UUID
    action: str
    actor_name: str | None
    actor_roles: list[str]
    changes: dict[str, Any]
    note: str | None
    finding_version: int
    created_at: datetime


class FindingTypeOption(BaseModel):
    key: str
    label: str
    source: str
    is_placeholder: bool
    in_project: bool  # one of the types this project chose to track


class SeverityLevel(BaseModel):
    key: str
    label: str
    definition: str = ""


class SeverityRubricOut(BaseModel):
    id: uuid.UUID
    version: int
    levels: list[SeverityLevel]
    is_placeholder: bool
    is_current: bool
    created_at: datetime


class ReviewOptions(BaseModel):
    finding_types: list[FindingTypeOption]
    severity_rubric: SeverityRubricOut
