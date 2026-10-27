"""Request and response shapes for reports and exports (P7)."""

import re
import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

KEY_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,60}")


class ReportFilters(BaseModel):
    """What goes into the export. Statuses are not a filter here: exports contain verified
    findings, plus unreviewed suggestions only when `include_unreviewed` is on (FR-46)."""

    type_key: list[str] = Field(default_factory=list, max_length=50)
    severity_key: list[str] = Field(default_factory=list, max_length=20)
    created_from: date | None = None
    created_to: date | None = None
    has_location: bool | None = None

    @field_validator("type_key", "severity_key")
    @classmethod
    def keys_are_codes(cls, value: list[str]) -> list[str]:
        for key in value:
            if not KEY_PATTERN.fullmatch(key):
                raise ValueError("Use the codes of finding types and severity levels.")
        return value

    @model_validator(mode="after")
    def dates_in_order(self) -> "ReportFilters":
        if self.created_from and self.created_to and self.created_from > self.created_to:
            raise ValueError("'Added from' must be on or before 'Added until'.")
        return self


class ReportRequest(BaseModel):
    format: Literal["csv", "geojson", "pdf"]
    filters: ReportFilters = Field(default_factory=ReportFilters)
    include_unreviewed: bool = False


class ReportShare(BaseModel):
    shared: bool


class ReportOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    format: str
    filters: dict[str, Any]
    include_unreviewed: bool
    settings_used: dict[str, Any]
    status: str  # queued / processing / completed / failed
    record_count: int | None
    shared_with_viewers: bool
    failure_reason: str | None
    requested_by_name: str | None
    created_at: datetime
    completed_at: datetime | None
    file_name: str | None
