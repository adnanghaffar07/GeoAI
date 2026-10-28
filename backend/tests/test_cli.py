"""The operator command that creates an organization and its first admin."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli import CommandError, create_organization, main, set_platform_admin
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


def _account(db: Session, email: str = "boss@x.test") -> User:
    create_organization(
        db, name="Org", admin_email=email, admin_name="Boss", admin_password="long-enough-password"
    )
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    return user


def test_accounts_are_not_platform_admins_by_default(db: Session) -> None:
    assert _account(db).is_platform_admin is False


def test_makes_an_existing_account_platform_admin_and_records_it(db: Session) -> None:
    user = _account(db)

    _, changed = set_platform_admin(db, email="BOSS@x.test", enabled=True)

    db.refresh(user)
    assert changed and user.is_platform_admin is True
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "user.platform_admin_granted"))
    assert event is not None and event.target_id == user.id and event.organization_id is None
    # Running it again changes nothing and records nothing new.
    assert set_platform_admin(db, email="boss@x.test", enabled=True)[1] is False


def test_can_take_the_role_away(db: Session) -> None:
    user = _account(db)
    set_platform_admin(db, email="boss@x.test", enabled=True)

    set_platform_admin(db, email="boss@x.test", enabled=False)

    db.refresh(user)
    assert user.is_platform_admin is False


def test_refuses_unknown_or_deactivated_accounts(db: Session) -> None:
    with pytest.raises(CommandError, match="No account"):
        set_platform_admin(db, email="nobody@x.test", enabled=True)
    user = _account(db)
    user.is_active = False
    db.commit()
    with pytest.raises(CommandError, match="deactivated"):
        set_platform_admin(db, email="boss@x.test", enabled=True)


def test_command_line_makes_platform_admin(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _account(db)
    monkeypatch.setattr("app.cli.get_session_factory", lambda: lambda: db)

    exit_code = main(["make-platform-admin", "--email", "boss@x.test"])

    assert exit_code == 0
    assert "is now a platform admin" in capsys.readouterr().out
