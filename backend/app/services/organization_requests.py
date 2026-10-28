"""Requests from new organizations, and their review by platform admins (CR-004).

- Anyone can send a request (public form). It creates nothing but the request.
- Only a platform admin can list, approve or reject requests.
- Approving creates the organization, its placeholder settings and an invitation for the
  contact person as its first admin, all in one transaction. The contact sets their own
  password through the invitation link; no password is ever taken on the request form.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, TooManyRequestsError
from app.core.security import normalize_email
from app.models import Organization, OrganizationRequest, User
from app.models.base import utc_now
from app.services.accounts import InvitationLink, invite_to_organization
from app.services.audit import record_event
from app.services.catalog import seed_placeholder_settings

PLATFORM_ROLE = "platform_admin"
_ALREADY_WAITING = (
    "A request for this email is already waiting for review. We will contact you soon."
)


@dataclass(frozen=True)
class RequestDetails:
    organization_name: str
    contact_name: str
    contact_email: str
    phone: str | None
    city_or_agency: str
    note: str | None


def submit_request(
    db: Session, details: RequestDetails, *, requester_ip: str | None
) -> OrganizationRequest:
    """Save a new request (commits). Refuses a second waiting request for the same email."""
    email = normalize_email(details.contact_email)
    settings = get_settings()
    if requester_ip:
        recent = db.scalar(
            select(func.count())
            .select_from(OrganizationRequest)
            .where(
                OrganizationRequest.requester_ip == requester_ip,
                OrganizationRequest.created_at > utc_now() - timedelta(hours=1),
            )
        )
        if (recent or 0) >= settings.organization_requests_per_hour:
            raise TooManyRequestsError(
                "Too many requests from your network. Please try again in an hour."
            )
    if _pending_for(db, email) is not None:
        raise ConflictError(_ALREADY_WAITING)

    request = OrganizationRequest(
        organization_name=details.organization_name.strip(),
        contact_name=details.contact_name.strip(),
        contact_email=email,
        phone=(details.phone or "").strip() or None,
        city_or_agency=details.city_or_agency.strip(),
        note=(details.note or "").strip() or None,
        requester_ip=requester_ip,
    )
    db.add(request)
    try:
        db.flush()
    except IntegrityError as exc:  # the same email sent twice at the same moment
        db.rollback()
        raise ConflictError(_ALREADY_WAITING) from exc
    record_event(
        db,
        action="organization_request.created",
        organization_id=None,
        actor_user_id=None,
        target_type="organization_request",
        target_id=request.id,
        details={"organization_name": request.organization_name, "email": email},
    )
    db.commit()
    return request


def _pending_for(db: Session, email: str) -> OrganizationRequest | None:
    return db.scalar(
        select(OrganizationRequest).where(
            func.lower(OrganizationRequest.contact_email) == email,
            OrganizationRequest.status == "pending",
        )
    )


def list_requests(db: Session, status: str) -> list[OrganizationRequest]:
    """Waiting requests oldest first (first come, first served); decided ones newest first."""
    order = (
        OrganizationRequest.created_at.asc()
        if status == "pending"
        else OrganizationRequest.decided_at.desc()
    )
    return list(
        db.scalars(
            select(OrganizationRequest)
            .where(OrganizationRequest.status == status)
            .order_by(order)
            .limit(500)
        )
    )


def count_pending(db: Session) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(OrganizationRequest)
            .where(OrganizationRequest.status == "pending")
        )
        or 0
    )


def _load_for_decision(db: Session, request_id: uuid.UUID) -> OrganizationRequest:
    """Lock the row so two admins clicking at the same moment cannot both decide."""
    request = db.scalar(
        select(OrganizationRequest).where(OrganizationRequest.id == request_id).with_for_update()
    )
    if request is None:
        raise NotFoundError("This request was not found.")
    if request.status != "pending":
        raise ConflictError(f"This request was already {request.status}. Reload the list.")
    return request


def approve_request(
    db: Session, admin: User, request_id: uuid.UUID, *, note: str | None
) -> tuple[OrganizationRequest, InvitationLink]:
    """Create the organization and an invitation for its first admin (commits)."""
    request = _load_for_decision(db, request_id)
    organization = Organization(name=request.organization_name)
    db.add(organization)
    db.flush()
    seed_placeholder_settings(db, organization.id)
    record_event(
        db,
        action="organization.created",
        organization_id=organization.id,
        actor_user_id=admin.id,
        actor_roles=[PLATFORM_ROLE],
        details={
            "name": organization.name,
            "first_admin_email": request.contact_email,
            "via": "organization_request",
            "request_id": str(request.id),
        },
    )
    link = invite_to_organization(
        db,
        organization_id=organization.id,
        email=request.contact_email,
        org_role="org_admin",
        invited_by=admin.id,
        actor_roles=[PLATFORM_ROLE],
    )
    _decide(db, request, admin, "approved", note)
    request.organization_id = organization.id
    record_event(
        db,
        action="organization_request.approved",
        organization_id=organization.id,
        actor_user_id=admin.id,
        actor_roles=[PLATFORM_ROLE],
        target_type="organization_request",
        target_id=request.id,
        details={"organization_name": organization.name, "email": request.contact_email},
    )
    db.commit()
    return request, link


def reject_request(
    db: Session, admin: User, request_id: uuid.UUID, *, reason: str
) -> OrganizationRequest:
    request = _load_for_decision(db, request_id)
    _decide(db, request, admin, "rejected", reason)
    record_event(
        db,
        action="organization_request.rejected",
        organization_id=None,
        actor_user_id=admin.id,
        actor_roles=[PLATFORM_ROLE],
        target_type="organization_request",
        target_id=request.id,
        details={"email": request.contact_email, "reason": request.decision_note},
    )
    db.commit()
    return request


def new_invitation_link(db: Session, admin: User, request_id: uuid.UUID) -> InvitationLink:
    """A fresh link for an approved request (the old one stops working). Commits."""
    request = db.get(OrganizationRequest, request_id)
    if request is None:
        raise NotFoundError("This request was not found.")
    if request.status != "approved" or request.organization_id is None:
        raise ConflictError("Only approved requests have an invitation link.")
    link = invite_to_organization(
        db,
        organization_id=request.organization_id,
        email=request.contact_email,
        org_role="org_admin",
        invited_by=admin.id,
        actor_roles=[PLATFORM_ROLE],
    )
    db.commit()
    return link


def _decide(
    db: Session, request: OrganizationRequest, admin: User, status: str, note: str | None
) -> None:
    request.status = status
    request.decided_by = admin.id
    request.decided_at = utc_now()
    request.decision_note = (note or "").strip() or None


def decided_by_names(db: Session, requests: list[OrganizationRequest]) -> dict[uuid.UUID, str]:
    ids = {r.decided_by for r in requests if r.decided_by}
    if not ids:
        return {}
    return {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_(ids)))}
