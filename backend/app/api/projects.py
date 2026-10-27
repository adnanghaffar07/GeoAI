"""Projects and project teams (api-spec.md section 3.4).

Every route goes through the central gatekeeper: `require_org_permission` for creating
and listing, `require_project_permission` for everything inside a project.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import (
    OrgContext,
    ProjectContext,
    require_org_permission,
    require_project_permission,
)
from app.core.database import get_db
from app.core.permissions import Perm, project_permissions
from app.models import AuditEvent, Project, User
from app.schemas.common import Page
from app.schemas.organizations import AuditEventOut
from app.schemas.projects import (
    EligibleMember,
    ProjectCounts,
    ProjectCreate,
    ProjectDetail,
    ProjectMemberCreate,
    ProjectMemberOut,
    ProjectSummary,
    ProjectUpdate,
)
from app.services import projects as service

org_router = APIRouter(prefix="/organizations/{org_id}/projects", tags=["projects"])
router = APIRouter(prefix="/projects/{project_id}", tags=["projects"])


def _summary(
    project: Project, roles: list[str], counts: service.Counts, org_role: str
) -> ProjectSummary:
    # Numbers about things a person may not see are not shown to them (decision Q5).
    permissions = project_permissions(roles, org_role)
    if Perm.FINDING_VIEW_CANDIDATES not in permissions:
        counts.findings_to_review = 0
        counts.findings_needs_field_check = 0
    if Perm.PRIORITY_VIEW not in permissions:
        counts.inspections_open = 0
    return ProjectSummary(
        id=project.id,
        organization_id=project.organization_id,
        name=project.name,
        archived=project.archived_at is not None,
        created_at=project.created_at,
        my_roles=roles,
        counts=ProjectCounts(**vars(counts)),
    )


def _detail(db: Session, ctx: ProjectContext) -> ProjectDetail:
    project = ctx.project
    counts = service.project_counts(db, [project.id])[project.id]
    summary = _summary(project, list(ctx.project_roles), counts, ctx.org_role)
    return ProjectDetail(
        **summary.model_dump(),
        boundary=service.boundary_geojson(db, project.id),
        finding_type_keys=project.finding_type_keys,
        road_category=project.road_category,
        survey_start=project.survey_start,
        survey_end=project.survey_end,
        partner_reference=project.partner_reference,
        archived_at=project.archived_at,
        my_permissions=sorted(ctx.permissions),
    )


# ------------------------------------------------------------- organization level
@org_router.get("", response_model=Page[ProjectSummary])
def list_projects(
    ctx: OrgContext = Depends(require_org_permission(Perm.ORG_VIEW)),
    db: Session = Depends(get_db),
    include_archived: bool = False,
) -> Page[ProjectSummary]:
    """Projects the caller can see: all of them for org admins, otherwise their own."""
    visible = service.visible_projects(db, ctx.user, ctx, include_archived=include_archived)
    counts = service.project_counts(db, [project.id for project, _ in visible])
    items = [
        _summary(project, roles, counts[project.id], ctx.membership.org_role)
        for project, roles in visible
    ]
    return Page(items=items, page=1, page_size=len(items), total=len(items))


@org_router.post("", response_model=ProjectSummary, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    ctx: OrgContext = Depends(require_org_permission(Perm.PROJECT_CREATE)),
    db: Session = Depends(get_db),
) -> ProjectSummary:
    project = service.create_project(db, ctx, body)
    db.commit()
    roles = ["project_manager"] + (
        ["technical_reviewer"] if ctx.user.id in body.reviewer_user_ids else []
    )
    return _summary(project, sorted(roles), service.Counts(0, 0, 0), ctx.membership.org_role)


# ------------------------------------------------------------------ project level
@router.get("", response_model=ProjectDetail)
def get_project(
    ctx: ProjectContext = Depends(require_project_permission(Perm.PROJECT_VIEW)),
    db: Session = Depends(get_db),
) -> ProjectDetail:
    return _detail(db, ctx)


@router.patch("", response_model=ProjectDetail)
def update_project(
    body: ProjectUpdate,
    ctx: ProjectContext = Depends(require_project_permission(Perm.PROJECT_EDIT)),
    db: Session = Depends(get_db),
) -> ProjectDetail:
    service.update_project(db, ctx, body)
    db.commit()
    db.refresh(ctx.project)
    return _detail(db, ctx)


@router.post("/archive", response_model=ProjectDetail)
def archive_project(
    ctx: ProjectContext = Depends(require_project_permission(Perm.PROJECT_ARCHIVE)),
    db: Session = Depends(get_db),
) -> ProjectDetail:
    service.archive_project(db, ctx)
    db.commit()
    return _detail(db, ctx)


@router.get("/members", response_model=Page[ProjectMemberOut])
def list_members(
    ctx: ProjectContext = Depends(require_project_permission(Perm.PROJECT_VIEW)),
    db: Session = Depends(get_db),
) -> Page[ProjectMemberOut]:
    items = [
        ProjectMemberOut(
            id=member.id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=member.role,
            added_at=member.created_at,
        )
        for member, user in service.list_project_members(db, ctx.project.id)
    ]
    return Page(items=items, page=1, page_size=len(items), total=len(items))


@router.get("/eligible-members", response_model=Page[EligibleMember])
def list_eligible_members(
    ctx: ProjectContext = Depends(require_project_permission(Perm.PROJECT_MEMBERS_MANAGE)),
    db: Session = Depends(get_db),
) -> Page[EligibleMember]:
    """Organization members who can be given a role on this project (change CR-002)."""
    items = [
        EligibleMember(user_id=user.id, email=user.email, full_name=user.full_name, org_role=role)
        for user, role in service.eligible_members(db, ctx.project.organization_id)
    ]
    return Page(items=items, page=1, page_size=len(items), total=len(items))


@router.post("/members", response_model=ProjectMemberOut, status_code=status.HTTP_201_CREATED)
def add_member(
    body: ProjectMemberCreate,
    ctx: ProjectContext = Depends(require_project_permission(Perm.PROJECT_MEMBERS_MANAGE)),
    db: Session = Depends(get_db),
) -> ProjectMemberOut:
    member = service.add_project_member(db, ctx, body.user_id, body.role)
    db.commit()
    user = db.get(User, member.user_id)
    assert user is not None
    return ProjectMemberOut(
        id=member.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=member.role,
        added_at=member.created_at,
    )


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    member_id: uuid.UUID,
    ctx: ProjectContext = Depends(require_project_permission(Perm.PROJECT_MEMBERS_MANAGE)),
    db: Session = Depends(get_db),
) -> Response:
    service.remove_project_member(db, ctx, member_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/audit-events", response_model=Page[AuditEventOut])
def list_project_audit_events(
    ctx: ProjectContext = Depends(require_project_permission(Perm.PROJECT_AUDIT_VIEW)),
    db: Session = Depends(get_db),
    action: str | None = Query(default=None, max_length=80),
    actor_user_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[AuditEventOut]:
    """History of this project: who did what and when (FR-53)."""
    conditions = [AuditEvent.project_id == ctx.project.id]
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
