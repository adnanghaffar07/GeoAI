"""Request and response shapes for organization requests (CR-004)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.auth import Email


class OrganizationRequestCreate(BaseModel):
    organization_name: str = Field(min_length=2, max_length=200)
    contact_name: str = Field(min_length=2, max_length=200)
    contact_email: str = Email
    phone: str | None = Field(default=None, max_length=40)
    city_or_agency: str = Field(min_length=2, max_length=200)
    note: str | None = Field(default=None, max_length=2000)
    # Trap for robots: hidden on the page, so people leave it empty.
    website: str | None = Field(default=None, max_length=200)


class OrganizationRequestSent(BaseModel):
    message: str


class OrganizationRequestOut(BaseModel):
    id: uuid.UUID
    organization_name: str
    contact_name: str
    contact_email: str
    phone: str | None
    city_or_agency: str
    note: str | None
    status: Literal["pending", "approved", "rejected"]
    created_at: datetime
    decided_at: datetime | None
    decided_by_name: str | None
    decision_note: str | None
    organization_id: uuid.UUID | None


class OrganizationRequestList(BaseModel):
    items: list[OrganizationRequestOut]
    pending_count: int


class ApproveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class RejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class InvitationLinkOut(BaseModel):
    request: OrganizationRequestOut
    invitation_url: str
    invitation_expires_at: datetime
