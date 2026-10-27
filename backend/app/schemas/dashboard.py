"""Response shape of the Overview dashboard."""

import uuid
from datetime import date

from pydantic import BaseModel


class DashboardScope(BaseModel):
    project_id: uuid.UUID | None  # None = every project the person can see
    days: int | None  # None = all time
    date_from: date
    date_to: date


class DashboardAccess(BaseModel):
    """What this person may see, so the screen shows only the matching charts."""

    photos: bool  # photo and analysis numbers (collectors: their own uploads)
    photos_own_only: bool
    candidates: bool  # unreviewed AI suggestions and field checks
    verified: bool
    rejected: bool
    priority: bool  # inspection priority and all inspections
    own_inspections: bool  # inspections assigned to this person


class DashboardTotals(BaseModel):
    photos: int = 0
    photos_analysed: int = 0
    photos_waiting_for_ai: int = 0
    photos_missing_location: int = 0
    waiting_review: int = 0
    needs_field_check: int = 0
    verified: int = 0
    rejected: int = 0
    verified_location_unconfirmed: int = 0
    inspections_open: int = 0
    inspections_resolved: int = 0


class ActivityDay(BaseModel):
    date: date
    photos: int
    suggestions: int  # AI suggestions and observations created that day
    verified: int  # findings verified that day (by their latest review)


class TopPriority(BaseModel):
    finding_id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    type_key: str | None
    severity_key: str | None
    score: float
    weight_covered: float
    inspection_status: str


class MapPoint(BaseModel):
    finding_id: uuid.UUID
    project_id: uuid.UUID
    latitude: float
    longitude: float
    type_key: str | None
    severity_key: str | None


class ProjectRow(BaseModel):
    id: uuid.UUID
    name: str
    my_roles: list[str]
    photos: int
    photos_waiting_for_ai: int = 0
    waiting_review: int
    verified: int
    rejected: int
    inspections_open: int


class LabelItem(BaseModel):
    key: str
    label: str


class Dashboard(BaseModel):
    scope: DashboardScope
    access: DashboardAccess
    totals: DashboardTotals
    review_status: dict[str, int]  # waiting / needs_field_check / verified / rejected
    verified_by_type: dict[str, int]
    verified_by_severity: dict[str, int]
    inspection_status: dict[str, int]  # none / planned / inspected / resolved (verified findings)
    activity: list[ActivityDay]
    top_priority: list[TopPriority]
    map_points: list[MapPoint]
    map_truncated: bool
    projects: list[ProjectRow]
    finding_types: list[LabelItem]
    severity_levels: list[LabelItem]
