"""The demo data script builds a full, clearly labelled DEMO organization, and only once."""

import datetime as dt

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import demo_data
from app.cli import CommandError
from app.demo_data import ORG_NAME, build
from app.models import Finding, Image, Inspection, Organization, Project, Report, User

PASSWORD = "demo-password-123"


class _FixedDate(dt.date):
    """The demo stamps photos with dates counted back from today, and the TEST DETECTOR's
    made-up results depend on the photo file, so the number of suggestions changed from day
    to day. A fixed "today" makes the test repeatable."""

    @classmethod
    def today(cls) -> "_FixedDate":
        return cls(2026, 10, 15)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(demo_data, "date", _FixedDate)


def test_demo_data_builds_every_stage_and_runs_only_once(db: Session) -> None:
    build(db, PASSWORD)

    org = db.scalar(select(Organization).where(Organization.name == ORG_NAME))
    assert org is not None
    projects = list(db.scalars(select(Project).where(Project.organization_id == org.id)))
    assert len(projects) == 3 and all(p.name.startswith("DEMO") for p in projects)
    assert (
        db.scalar(select(func.count()).select_from(User).where(User.email.like("%@demo-city.test")))
        == 5
    )
    assert db.scalar(select(func.count()).select_from(Image)) == 15
    statuses = set(db.scalars(select(Finding.review_status)))
    assert {"ai_generated", "verified", "rejected", "needs_field_check"} <= statuses
    assert (
        db.scalar(select(func.count()).select_from(Finding).where(Finding.origin == "manual")) == 1
    )
    inspection_states = set(db.scalars(select(Inspection.status)))
    assert {"planned", "resolved", "reopened"} <= inspection_states
    reports = list(db.scalars(select(Report)))
    assert sorted(r.format for r in reports) == ["csv", "geojson", "pdf"]
    assert all(r.status == "completed" for r in reports)
    assert any(r.shared_with_viewers for r in reports)

    with pytest.raises(CommandError, match="already exists"):
        build(db, PASSWORD)


def test_short_password_is_refused(db: Session) -> None:
    with pytest.raises(CommandError, match="Password"):
        build(db, "short")
