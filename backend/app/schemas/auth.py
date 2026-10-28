"""Request and response shapes for sign-in, invitations, and password resets."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.security import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH

Password = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

# A light format check ("something@something.something"). Stricter checkers reject
# internal addresses some organizations use (e.g. ending in .local), so we keep it simple;
# an invitation link proves the address works.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
Email = Field(min_length=3, max_length=320, pattern=EMAIL_PATTERN)


class SignInRequest(BaseModel):
    email: str = Email
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_platform_admin: bool = False


class MembershipOut(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    org_role: str
    permissions: list[str]


class MeResponse(BaseModel):
    user: UserOut
    memberships: list[MembershipOut]


class InvitationInfo(BaseModel):
    organization_name: str
    email: str
    org_role: str
    # True when this email already has an account: the person only needs to sign in.
    account_exists: bool


class AcceptInvitationRequest(BaseModel):
    """Name and password are required only when creating a new account."""

    full_name: str | None = Field(default=None, max_length=200)
    password: str | None = Password

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class AcceptInvitationResponse(BaseModel):
    # "signed_in": new account created and signed in.
    # "sign_in_required": existing account; membership added, sign in normally.
    result: Literal["signed_in", "sign_in_required"]


class ResetInfo(BaseModel):
    email: str


class SetPasswordRequest(BaseModel):
    password: str = Password
