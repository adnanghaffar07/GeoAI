"""Business rules for sign-in, invitations, members, and password resets.

Functions here change the database session but do not commit, unless stated;
routes commit once the whole action has succeeded (one transaction per action).
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import OrgContext
from app.core.config import get_settings
from app.core.errors import (
    ConflictError,
    LinkInvalidError,
    NotAuthenticatedError,
    NotFoundError,
    TooManyRequestsError,
    ValidationFailedError,
)
from app.core.permissions import org_permissions
from app.core.security import (
    hash_password,
    hash_token,
    new_token,
    normalize_email,
    verify_password,
)
from app.models import (
    AuditEvent,
    Invitation,
    Organization,
    OrganizationMembership,
    PasswordReset,
    User,
)
from app.models.base import utc_now
from app.services.audit import record_event
from app.services.projects import remove_user_from_org_projects
from app.services.sessions import create_session, end_all_sessions

_WRONG_CREDENTIALS = "Email or password is incorrect."


# --------------------------------------------------------------------------- sign-in
def sign_in(
    db: Session, email: str, password: str, *, user_agent: str | None, ip_address: str | None
) -> tuple[User, str]:
    """Check credentials and create a session. Returns (user, session token).

    Commits. Failed attempts are recorded (and committed) before the error is raised,
    so the lockout counts them.

    Raises:
        TooManyRequestsError: too many recent failed attempts for this email.
        NotAuthenticatedError: wrong email or password (same message for both).
    """
    settings = get_settings()
    email = normalize_email(email)
    window_start = utc_now() - timedelta(minutes=settings.sign_in_failure_window_minutes)
    recent_failures = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.action == "auth.sign_in_failed",
            AuditEvent.details["email"].astext == email,
            AuditEvent.created_at > window_start,
        )
    )
    if (recent_failures or 0) >= settings.sign_in_max_failures:
        raise TooManyRequestsError()

    user = db.scalar(select(User).where(func.lower(User.email) == email))
    password_ok = verify_password(password, user.password_hash if user else None)
    if user is None or not password_ok or not user.is_active:
        record_event(
            db,
            action="auth.sign_in_failed",
            organization_id=None,
            actor_user_id=None,
            details={"email": email, "ip_address": ip_address},
        )
        db.commit()
        raise NotAuthenticatedError(_WRONG_CREDENTIALS)

    token = create_session(db, user, user_agent=user_agent, ip_address=ip_address)
    record_event(
        db,
        action="auth.signed_in",
        organization_id=None,
        actor_user_id=user.id,
        details={"ip_address": ip_address},
    )
    db.commit()
    return user, token


@dataclass(frozen=True)
class MembershipSummary:
    organization_id: uuid.UUID
    organization_name: str
    org_role: str
    permissions: list[str]


def list_memberships(db: Session, user: User) -> list[MembershipSummary]:
    rows = db.execute(
        select(Organization, OrganizationMembership)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(OrganizationMembership.user_id == user.id)
        .order_by(Organization.name)
    ).all()
    return [
        MembershipSummary(
            organization_id=org.id,
            organization_name=org.name,
            org_role=membership.org_role,
            permissions=sorted(org_permissions(membership.org_role)),
        )
        for org, membership in rows
    ]


# ----------------------------------------------------------------------- invitations
@dataclass(frozen=True)
class InvitationLink:
    invitation: Invitation
    url: str


def create_invitation(db: Session, ctx: OrgContext, email: str, org_role: str) -> InvitationLink:
    """Create an invitation and its one-time link. Older pending invites for the same
    email in this organization are revoked, so only the newest link works."""
    email = normalize_email(email)
    already_member = db.scalar(
        select(OrganizationMembership.id)
        .join(User, User.id == OrganizationMembership.user_id)
        .where(
            OrganizationMembership.organization_id == ctx.organization.id,
            func.lower(User.email) == email,
        )
    )
    if already_member:
        raise ConflictError("This person is already a member of the organization.")

    now = utc_now()
    pending = db.scalars(
        select(Invitation).where(
            Invitation.organization_id == ctx.organization.id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
    ).all()
    for old in pending:
        old.revoked_at = now

    token = new_token()
    invitation = Invitation(
        organization_id=ctx.organization.id,
        email=email,
        org_role=org_role,
        token_hash=hash_token(token),
        invited_by=ctx.user.id,
        expires_at=now + timedelta(days=get_settings().invitation_lifetime_days),
    )
    db.add(invitation)
    db.flush()
    record_event(
        db,
        action="invitation.created",
        organization_id=ctx.organization.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="invitation",
        target_id=invitation.id,
        details={"email": email, "org_role": org_role},
    )
    return InvitationLink(invitation, f"{get_settings().public_app_url}/invite/{token}")


def account_exists(db: Session, email: str) -> bool:
    return db.scalar(select(User.id).where(func.lower(User.email) == email)) is not None


def find_usable_invitation(db: Session, token: str) -> tuple[Invitation, Organization]:
    """Return a valid invitation for a link token.

    Raises:
        LinkInvalidError: with details.reason "invalid", "revoked", "used", or "expired".
    """
    row = db.execute(
        select(Invitation, Organization)
        .join(Organization, Organization.id == Invitation.organization_id)
        .where(Invitation.token_hash == hash_token(token))
    ).first()
    if row is None:
        raise LinkInvalidError(details={"reason": "invalid"})
    invitation, organization = row
    if invitation.revoked_at is not None:
        raise LinkInvalidError(details={"reason": "revoked"})
    if invitation.accepted_at is not None:
        raise LinkInvalidError(details={"reason": "used"})
    if invitation.expires_at <= utc_now():
        raise LinkInvalidError(details={"reason": "expired"})
    return invitation, organization


@dataclass(frozen=True)
class AcceptResult:
    user: User
    created_new_account: bool


def accept_invitation(
    db: Session, token: str, full_name: str | None, password: str | None
) -> AcceptResult:
    """Accept an invitation.

    - New email: creates the account with the given name and password.
    - Email that already has an account (member of another organization): adds the
      membership only; the existing password is NOT changed and the person must sign in
      normally. This prevents taking over an existing account with an invite link.
    """
    invitation, organization = find_usable_invitation(db, token)
    user = db.scalar(select(User).where(func.lower(User.email) == invitation.email))
    created = user is None
    if user is None:
        if not full_name or not full_name.strip() or not password:
            raise ValidationFailedError(
                "Enter your name and a password to create your account.",
                details={"fields": [{"field": "body.full_name", "message": "Required"}]},
            )
        user = User(
            email=invitation.email,
            full_name=full_name.strip(),
            password_hash=hash_password(password),
        )
        db.add(user)
        db.flush()
    db.add(
        OrganizationMembership(
            organization_id=organization.id, user_id=user.id, org_role=invitation.org_role
        )
    )
    invitation.accepted_at = utc_now()
    record_event(
        db,
        action="invitation.accepted",
        organization_id=organization.id,
        actor_user_id=user.id,
        actor_roles=[invitation.org_role],
        target_type="invitation",
        target_id=invitation.id,
        details={"email": invitation.email, "created_new_account": created},
    )
    return AcceptResult(user=user, created_new_account=created)


def list_pending_invitations(db: Session, org_id: uuid.UUID) -> list[Invitation]:
    return list(
        db.scalars(
            select(Invitation)
            .where(
                Invitation.organization_id == org_id,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
                Invitation.expires_at > utc_now(),
            )
            .order_by(Invitation.created_at.desc())
        ).all()
    )


def revoke_invitation(db: Session, ctx: OrgContext, invitation_id: uuid.UUID) -> None:
    invitation = db.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id, Invitation.organization_id == ctx.organization.id
        )
    )
    if invitation is None or invitation.accepted_at is not None:
        raise NotFoundError("Invitation not found.")
    if invitation.revoked_at is None:
        invitation.revoked_at = utc_now()
        record_event(
            db,
            action="invitation.revoked",
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            actor_roles=ctx.actor_roles,
            target_type="invitation",
            target_id=invitation.id,
            details={"email": invitation.email},
        )


# --------------------------------------------------------------------------- members
def list_members(db: Session, org_id: uuid.UUID) -> list[tuple[User, OrganizationMembership]]:
    rows = db.execute(
        select(User, OrganizationMembership)
        .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
        .where(OrganizationMembership.organization_id == org_id)
        .order_by(User.full_name, User.email)
    ).all()
    return [(user, membership) for user, membership in rows]


def _get_membership_for_update(
    db: Session, org_id: uuid.UUID, user_id: uuid.UUID
) -> OrganizationMembership:
    membership = db.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.user_id == user_id,
        )
        .with_for_update()
    )
    if membership is None:
        raise NotFoundError("Member not found.")
    return membership


def _ensure_another_admin_remains(db: Session, org_id: uuid.UUID) -> None:
    """Refuse to remove or demote the last org admin (the organization would be locked)."""
    # Lock all admin rows so two simultaneous changes cannot both pass this check.
    admins = db.scalars(
        select(OrganizationMembership.id)
        .where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.org_role == "org_admin",
        )
        .with_for_update()
    ).all()
    if len(admins) <= 1:
        raise ConflictError(
            "The organization must keep at least one administrator. "
            "Make someone else an administrator first."
        )


def change_member_role(
    db: Session, ctx: OrgContext, user_id: uuid.UUID, new_role: str
) -> OrganizationMembership:
    membership = _get_membership_for_update(db, ctx.organization.id, user_id)
    old_role = membership.org_role
    if old_role == new_role:
        return membership
    if old_role == "org_admin":
        _ensure_another_admin_remains(db, ctx.organization.id)
    membership.org_role = new_role
    record_event(
        db,
        action="member.role_changed",
        organization_id=ctx.organization.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="user",
        target_id=user_id,
        details={"old_role": old_role, "new_role": new_role},
    )
    return membership


def remove_member(db: Session, ctx: OrgContext, user_id: uuid.UUID) -> None:
    """Remove a person from the organization. Their sessions end immediately (FR-03).

    Their project roles in this organization's projects are removed too.
    """
    membership = _get_membership_for_update(db, ctx.organization.id, user_id)
    if membership.org_role == "org_admin":
        _ensure_another_admin_remains(db, ctx.organization.id)
    removed_role = membership.org_role
    db.delete(membership)
    remove_user_from_org_projects(db, ctx.organization.id, user_id)
    end_all_sessions(db, user_id)
    record_event(
        db,
        action="member.removed",
        organization_id=ctx.organization.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="user",
        target_id=user_id,
        details={"removed_role": removed_role},
    )


# ------------------------------------------------------------------- password resets
@dataclass(frozen=True)
class ResetLink:
    reset: PasswordReset
    url: str


def create_password_reset(db: Session, ctx: OrgContext, user_id: uuid.UUID) -> ResetLink:
    """Create a one-time password reset link for a member of this organization."""
    _get_membership_for_update(db, ctx.organization.id, user_id)  # must be a member here
    now = utc_now()
    # Only the newest link works: older unused links for this person expire now.
    for old in db.scalars(
        select(PasswordReset).where(
            PasswordReset.user_id == user_id,
            PasswordReset.used_at.is_(None),
            PasswordReset.expires_at > now,
        )
    ).all():
        old.expires_at = now
    token = new_token()
    reset = PasswordReset(
        user_id=user_id,
        token_hash=hash_token(token),
        created_by=ctx.user.id,
        expires_at=now + timedelta(minutes=get_settings().password_reset_lifetime_minutes),
    )
    db.add(reset)
    db.flush()
    record_event(
        db,
        action="password_reset.created",
        organization_id=ctx.organization.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="user",
        target_id=user_id,
    )
    return ResetLink(reset, f"{get_settings().public_app_url}/reset-password/{token}")


def find_usable_reset(db: Session, token: str) -> tuple[PasswordReset, User]:
    row = db.execute(
        select(PasswordReset, User)
        .join(User, User.id == PasswordReset.user_id)
        .where(PasswordReset.token_hash == hash_token(token))
    ).first()
    if row is None:
        raise LinkInvalidError(details={"reason": "invalid"})
    reset, user = row
    if reset.used_at is not None:
        raise LinkInvalidError(details={"reason": "used"})
    if reset.expires_at <= utc_now():
        raise LinkInvalidError(details={"reason": "expired"})
    return reset, user


def use_password_reset(db: Session, token: str, new_password: str) -> User:
    """Set a new password, mark the link used, and sign the person out everywhere."""
    reset, user = find_usable_reset(db, token)
    user.password_hash = hash_password(new_password)
    reset.used_at = utc_now()
    end_all_sessions(db, user.id)
    record_event(
        db,
        action="password_reset.used",
        organization_id=None,
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
    )
    return user
