"""The permission policy itself (no database). Locks in the owner's accepted decisions."""

from app.core.permissions import (
    CONDITIONS,
    ORG_ADMIN_PROJECT_PERMISSIONS,
    ORG_ROLE_PERMISSIONS,
    PROJECT_ROLE_PERMISSIONS,
    Perm,
    org_permissions,
    project_permissions,
)
from app.models import ORG_ROLES

ALL_KEYS = {value for name, value in vars(Perm).items() if name.isupper()}


def test_every_granted_key_is_a_defined_permission() -> None:
    granted = set().union(*ORG_ROLE_PERMISSIONS.values(), *PROJECT_ROLE_PERMISSIONS.values())
    assert granted <= ALL_KEYS
    assert {key for _, key in CONDITIONS} <= ALL_KEYS


def test_policy_covers_exactly_the_stored_org_roles() -> None:
    assert set(ORG_ROLE_PERMISSIONS) == set(ORG_ROLES)


def test_unknown_role_gets_nothing() -> None:
    assert org_permissions("superuser") == frozenset()
    assert project_permissions(["superuser"], None) == frozenset()


def test_only_technical_reviewers_can_review() -> None:
    """Decision Q3."""
    for role, keys in PROJECT_ROLE_PERMISSIONS.items():
        assert (Perm.FINDING_REVIEW in keys) == (role == "technical_reviewer")
    assert Perm.FINDING_REVIEW not in ORG_ADMIN_PROJECT_PERMISSIONS


def test_project_roles_combine() -> None:
    """Decision Q2: a manager who is also a reviewer gets both sets."""
    combined = project_permissions(["project_manager", "technical_reviewer"], "org_member")
    assert Perm.FINDING_REVIEW in combined
    assert Perm.REPORT_GENERATE in combined


def test_org_admin_manages_every_project_without_membership() -> None:
    assert Perm.PROJECT_EDIT in project_permissions([], "org_admin")
    assert project_permissions([], "org_member") == frozenset()


def test_viewers_are_read_only() -> None:
    viewer = PROJECT_ROLE_PERMISSIONS["viewer"]
    writes = {
        Perm.IMAGE_UPLOAD,
        Perm.FINDING_REVIEW,
        Perm.FINDING_CREATE_MANUAL,
        Perm.REPORT_GENERATE,
        Perm.PROJECT_EDIT,
    }
    assert not viewer & writes


def test_project_creation_is_for_admins_and_managers() -> None:
    """Decision Q1."""
    assert Perm.PROJECT_CREATE in org_permissions("org_admin")
    assert Perm.PROJECT_CREATE in org_permissions("org_manager")
    assert Perm.PROJECT_CREATE not in org_permissions("org_member")
