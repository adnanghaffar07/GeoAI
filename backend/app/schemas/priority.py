"""Request and response shapes for inspection priority and inspections (P7)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.findings import FindingOut

PRIORITY_INPUTS: tuple[str, ...] = ("severity", "road_category", "facility_proximity")


class PriorityConfigIn(BaseModel):
    """A new settings version. Nothing is edited in place (database-schema §3.3)."""

    weights: dict[str, float]
    severity_points: dict[str, float]
    road_category_points: dict[str, float]
    facility_types: list[str] = Field(default_factory=list, max_length=20)
    facility_radius_m: int = Field(ge=1, le=5000)
    # True until the customer confirms these values (PI-08).
    is_placeholder: bool = True

    @field_validator("weights")
    @classmethod
    def check_weights(cls, value: dict[str, float]) -> dict[str, float]:
        if set(value) != set(PRIORITY_INPUTS):
            raise ValueError(
                f"Give a weight for exactly these inputs: {', '.join(PRIORITY_INPUTS)}."
            )
        if any(not 0 <= weight <= 1 for weight in value.values()):
            raise ValueError("Each weight must be between 0 and 1.")
        if abs(sum(value.values()) - 1) > 0.001:
            raise ValueError("The weights must add up to 1 (100%).")
        return value

    @field_validator("severity_points", "road_category_points")
    @classmethod
    def check_points(cls, value: dict[str, float]) -> dict[str, float]:
        if len(value) > 50:
            raise ValueError("Too many entries.")
        for key, points in value.items():
            if not key.strip() or len(key) > 60:
                raise ValueError("Each entry needs a name of up to 60 characters.")
            if not 0 <= points <= 100:
                raise ValueError("Points must be between 0 and 100.")
        return {key.strip(): points for key, points in value.items()}

    @field_validator("facility_types")
    @classmethod
    def check_facility_types(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if any(len(item) > 60 for item in cleaned):
            raise ValueError("Facility type names can be up to 60 characters.")
        return list(dict.fromkeys(cleaned))


class PriorityConfigOut(BaseModel):
    id: uuid.UUID
    version: int
    weights: dict[str, float]
    severity_points: dict[str, float]
    road_category_points: dict[str, float]
    facility_types: list[str]
    facility_radius_m: int
    is_placeholder: bool
    is_current: bool
    created_by_name: str | None
    created_at: datetime


class PriorityInput(BaseModel):
    """One input of the score, shown so anyone can check the calculation (FR-41)."""

    key: str
    label: str
    value: str | None
    points: float | None
    weight: float
    contribution: float | None
    missing: bool
    reason: str | None = None


class PriorityBreakdown(BaseModel):
    inputs: list[PriorityInput]
    # Share of the total weight that had a value (1.0 = nothing missing).
    weight_covered: float
    missing: list[str]


class InspectionPlan(BaseModel):
    owner_user_id: uuid.UUID
    planned_date: date


class InspectionUpdate(BaseModel):
    status: Literal["inspected", "resolved"]
    outcome_note: str | None = Field(default=None, max_length=2000)


class InspectionReopen(BaseModel):
    reason: str = Field(max_length=2000)
    owner_user_id: uuid.UUID
    planned_date: date

    @model_validator(mode="after")
    def reason_required(self) -> "InspectionReopen":
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("Say why the inspection is reopened.")
        return self


class InspectionOut(BaseModel):
    id: uuid.UUID
    finding_id: uuid.UUID
    owner_user_id: uuid.UUID
    owner_name: str | None
    planned_date: date
    status: str  # planned / inspected / resolved / reopened
    outcome_note: str | None
    has_evidence: bool
    inspected_by_name: str | None
    inspected_at: datetime | None
    resolved_by_name: str | None
    resolved_at: datetime | None
    reopen_reason: str | None
    reopened_by_name: str | None
    reopened_at: datetime | None
    created_by_name: str | None
    created_at: datetime


class PriorityItem(BaseModel):
    finding: FindingOut
    # "Inspection priority" only: it does not decide repairs or compliance (FR-42).
    score: float
    breakdown: PriorityBreakdown
    inspection: InspectionOut | None


class PriorityList(BaseModel):
    items: list[PriorityItem]
    page: int
    page_size: int
    total: int
    config: PriorityConfigOut


class AssignedInspection(BaseModel):
    """An open inspection with its finding, for the "inspections" list."""

    inspection: InspectionOut
    finding: FindingOut
