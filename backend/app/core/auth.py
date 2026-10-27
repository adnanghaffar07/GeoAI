"""The central gatekeeper: who is signed in, and are they allowed?

Every protected route uses one of these FastAPI dependencies:

- `get_current_user`: requires a valid session. Otherwise `401 not_authenticated`.
- `require_org_permission(key)`: requires membership of the organization in the URL
  and the given permission key. Not a member: `404 not_found` (the organization's
  existence is not revealed). Member without the permission: `403 permission_denied`.

- `require_project_permission(key)`: requires access to the project in the URL
  (org admin of its organization, or at least one project role) and the key.
  No access: `404`. Access without the key: `403`.

Some permissions are granted with a condition (e.g. collectors: own uploads only).
`ProjectContext.is_unconditional(key)` tells feature code whether to apply it.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Path, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import NotAuthenticatedError, NotFoundError, PermissionDeniedError
from app.core.permissions import (
    CONDITIONS,
    ORG_ADMIN_PROJECT_PERMISSIONS,
    org_permissions,
    project_permissions,
)
from app.models import (
    Organization,
    OrganizationMembership,
    Project,
    ProjectMember,
    User,
    UserSession,
)
from app.services.sessions import extend_if_due, find_active_session


@dataclass(frozen=True)
class CurrentUser:
    user: User
    session: UserSession


@dataclass(frozen=True)
class OrgContext:
    """Everything a route needs to know about the caller within one organization."""

    user: User
    organization: Organization
    membership: OrganizationMembership
    permissions: frozenset[str]

    @property
    def actor_roles(self) -> list[str]:
        return [self.membership.org_role]


def get_current_user(request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise NotAuthenticatedError()
    found = find_active_session(db, token)
    if found is None:
        raise NotAuthenticatedError("Your session has ended. Please sign in again.")
    session, user = found
    extend_if_due(db, session)
    return CurrentUser(user=user, session=session)


def load_org_context(db: Session, user: User, org_id: uuid.UUID) -> OrgContext:
    """Load the caller's membership in an organization, or raise 404."""
    row = db.execute(
        select(Organization, OrganizationMembership)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(Organization.id == org_id, OrganizationMembership.user_id == user.id)
    ).first()
    if row is None:
        raise NotFoundError("Organization not found.")
    organization, membership = row
    return OrgContext(
        user=user,
        organization=organization,
        membership=membership,
        permissions=org_permissions(membership.org_role),
    )


def require_org_permission(permission: str) -> Callable[..., OrgContext]:
    """Dependency factory: `ctx: OrgContext = Depends(require_org_permission(Perm.X))`."""

    def dependency(
        org_id: uuid.UUID = Path(),
        current: CurrentUser = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> OrgContext:
        ctx = load_org_context(db, current.user, org_id)
        if permission not in ctx.permissions:
            raise PermissionDeniedError()
        return ctx

    return dependency


@dataclass(frozen=True)
class ProjectContext:
    """The caller's access to one project."""

    user: User
    project: Project
    org_role: str
    project_roles: tuple[str, ...]
    permissions: frozenset[str]

    @property
    def actor_roles(self) -> list[str]:
        return sorted({self.org_role, *self.project_roles})

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    def is_unconditional(self, permission: str) -> bool:
        """True if some role grants `permission` without a condition such as "own uploads"."""
        if self.org_role == "org_admin" and permission in ORG_ADMIN_PROJECT_PERMISSIONS:
            return True
        return any(
            permission in project_permissions([role], None) and (role, permission) not in CONDITIONS
            for role in self.project_roles
        )


def load_project_context(db: Session, user: User, project_id: uuid.UUID) -> ProjectContext:
    """Load the caller's access to a project, or raise 404 if they have none."""
    row = db.execute(
        select(Project, OrganizationMembership.org_role)
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == Project.organization_id,
        )
        .where(Project.id == project_id, OrganizationMembership.user_id == user.id)
    ).first()
    if row is None:
        raise NotFoundError("Project not found.")
    project, org_role = row
    roles = tuple(
        sorted(
            db.scalars(
                select(ProjectMember.role).where(
                    ProjectMember.project_id == project.id, ProjectMember.user_id == user.id
                )
            ).all()
        )
    )
    if org_role != "org_admin" and not roles:
        raise NotFoundError("Project not found.")
    return ProjectContext(
        user=user,
        project=project,
        org_role=org_role,
        project_roles=roles,
        permissions=project_permissions(roles, org_role),
    )


def require_project_permission(permission: str) -> Callable[..., ProjectContext]:
    """Dependency factory: `ctx: ProjectContext = Depends(require_project_permission(P.X))`."""

    def dependency(
        project_id: uuid.UUID = Path(),
        current: CurrentUser = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> ProjectContext:
        ctx = load_project_context(db, current.user, project_id)
        if permission not in ctx.permissions:
            raise PermissionDeniedError()
        return ctx

    return dependency
