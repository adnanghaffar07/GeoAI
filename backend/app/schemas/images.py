"""Request and response shapes for photos."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LatLon(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class ImageAnalysis(BaseModel):
    """The photo's analysis with the current AI model, if requested."""

    job_id: uuid.UUID
    status: str  # queued / processing / completed / failed
    failure_reason: str | None
    model_version: str
    is_test_detector: bool
    is_trial_model: bool = False  # "TRIAL MODEL: accuracy not approved"
    # Number of AI suggestions; null for people who may not see suggestions.
    candidate_count: int | None


class ImageOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    width_px: int
    height_px: int
    captured_at: datetime | None
    # Where the camera (or phone) was. Approximate unless a reviewer confirms it.
    location: LatLon | None
    location_source: str
    location_quality: str
    quality_flags: list[str]
    status: str
    uploaded_by: uuid.UUID
    uploaded_by_name: str | None
    created_at: datetime
    analysis: ImageAnalysis | None = None


class UploadResult(BaseModel):
    # True when this exact file was already in the project; the existing photo is returned.
    duplicate: bool
    image: ImageOut


class SetLocationRequest(LatLon):
    """A point picked on the map for a photo that has no GPS location."""
