"""Request and response shapes for projects and project teams."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ProjectRole = Literal["project_manager", "field_collector", "technical_reviewer", "viewer"]

# Limits that keep a boundary reasonable to store and draw.
MAX_BOUNDARY_POINTS = 10_000


class GeoJsonArea(BaseModel):
    """A survey area: GeoJSON Polygon or MultiPolygon in longitude/latitude (EPSG:4326).

    Shape problems (self-crossing edges etc.) are checked by PostGIS when saving.
    """

    type: Literal["Polygon", "MultiPolygon"]
    coordinates: list[Any]

    @model_validator(mode="after")
    def check_coordinates(self) -> "GeoJsonArea":
        polygons = [self.coordinates] if self.type == "Polygon" else self.coordinates
        if not polygons:
            raise ValueError("The area has no shape.")
        points = 0
        for polygon in polygons:
            if not isinstance(polygon, list) or not polygon:
                raise ValueError("Each area needs at least one ring of points.")
            for ring in polygon:
                if not isinstance(ring, list) or len(ring) < 4:
                    raise ValueError("Each ring needs at least 4 points (3 corners + closing).")
                for point in ring:
                    if (
                        not isinstance(point, list)
                        or len(point) < 2
                        or not all(isinstance(v, int | float) for v in point[:2])
                    ):
                        raise ValueError("Points must be [longitude, latitude] numbers.")
                    lon, lat = point[0], point[1]
                    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                        raise ValueError("Points must be longitude -180..180, latitude -90..90.")
                    points += 1
        if points > MAX_BOUNDARY_POINTS:
            raise ValueError(f"The area has too many points (maximum {MAX_BOUNDARY_POINTS}).")
        return self


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    boundary: GeoJsonArea
    finding_type_keys: list[str] = Field(min_length=1, max_length=50)
    # Spec: assigned reviewers are required. The creator may choose themselves (Q2).
    reviewer_user_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    road_category: str | None = Field(default=None, max_length=60)
    survey_start: date | None = None
    survey_end: date | None = None
    partner_reference: str | None = Field(default=None, max_length=120)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Enter a project name.")
        return value

    @model_validator(mode="after")
    def check_dates(self) -> "ProjectCreate":
        if self.survey_start and self.survey_end and self.survey_end < self.survey_start:
            raise ValueError("Survey end date must be on or after the start date.")
        return self


class ProjectUpdate(BaseModel):
    """Only the fields sent are changed."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    boundary: GeoJsonArea | None = None
    finding_type_keys: list[str] | None = Field(default=None, min_length=1, max_length=50)
    road_category: str | None = Field(default=None, max_length=60)
    survey_start: date | None = None
    survey_end: date | None = None
    partner_reference: str | None = Field(default=None, max_length=120)


class ProjectCounts(BaseModel):
    images: int
    images_missing_location: int
    images_with_quality_flags: int
    images_analysed: int = 0
    images_waiting_for_ai: int = 0
    findings_to_review: int = 0
    findings_needs_field_check: int = 0
    findings_verified: int = 0
    verified_location_unconfirmed: int = 0
    verified_by_type: dict[str, int] = {}
    inspections_open: int = 0


class ProjectSummary(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    archived: bool
    created_at: datetime
    my_roles: list[str]
    counts: ProjectCounts


class ProjectDetail(ProjectSummary):
    boundary: dict[str, Any]
    finding_type_keys: list[str]
    road_category: str | None
    survey_start: date | None
    survey_end: date | None
    partner_reference: str | None
    archived_at: datetime | None
    # What the caller may do here; screens show buttons from this list.
    my_permissions: list[str]


class ProjectMemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str
    added_at: datetime


class ProjectMemberCreate(BaseModel):
    user_id: uuid.UUID
    role: ProjectRole


class EligibleMember(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    org_role: str


class FindingTypeOut(BaseModel):
    key: str
    label: str
    source: Literal["ai", "manual"] | str
    is_placeholder: bool
    is_active: bool
