"""Requests from new organizations (CR-004).

- `POST /api/v1/organization-requests`: public "Request access" form (no sign-in).
- `/api/v1/platform/organization-requests...`: platform admins only.
"""

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.auth import require_platform_admin
from app.core.database import get_db
from app.models import OrganizationRequest, User
from app.schemas.platform import (
    ApproveRequest,
    InvitationLinkOut,
    OrganizationRequestCreate,
    OrganizationRequestList,
    OrganizationRequestOut,
    OrganizationRequestSent,
    RejectRequest,
)
from app.services import organization_requests as service
from app.services.accounts import InvitationLink

logger = logging.getLogger(__name__)

public_router = APIRouter(prefix="/organization-requests", tags=["organization requests"])
router = APIRouter(prefix="/platform/organization-requests", tags=["platform"])

SENT_MESSAGE = (
    "Thank you. Your request has been sent. We will review it and email you an "
    "invitation link when it is approved."
)


def _requester_ip(request: Request) -> str | None:
    """The visitor's address. Behind Cloudflare or a proxy, the real one is in a header;
    it is used only for the spam limit, so a faked header can only hurt the faker."""
    forwarded = (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    )
    if forwarded:
        return forwarded[:64]
    return request.client.host if request.client else None


@public_router.post("", status_code=status.HTTP_202_ACCEPTED)
def send_request(
    body: OrganizationRequestCreate, request: Request, db: Session = Depends(get_db)
) -> OrganizationRequestSent:
    if body.website:  # only robots fill in the hidden field; pretend it worked
        logger.info("Organization request ignored: hidden field was filled in")
        return OrganizationRequestSent(message=SENT_MESSAGE)
    service.submit_request(
        db,
        service.RequestDetails(
            organization_name=body.organization_name,
            contact_name=body.contact_name,
            contact_email=body.contact_email,
            phone=body.phone,
            city_or_agency=body.city_or_agency,
            note=body.note,
        ),
        requester_ip=_requester_ip(request),
    )
    return OrganizationRequestSent(message=SENT_MESSAGE)


def _out(item: OrganizationRequest, names: dict[uuid.UUID, str]) -> OrganizationRequestOut:
    return OrganizationRequestOut(
        id=item.id,
        organization_name=item.organization_name,
        contact_name=item.contact_name,
        contact_email=item.contact_email,
        phone=item.phone,
        city_or_agency=item.city_or_agency,
        note=item.note,
        status=item.status,
        created_at=item.created_at,
        decided_at=item.decided_at,
        decided_by_name=names.get(item.decided_by) if item.decided_by else None,
        decision_note=item.decision_note,
        organization_id=item.organization_id,
    )


def _with_link(db: Session, item: OrganizationRequest, link: InvitationLink) -> InvitationLinkOut:
    return InvitationLinkOut(
        request=_out(item, service.decided_by_names(db, [item])),
        invitation_url=link.url,
        invitation_expires_at=link.invitation.expires_at,
    )


@router.get("")
def list_requests(
    request_status: Literal["pending", "approved", "rejected"] = Query("pending", alias="status"),
    _admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> OrganizationRequestList:
    items = service.list_requests(db, request_status)
    names = service.decided_by_names(db, items)
    return OrganizationRequestList(
        items=[_out(item, names) for item in items], pending_count=service.count_pending(db)
    )


@router.post("/{request_id}/approve")
def approve(
    request_id: uuid.UUID,
    body: ApproveRequest,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> InvitationLinkOut:
    item, link = service.approve_request(db, admin, request_id, note=body.note)
    return _with_link(db, item, link)


@router.post("/{request_id}/reject")
def reject(
    request_id: uuid.UUID,
    body: RejectRequest,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> OrganizationRequestOut:
    item = service.reject_request(db, admin, request_id, reason=body.reason)
    return _out(item, service.decided_by_names(db, [item]))


@router.post("/{request_id}/invitation-link")
def new_link(
    request_id: uuid.UUID,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> InvitationLinkOut:
    link = service.new_invitation_link(db, admin, request_id)
    item = db.get(OrganizationRequest, request_id)
    assert item is not None
    return _with_link(db, item, link)
