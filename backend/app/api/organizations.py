"""Organization details, members, invitations, password reset links, and history.

Paths (under /api/v1/organizations/{org_id}): see api-spec.md section 3.3.
Every route goes through `require_org_permission`, the central gatekeeper.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import OrgContext, require_org_permission
from app.core.database import get_db
from app.core.errors import ValidationFailedError
from app.core.permissions import Perm
from app.models import AuditEvent, SeverityRubric, User
from app.schemas.common import Page
from app.schemas.dashboard import Dashboard
from app.schemas.findings import SeverityRubricOut
from app.schemas.organizations import (
    AuditEventOut,
    ChangeRoleRequest,
    InvitationCreate,
    InvitationCreated,
    InvitationOut,
    MemberOut,
    OrganizationOut,
    OrganizationUpdate,
    PasswordResetCreated,
)
from app.schemas.projects import FindingTypeOut
from app.services import accounts, catalog
from app.services import dashboard as dashboard_service
from app.services import findings as findings_service
from app.services.audit import record_event

router = APIRouter(prefix="/organizations/{org_id}", tags=["organizations"])


def _org_out(ctx: OrgContext) -> OrganizationOut:
    org = ctx.organization
    return OrganizationOut(id=org.id, name=org.name, created_at=org.created_at)


@router.get("", response_model=OrganizationOut)
def get_organization(
    ctx: OrgContext = Depends(require_org_permission(Perm.ORG_VIEW)),
) -> OrganizationOut:
    return _org_out(ctx)


@router.patch("", response_model=OrganizationOut)
def update_organization(
    body: OrganizationUpdate,
    ctx: OrgContext = Depends(require_org_permission(Perm.ORG_SETTINGS_EDIT)),
    db: Session = Depends(get_db),
) -> OrganizationOut:
    old_name = ctx.organization.name
    ctx.organization.name = body.name.strip()
    record_event(
        db,
        action="organization.settings_changed",
        organization_id=ctx.organization.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="organization",
        target_id=ctx.organization.id,
        details={"name": {"old": old_name, "new": ctx.organization.name}},
    )
    db.commit()
    return _org_out(ctx)


@router.get("/finding-types", response_model=Page[FindingTypeOut])
def list_finding_types(
    ctx: OrgContext = Depends(require_org_permission(Perm.ORG_VIEW)),
    db: Session = Depends(get_db),
) -> Page[FindingTypeOut]:
    """Problem types this organization uses (placeholders until the customer confirms)."""
    items = [
        FindingTypeOut(
            key=t.key,
            label=t.label,
            source=t.source,
            is_placeholder=t.is_placeholder,
            is_active=t.is_active,
        )
        for t in catalog.list_finding_types(db, ctx.organization.id)
    ]
    return Page(items=items, page=1, page_size=len(items), total=len(items))


@router.get("/severity-rubrics", response_model=Page[SeverityRubricOut])
def list_severity_rubrics(
    ctx: OrgContext = Depends(require_org_permission(Perm.ORG_VIEW)),
    db: Session = Depends(get_db),
) -> Page[SeverityRubricOut]:
    """Every version of the severity scale, newest first. A version is never edited; a
    change creates a new version, so old findings keep the scale they were reviewed with."""
    rubrics = db.scalars(
        select(SeverityRubric)
        .where(SeverityRubric.organization_id == ctx.organization.id)
        .order_by(SeverityRubric.version.desc())
    ).all()
    items = [findings_service.rubric_out(rubric) for rubric in rubrics]
    return Page(items=items, page=1, page_size=len(items), total=len(items))


@router.get("/dashboard", response_model=Dashboard)
def get_dashboard(
    ctx: OrgContext = Depends(require_org_permission(Perm.ORG_VIEW)),
    db: Session = Depends(get_db),
    project_id: uuid.UUID | None = None,
    days: int | None = Query(default=None, description="7, 30 or 90; leave out for all time"),
) -> Dashboard:
    """Numbers and chart data for the Overview, across the projects this person can see
    (or one project). Every number follows the person's permissions on each project."""
    if days is not None and days not in (7, 30, 90):
        raise ValidationFailedError("Choose 7, 30 or 90 days, or leave it out for all time.")
    return dashboard_service.build(db, ctx, project_id=project_id, days=days)


# ------------------------------------------------------------------------ members
@router.get("/members", response_model=Page[MemberOut])
def list_members(
    ctx: OrgContext = Depends(require_org_permission(Perm.ORG_MEMBERS_VIEW)),
    db: Session = Depends(get_db),
) -> Page[MemberOut]:
    items = [
        MemberOut(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            org_role=membership.org_role,
            is_active=user.is_active,
            joined_at=membership.created_at,
        )
        for user, membership in accounts.list_members(db, ctx.organization.id)
    ]
    return Page(items=items, page=1, page_size=len(items), total=len(items))


@router.patch("/members/{user_id}", response_model=MemberOut)
def change_member_role(
    user_id: uuid.UUID,
    body: ChangeRoleRequest,
    ctx: OrgContext = Depends(require_org_permission(Perm.ORG_MEMBERS_CHANGE_ROLE)),
    db: Session = Depends(get_db),
) -> MemberOut:
    membership = accounts.change_member_role(db, ctx, user_id, body.org_role)
    db.commit()
    user = db.get(User, user_id)
    assert user is not None
    return MemberOut(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        org_role=membership.org_role,
        is_active=user.is_active,
        joined_at=membership.created_at,
    )


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: uuid.UUID,
    ctx: OrgContext = Depends(require_org_permission(Perm.ORG_MEMBERS_REMOVE)),
    db: Session = Depends(get_db),
) -> Response:
    accounts.remove_member(db, ctx, user_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/members/{user_id}/password-reset",
    response_model=PasswordResetCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_password_reset(
    user_id: uuid.UUID,
    ctx: OrgContext = Depends(require_org_permission(Perm.ORG_MEMBERS_RESET_PASSWORD)),
    db: Session = Depends(get_db),
) -> PasswordResetCreated:
    link = accounts.create_password_reset(db, ctx, user_id)
    db.commit()
    return PasswordResetCreated(reset_url=link.url, expires_at=link.reset.expires_at)


# -------------------------------------------------------------------- invitations
@router.get("/invitations", response_model=Page[InvitationOut])
def list_invitations(
    ctx: OrgContext = Depends(require_org_permission(Perm.ORG_MEMBERS_INVITE)),
    db: Session = Depends(get_db),
) -> Page[InvitationOut]:
    items = [
        InvitationOut.model_validate(invitation)
        for invitation in accounts.list_pending_invitations(db, ctx.organization.id)
    ]
    return Page(items=items, page=1, page_size=len(items), total=len(items))


@router.post("/invitations", response_model=InvitationCreated, status_code=status.HTTP_201_CREATED)
def create_invitation(
    body: InvitationCreate,
    ctx: OrgContext = Depends(require_org_permission(Perm.ORG_MEMBERS_INVITE)),
    db: Session = Depends(get_db),
) -> InvitationCreated:
    link = accounts.create_invitation(db, ctx, body.email, body.org_role)
    db.commit()
    base = InvitationOut.model_validate(link.invitation)
    return InvitationCreated(**base.model_dump(), invite_url=link.url)


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(
    invitation_id: uuid.UUID,
    ctx: OrgContext = Depends(require_org_permission(Perm.ORG_MEMBERS_INVITE)),
    db: Session = Depends(get_db),
) -> Response:
    accounts.revoke_invitation(db, ctx, invitation_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------------ history
@router.get("/audit-events", response_model=Page[AuditEventOut])
def list_audit_events(
    ctx: OrgContext = Depends(require_org_permission(Perm.ORG_AUDIT_VIEW)),
    db: Session = Depends(get_db),
    action: str | None = Query(default=None, max_length=80),
    actor_user_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[AuditEventOut]:
    conditions = [AuditEvent.organization_id == ctx.organization.id]
    if action:
        conditions.append(AuditEvent.action == action)
    if actor_user_id:
        conditions.append(AuditEvent.actor_user_id == actor_user_id)
    if since:
        conditions.append(AuditEvent.created_at >= since)
    if until:
        conditions.append(AuditEvent.created_at < until)

    total = db.scalar(select(func.count()).select_from(AuditEvent).where(*conditions)) or 0
    rows = db.execute(
        select(AuditEvent, User.email)
        .outerjoin(User, User.id == AuditEvent.actor_user_id)
        .where(*conditions)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        AuditEventOut(
            id=event.id,
            action=event.action,
            actor_user_id=event.actor_user_id,
            actor_email=email,
            actor_roles=event.actor_roles,
            target_type=event.target_type,
            target_id=event.target_id,
            details=event.details,
            request_id=event.request_id,
            created_at=event.created_at,
        )
        for event, email in rows
    ]
    return Page(items=items, page=page, page_size=page_size, total=total)
