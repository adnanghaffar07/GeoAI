"""The operator command that creates an organization and its first admin."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli import CommandError, create_organization, main
from app.models import AuditEvent, OrganizationMembership, User


def test_creates_organization_admin_and_history(db: Session) -> None:
    org = create_organization(
        db,
        name="  City Road Department ",
        admin_email="Admin@City.test",
        admin_name="Ada",
        admin_password="long-enough-password",
    )

    user = db.scalar(select(User))
    membership = db.scalar(select(OrganizationMembership))
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "organization.created"))
    assert org.name == "City Road Department"
    assert user is not None and user.email == "admin@city.test"
    assert membership is not None and membership.org_role == "org_admin"
    assert event is not None and event.organization_id == org.id


def test_refuses_duplicate_email(db: Session) -> None:
    create_organization(
        db, name="A", admin_email="a@x.test", admin_name="A", admin_password="long-enough-password"
    )

    with pytest.raises(CommandError, match="already exists"):
        create_organization(
            db,
            name="B",
            admin_email="A@x.test",
            admin_name="B",
            admin_password="long-enough-password",
        )


def test_refuses_short_password(db: Session) -> None:
    with pytest.raises(CommandError, match="characters"):
        create_organization(
            db, name="A", admin_email="a@x.test", admin_name="A", admin_password="short"
        )


def test_command_line_reports_mismatched_passwords(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter(["first-password-1", "second-password-2"])
    monkeypatch.setattr("getpass.getpass", lambda _prompt: next(answers))

    exit_code = main(
        ["create-organization", "--name", "A", "--admin-email", "a@x.test", "--admin-name", "A"]
    )

    assert exit_code == 1
    assert "do not match" in capsys.readouterr().err
