"""Operator commands, run on the server (not from the app's screens).

Create a new organization and its first administrator:

    docker compose exec api python -m app.cli create-organization \\
        --name "City Road Department" --admin-email admin@example.com --admin-name "Ada Admin"

The password is asked for twice and never shown or stored in plain text.

Make an existing account a platform admin (CR-004; it can review requests from new
organizations). Add --remove to take the role away again:

    docker compose exec api python -m app.cli make-platform-admin --email admin@example.com

This is the pilot's way of adding organizations (see project-decisions.md: the
delivery model and main-admin sign-in method can change later).
"""

import argparse
import getpass
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_session_factory
from app.core.security import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    hash_password,
    normalize_email,
)
from app.models import Organization, OrganizationMembership, User
from app.services.audit import record_event
from app.services.catalog import seed_placeholder_settings


class CommandError(Exception):
    """A problem the operator can fix; printed without a traceback."""


def create_organization(
    db: Session, *, name: str, admin_email: str, admin_name: str, admin_password: str
) -> Organization:
    """Create an organization and its first org admin in one transaction (commits)."""
    name = name.strip()
    admin_email = normalize_email(admin_email)
    if not name:
        raise CommandError("Organization name is required.")
    if "@" not in admin_email:
        raise CommandError("Admin email looks invalid.")
    if not PASSWORD_MIN_LENGTH <= len(admin_password) <= PASSWORD_MAX_LENGTH:
        raise CommandError(
            f"Password must be {PASSWORD_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} characters."
        )
    if db.scalar(select(User.id).where(func.lower(User.email) == admin_email)):
        raise CommandError(
            f"A user with email {admin_email} already exists. Use a different email, "
            "or invite that person from the existing organization."
        )

    organization = Organization(name=name)
    user = User(
        email=admin_email,
        full_name=admin_name.strip() or admin_email,
        password_hash=hash_password(admin_password),
    )
    db.add_all([organization, user])
    db.flush()
    db.add(
        OrganizationMembership(
            organization_id=organization.id, user_id=user.id, org_role="org_admin"
        )
    )
    seed_placeholder_settings(db, organization.id)
    record_event(
        db,
        action="organization.created",
        organization_id=organization.id,
        actor_user_id=None,
        details={"name": name, "first_admin_email": admin_email, "via": "cli"},
    )
    db.commit()
    return organization


def set_platform_admin(db: Session, *, email: str, enabled: bool) -> tuple[User, bool]:
    """Give (or take away) the platform admin role. Commits.

    Returns the user and whether anything changed (running it twice is harmless)."""
    email = normalize_email(email)
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        raise CommandError(
            f"No account with email {email}. "
            "Create it first (create-organization or an invitation)."
        )
    if not user.is_active:
        raise CommandError(f"The account {email} is deactivated. Reactivate it first.")
    if user.is_platform_admin == enabled:
        return user, False
    user.is_platform_admin = enabled
    record_event(
        db,
        action="user.platform_admin_granted" if enabled else "user.platform_admin_removed",
        organization_id=None,
        actor_user_id=None,
        target_type="user",
        target_id=user.id,
        details={"email": email, "via": "cli"},
    )
    db.commit()
    return user, True


def _ask_password() -> str:
    first = getpass.getpass("Password for the admin: ")
    second = getpass.getpass("Repeat the password: ")
    if first != second:
        raise CommandError("The two passwords do not match.")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-organization", help="Create an organization and first admin")
    create.add_argument("--name", required=True, help="Organization name")
    create.add_argument("--admin-email", required=True)
    create.add_argument("--admin-name", required=True)
    platform = sub.add_parser(
        "make-platform-admin", help="Make an existing account a platform admin"
    )
    platform.add_argument("--email", required=True)
    platform.add_argument("--remove", action="store_true", help="Take the role away instead")
    args = parser.parse_args(argv)

    if args.command == "make-platform-admin":
        return _platform_admin_command(args.email, enabled=not args.remove)

    try:
        password = _ask_password()
        with get_session_factory()() as db:
            org = create_organization(
                db,
                name=args.name,
                admin_email=args.admin_email,
                admin_name=args.admin_name,
                admin_password=password,
            )
    except CommandError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Created organization '{org.name}' ({org.id}).")
    print(f"The admin can now sign in with {normalize_email(args.admin_email)}.")
    return 0


def _platform_admin_command(email: str, *, enabled: bool) -> int:
    try:
        with get_session_factory()() as db:
            user, changed = set_platform_admin(db, email=email, enabled=enabled)
    except CommandError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    role = "is now a platform admin" if enabled else "is no longer a platform admin"
    if not changed:
        role = "was already a platform admin" if enabled else "was not a platform admin"
    print(f"{user.email} {role}.")
    if changed:
        print("They may need to sign out and in again to see the change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
