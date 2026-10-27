"""Request and response shapes for organizations, members, invitations, and history."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import Email

OrgRole = Literal["org_admin", "org_manager", "org_member"]


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    org_role: str
    is_active: bool
    joined_at: datetime


class ChangeRoleRequest(BaseModel):
    org_role: OrgRole


class InvitationCreate(BaseModel):
    email: str = Email
    org_role: OrgRole


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    org_role: str
    expires_at: datetime
    created_at: datetime


class InvitationCreated(InvitationOut):
    # Shown once to the admin, with a Copy button (FR-54). Never retrievable again.
    invite_url: str


class PasswordResetCreated(BaseModel):
    # Shown once to the admin (FR-55). Never retrievable again.
    reset_url: str
    expires_at: datetime


class AuditEventOut(BaseModel):
    id: uuid.UUID
    action: str
    actor_user_id: uuid.UUID | None
    actor_email: str | None
    actor_roles: list[str]
    target_type: str | None
    target_id: uuid.UUID | None
    details: dict[str, Any]
    request_id: str | None
    created_at: datetime
