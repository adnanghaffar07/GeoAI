"""Road-risk forecasting responses (F4c; api-spec.md section 3.10).

Owner decision F4-D2 (2026-10-30): levels only. No response carries a percentage or the raw
model value; every risk response carries the TRIAL label and the fixed notice.
"""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

TRIAL_LABEL = "TRIAL FORECAST"
NOTICE = "Risk estimate, not a confirmed defect."


VisibleRole = Literal["technical_reviewer", "viewer", "field_collector"]


class ForecastSettingsIn(BaseModel):
    """Switch on/off and/or who else can see road risk (project managers always can)."""

    enabled: bool | None = None
    visible_to_roles: list[VisibleRole] | None = Field(default=None, max_length=3)
    assistant_enabled: bool | None = None  # CR-006

    @model_validator(mode="after")
    def something_to_change(self) -> "ForecastSettingsIn":
        if (
            self.enabled is None
            and self.visible_to_roles is None
            and self.assistant_enabled is None
        ):
            raise ValueError("Give enabled, visible_to_roles or assistant_enabled.")
        return self


class ForecastStatusOut(BaseModel):
    """Whether forecasting is on for the project and how far it has got."""

    enabled: bool
    status: str  # off / setting_up / ready / failed / too_large
    level: int | None  # 2 = tested Chicago levels, 1 = risk factors only
    level_label: str | None
    message: str | None
    area_km2: float | None
    max_area_km2: float
    last_weekly_run: date | None
    last_daily_run: date | None
    can_configure: bool
    visible_to_roles: list[str]  # besides project managers (F4d)
    assistant_enabled: bool = False  # CR-006 "Ask about road risk"
    label: str = TRIAL_LABEL
    notice: str = NOTICE


class RunOut(BaseModel):
    id: uuid.UUID
    kind: str
    as_of: date
    model_version: str
    data_dates: dict[str, Any]
    finished_at: datetime | None


class ReasonOut(BaseModel):
    """One of the main reasons a section ranks where it does, largest first (no numbers)."""

    input: str
    label: str
    value: float | None


class FactorOut(BaseModel):
    factor: str
    label: str
    value: float | None  # None = missing, never guessed
    level: str  # high / medium / low / missing
    kind: str  # risk / background


class SectionRiskOut(BaseModel):
    section_id: uuid.UUID
    name: str | None
    road_type: str
    length_m: float
    position: int  # 1 = inspect first, within this project
    level: str | None  # high / medium / low (Level 2 only)
    rank_in_area: int | None  # 1 = riskiest in the whole area that Monday (Level 2 only)
    reasons: list[ReasonOut]
    missing_inputs: list[str]
    factors: list[FactorOut]


class LevelCounts(BaseModel):
    high: int = 0
    medium: int = 0
    low: int = 0


class RiskListOut(BaseModel):
    items: list[SectionRiskOut]
    page: int
    page_size: int
    total: int
    status: ForecastStatusOut
    levels_run: RunOut | None  # the weekly Chicago levels shown (Level 2)
    factors_run: RunOut | None  # the daily risk factors shown
    counts: LevelCounts
    label: str = TRIAL_LABEL
    notice: str = NOTICE


class HistoryPoint(BaseModel):
    as_of: date
    level: str
    rank_in_area: int


class LinkedInspection(BaseModel):
    id: uuid.UUID
    status: str
    planned_date: date | None


class RoadDetailsOut(BaseModel):
    """Team lead item 12, from OpenStreetMap; None = not on the map."""

    speed_limit_mph: int | None = None
    lanes: int | None = None
    surface: str | None = None
    oneway: bool | None = None
    road_ref: str | None = None
    source: str = "OpenStreetMap contributors"


class SectionDetailOut(BaseModel):
    section: SectionRiskOut
    road: RoadDetailsOut | None = None
    geometry: dict[str, Any]
    history: list[HistoryPoint]  # weekly levels, newest first
    inspections: list[LinkedInspection]  # inspections planned from this section's levels
    levels_run: RunOut | None
    factors_run: RunOut | None
    label: str = TRIAL_LABEL
    notice: str = NOTICE


class OutlookOut(BaseModel):
    source: str
    issued_at: datetime
    fetched_at: datetime
    days: list[dict[str, Any]]
    freeze_thaw_days: int
    frost_days: int
    heavy_rain_days: int
    snow_mm: float


class RecentWeatherOut(BaseModel):
    """The weather inputs of the latest daily run (the same for every section of a station)."""

    as_of: date
    values: list[FactorOut]


class WeatherOut(BaseModel):
    outlook: OutlookOut | None
    recent: RecentWeatherOut | None


class AlertOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    type: str
    title: str
    details: dict[str, Any]
    created_at: datetime
    closed_at: datetime | None
    read: bool


class NotificationsOut(BaseModel):
    items: list[AlertOut]
    unread_count: int = Field(ge=0)
    # The person manages at least one project, so the bell is shown (F4e).
    manages_projects: bool = False


class AssistantQuestion(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class SourceLink(BaseModel):
    label: str
    path: str  # a page of this app, e.g. /projects/{id}/road-risk/{section}


class AssistantAnswer(BaseModel):
    """CR-006: an answer built from the app's data; never a percentage, never an action."""

    answer: str
    sources: list[SourceLink]
    used_model: bool  # False: the built-in answer (the free local model was off or too slow)
    questions_left_today: int
    label: str = f"{TRIAL_LABEL} · AI answer: check the linked pages"
    notice: str = NOTICE
