"""Fill the app with clearly labelled DEMO data, for demonstrations and manual testing.

(Uses `random` only to draw dummy pictures and positions: not for anything secret.)

Run once (it asks for the password of the demo users):

    docker compose exec api python -m app.demo_data

It creates a separate organization "DEMO City" with demo users in every role, 3 projects
in San Francisco with 5 generated road photos each, AI analysis (test detector), reviews,
inspection priority, inspections and reports. It goes through the same service code as the
app, so every rule (permissions, history, versions) applies.

Everything here is made up: the photos are drawn by this script and their GPS positions are
placed inside the demo areas. Nothing is real data. Running it a second time is refused, so
nothing is duplicated.
"""

import argparse
import getpass
import io
import math
import os
import random
import sys
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
from PIL.TiffImagePlugin import IFDRational
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli import CommandError, create_organization
from app.core.auth import OrgContext, ProjectContext, load_org_context, load_project_context
from app.core.database import get_session_factory
from app.core.security import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, hash_password
from app.models import Finding, Organization, OrganizationMembership, User
from app.schemas.findings import ManualFindingCreate, ReviewRequest
from app.schemas.images import LatLon
from app.schemas.priority import (
    InspectionPlan,
    InspectionReopen,
    InspectionUpdate,
    PriorityConfigIn,
)
from app.schemas.projects import ProjectCreate
from app.schemas.reports import ReportFilters, ReportRequest
from app.services import analysis, findings, images, inspections, priority, projects, reports

ORG_NAME = "DEMO City"
EMAIL_DOMAIN = "demo-city.test"
PEOPLE = {
    # key: (name, org role, project roles)
    "admin": ("Dana Admin (demo)", "org_admin", []),
    "manager": ("Maya Manager (demo)", "org_member", ["project_manager"]),
    "reviewer": ("Ravi Reviewer (demo)", "org_member", ["technical_reviewer"]),
    "collector": ("Cole Collector (demo)", "org_member", ["field_collector"]),
    "viewer": ("Vera Viewer (demo)", "org_member", ["viewer"]),
}
TYPES = ["pothole", "surface_cracking", "pavement_deterioration"]


@dataclass
class Area:
    name: str
    road_category: str | None
    west: float
    south: float
    east: float
    north: float

    def polygon(self) -> dict[str, Any]:
        w, s, e, n = self.west, self.south, self.east, self.north
        return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}

    def point(self, rng: random.Random) -> tuple[float, float]:
        """A made-up position inside the area (latitude, longitude)."""
        return (
            rng.uniform(self.south + 0.0005, self.north - 0.0005),
            rng.uniform(self.west + 0.0005, self.east - 0.0005),
        )


PROJECTS = [
    Area("DEMO - Mission District streets", "arterial", -122.4230, 37.7560, -122.4130, 37.7650),
    Area("DEMO - Sunset residential roads", "local", -122.4950, 37.7520, -122.4830, 37.7600),
    Area("DEMO - Downtown survey (no road category)", None, -122.4080, 37.7850, -122.3990, 37.7920),
]


# ----------------------------------------------------------------- generated photos
def _dms(value: float) -> tuple[IFDRational, IFDRational, IFDRational]:
    value = abs(value)
    degrees = int(value)
    minutes = int((value - degrees) * 60)
    seconds = round(((value - degrees) * 60 - minutes) * 60, 4)
    return IFDRational(degrees), IFDRational(minutes), IFDRational(seconds)


def road_photo(seed: int, *, gps: tuple[float, float] | None, kind: str = "normal") -> bytes:
    """A drawn road photo: asphalt, lane markings, cracks and potholes. Dummy data only."""
    rng = random.Random(seed)
    width, height = 1280, 960
    photo = Image.new("RGB", (width, height), (108, 110, 112))
    draw = ImageDraw.Draw(photo)
    # Asphalt grain.
    for _ in range(26000):
        x, y = rng.randrange(width), rng.randrange(height)
        shade = rng.randint(70, 150)
        draw.point((x, y), fill=(shade, shade, shade + rng.randint(-4, 4)))
    # Sky band and kerb, so it looks like a road photo taken from a car.
    draw.rectangle((0, 0, width, 250), fill=(176, 200, 222))
    draw.polygon([(0, 250), (width, 250), (width, 300), (0, 330)], fill=(150, 146, 136))
    # Lane markings in perspective.
    for i in range(6):
        top = 330 + i * 110
        draw.polygon(
            [
                (630 - 4 - i * 3, top),
                (650 + 4 + i * 3, top),
                (655 + 6 + i * 4, top + 60),
                (625 - 6 - i * 4, top + 60),
            ],
            fill=(232, 196, 40),
        )
    # Cracks.
    for _ in range(rng.randint(2, 5)):
        x, y = rng.randint(80, width - 80), rng.randint(380, height - 60)
        points = [(x, y)]
        for _ in range(rng.randint(6, 14)):
            x += rng.randint(-40, 40)
            y += rng.randint(-25, 25)
            points.append((x, y))
        draw.line(points, fill=(38, 38, 40), width=rng.randint(2, 5))
    # Potholes.
    for _ in range(rng.randint(1, 3)):
        cx, cy = rng.randint(150, width - 150), rng.randint(450, height - 120)
        rx, ry = rng.randint(50, 120), rng.randint(25, 60)
        draw.ellipse((cx - rx - 8, cy - ry - 6, cx + rx + 8, cy + ry + 6), fill=(140, 136, 128))
        draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=(48, 46, 44))
        for _ in range(12):
            angle = rng.uniform(0, 2 * math.pi)
            px, py = cx + math.cos(angle) * rx * 0.6, cy + math.sin(angle) * ry * 0.6
            draw.ellipse((px - 6, py - 4, px + 6, py + 4), fill=(80, 78, 74))
    # Fine grain over the whole road, like real asphalt texture (keeps sharp photos sharp).
    pixels = np.asarray(photo, dtype=np.int16)
    noise = np.random.default_rng(seed).integers(-38, 39, size=pixels.shape[:2], dtype=np.int16)
    photo = Image.fromarray(np.clip(pixels + noise[:, :, None], 0, 255).astype(np.uint8))
    if kind == "blurry":
        photo = photo.filter(ImageFilter.GaussianBlur(14))
    elif kind == "dark":
        photo = ImageEnhance.Brightness(photo).enhance(0.07)

    exif = Image.Exif()
    exif[0x010F] = "DEMO camera"  # make
    if gps is not None:
        latitude, longitude = gps
        exif.get_ifd(0x8825).update(
            {
                1: "N" if latitude >= 0 else "S",
                2: _dms(latitude),
                3: "E" if longitude >= 0 else "W",
                4: _dms(longitude),
            }
        )
    taken = date.today() - timedelta(days=rng.randint(1, 20))
    exif.get_ifd(0x8769)[0x9003] = (
        f"{taken:%Y:%m:%d} {rng.randint(8, 17):02d}:{rng.randint(0, 59):02d}:00"
    )
    exif.get_ifd(0x8769)[0x9011] = "-07:00"
    buffer = io.BytesIO()
    photo.save(buffer, format="JPEG", quality=88, exif=exif)
    return buffer.getvalue()


def evidence_photo(seed: int) -> bytes:
    """A drawn "after repair" photo for a resolved inspection."""
    rng = random.Random(seed)
    photo = Image.new("RGB", (800, 600), (96, 98, 100))
    draw = ImageDraw.Draw(photo)
    for _ in range(9000):
        shade = rng.randint(70, 130)
        draw.point((rng.randrange(800), rng.randrange(600)), fill=(shade, shade, shade))
    draw.ellipse((260, 230, 540, 380), fill=(40, 40, 42))  # fresh patch
    buffer = io.BytesIO()
    photo.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


# ----------------------------------------------------------------- helpers
class Demo:
    def __init__(self, db: Session, password: str) -> None:
        self.db = db
        self.password = password
        self.users: dict[str, User] = {}
        self.log: list[str] = []

    def say(self, text: str) -> None:
        print(f"  - {text}")

    def org_ctx(self, key: str) -> OrgContext:
        return load_org_context(self.db, self.users[key], self.org.id)

    def ctx(self, key: str, project_id: uuid.UUID) -> ProjectContext:
        return load_project_context(self.db, self.users[key], project_id)

    # people -------------------------------------------------------------
    def create_people(self) -> None:
        create_organization(
            self.db,
            name=ORG_NAME,
            admin_email=f"admin@{EMAIL_DOMAIN}",
            admin_name=PEOPLE["admin"][0],
            admin_password=self.password,
        )
        org = self.db.scalar(select(Organization).where(Organization.name == ORG_NAME))
        assert org is not None
        self.org = org
        self.users["admin"] = self.db.scalar(
            select(User).where(User.email == f"admin@{EMAIL_DOMAIN}")
        )  # type: ignore[assignment]
        for key, (name, org_role, _) in PEOPLE.items():
            if key == "admin":
                continue
            user = User(
                email=f"{key}@{EMAIL_DOMAIN}",
                full_name=name,
                password_hash=hash_password(self.password),
            )
            self.db.add(user)
            self.db.flush()
            self.db.add(
                OrganizationMembership(organization_id=org.id, user_id=user.id, org_role=org_role)
            )
            self.users[key] = user
        self.db.commit()
        self.say(f"organization '{ORG_NAME}' with 5 demo users")

    # one project ----------------------------------------------------------
    def create_project(self, number: int, area: Area) -> uuid.UUID:
        project = projects.create_project(
            self.db,
            self.org_ctx("admin"),
            ProjectCreate(
                name=area.name,
                boundary=area.polygon(),
                finding_type_keys=TYPES,
                reviewer_user_ids=[self.users["reviewer"].id],
                road_category=area.road_category,
                survey_start=date.today() - timedelta(days=21),
                survey_end=date.today() + timedelta(days=30),
                partner_reference=f"DEMO-{number}",
            ),
        )
        self.db.commit()
        admin_ctx = self.ctx("admin", project.id)
        for key in ("manager", "collector", "viewer"):
            for role in PEOPLE[key][2]:
                projects.add_project_member(self.db, admin_ctx, self.users[key].id, role)
        self.db.commit()
        return project.id

    def upload_photos(self, number: int, project_id: uuid.UUID, area: Area) -> None:
        """5 photos by the field collector: 3 with GPS, 1 without (location picked later),
        and 1 without GPS that is blurry or dark (left without a location, flagged)."""
        rng = random.Random(number * 100)
        ctx = self.ctx("collector", project_id)
        plan = [
            ("normal", True),
            ("normal", True),
            ("normal", True),
            ("normal", False),
            ("blurry" if number % 2 else "dark", False),
        ]
        picked = None
        for index, (kind, has_gps) in enumerate(plan, start=1):
            gps = area.point(rng) if has_gps else None
            data = road_photo(number * 10 + index, gps=gps, kind=kind)
            outcome = images.upload_image(
                self.db,
                ctx,
                upload=io.BytesIO(data),
                filename=f"demo-street-{number}-{index}.jpg",
                device_location=None,
            )
            if index == 4:
                picked = outcome.image
        if picked is not None:  # the collector picks where photo 4 was taken
            lat, lon = area.point(rng)
            images.set_location(self.db, ctx, picked, LatLon(latitude=lat, longitude=lon))
            self.db.commit()

    def analyse(self, project_id: uuid.UUID) -> None:
        outcome = analysis.start_analysis(self.db, self.ctx("manager", project_id), image_ids=None)
        # Run the jobs here instead of through the queue (same code as the worker).
        session_factory = get_session_factory()

        def run_now(job_id: uuid.UUID) -> None:
            with session_factory() as worker_db:
                analysis.run_job(worker_db, job_id)

        analysis.queue_jobs(self.db, outcome.jobs, run_now)
        self.db.expire_all()

    def review(
        self, project_id: uuid.UUID, decisions: list[tuple[str, dict[str, Any]]]
    ) -> list[Finding]:
        """Apply decisions to the AI suggestions in order; the rest stay unreviewed."""
        ctx = self.ctx("reviewer", project_id)
        todo = list(
            self.db.scalars(
                select(Finding)
                .where(Finding.project_id == project_id, Finding.origin == "ai")
                .order_by(Finding.created_at, Finding.detection_index)
            )
        )
        done = []
        for finding, (action, fields) in zip(todo, decisions, strict=False):
            body = {"action": action, "version": finding.version, **fields}
            if action == "verify" and "type_key" not in fields:
                body["type_key"] = finding.predicted_type_key
            done.append(findings.review(self.db, ctx, finding.id, ReviewRequest(**body)))
        return done


def _ask_password() -> str:
    from_env = os.environ.get("DEMO_PASSWORD")
    if from_env:
        return from_env
    first = getpass.getpass("Password for ALL demo users: ")
    second = getpass.getpass("Repeat the password: ")
    if first != second:
        raise CommandError("The two passwords do not match.")
    return first


def build(db: Session, password: str) -> None:
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise CommandError(
            f"Password must be {PASSWORD_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} characters."
        )
    if db.scalar(select(Organization.id).where(Organization.name == ORG_NAME)) is not None:
        raise CommandError(
            f"The '{ORG_NAME}' demo organization already exists; nothing was changed."
        )
    demo = Demo(db, password)
    print("Creating demo data (all clearly labelled DEMO):")
    demo.create_people()

    project_ids = []
    for number, area in enumerate(PROJECTS, start=1):
        project_id = demo.create_project(number, area)
        demo.upload_photos(number, project_id, area)
        demo.analyse(project_id)
        project_ids.append(project_id)
        demo.say(f"project '{area.name}': 5 photos uploaded and analysed")

    # Project 1: a full review, priority settings v2, inspections and reports.
    p1 = project_ids[0]
    reviewed = demo.review(
        p1,
        [
            ("verify", {"severity_key": "high", "notes": "Deep pothole in the right lane (demo)."}),
            ("verify", {"severity_key": "medium", "type_key": "surface_cracking"}),
            ("verify", {"severity_key": "low"}),
            ("reject", {"reason": "Shadow from a tree, not damage (demo)."}),
            ("needs_field_check", {"reason": "Photo too far away to judge (demo)."}),
        ],
    )
    if reviewed and reviewed[0].location_quality != "missing":
        first = reviewed[0]
        moved = LatLon(latitude=PROJECTS[0].south + 0.004, longitude=PROJECTS[0].west + 0.005)
        findings.review(
            db,
            demo.ctx("reviewer", p1),
            first.id,
            ReviewRequest(
                action="edit",
                version=first.version,
                corrected_location=moved,
                reason="Pin moved to the exact spot (demo).",
            ),
        )
    manual = findings.create_manual(
        db,
        demo.ctx("collector", p1),
        ManualFindingCreate(
            type_key="sidewalk_observation",
            notes="Raised sidewalk slab near the bus stop, trip hazard (demo).",
            location=LatLon(latitude=PROJECTS[0].south + 0.006, longitude=PROJECTS[0].west + 0.004),
        ),
    )
    findings.review(
        db,
        demo.ctx("reviewer", p1),
        manual.id,
        ReviewRequest(
            action="verify",
            version=manual.version,
            type_key="sidewalk_observation",
            severity_key="medium",
        ),
    )
    counts = {
        status: sum(1 for f in reviewed if f.review_status == status)
        for status in ("verified", "rejected", "needs_field_check")
    }
    demo.say(
        f"project 1: {counts['verified']} AI suggestions verified, {counts['rejected']} rejected, "
        f"{counts['needs_field_check']} needs field check, 1 sidewalk observation verified"
    )

    priority.save_config(
        db,
        demo.ctx("manager", p1),
        PriorityConfigIn(
            weights={"severity": 0.6, "road_category": 0.25, "facility_proximity": 0.15},
            severity_points={"low": 30, "medium": 65, "high": 100},
            road_category_points={"arterial": 100, "collector": 70, "local": 40, "other": 20},
            facility_types=["school", "hospital"],
            facility_radius_m=250,
            is_placeholder=True,
        ),
    )
    verified = list(
        db.scalars(
            select(Finding).where(Finding.project_id == p1, Finding.review_status == "verified")
        )
    )
    project_1 = demo.ctx("manager", p1).project
    _, scores = priority.scores_for(db, project_1, verified)
    ranked = sorted(verified, key=lambda f: -scores[f.id][0])
    demo.say("project 1: priority settings version 2 saved, scores calculated")

    manager = demo.ctx("manager", p1)
    collector_id = demo.users["collector"].id
    soon = date.today() + timedelta(days=7)
    if len(ranked) >= 1:
        inspections.plan(
            db, manager, ranked[0], InspectionPlan(owner_user_id=collector_id, planned_date=soon)
        )
    if len(ranked) >= 2:
        done = inspections.plan(
            db,
            manager,
            ranked[1],
            InspectionPlan(owner_user_id=collector_id, planned_date=date.today()),
        )
        collector = demo.ctx("collector", p1)
        inspections.record(
            db,
            collector,
            ranked[1],
            done.id,
            InspectionUpdate(status="inspected", outcome_note="Crack confirmed on site (demo)."),
        )
        inspections.add_evidence(db, collector, done.id, io.BytesIO(evidence_photo(7)))
        inspections.record(
            db,
            collector,
            ranked[1],
            done.id,
            InspectionUpdate(status="resolved", outcome_note="Sealed the crack (demo)."),
        )
    if len(ranked) >= 3:
        old = inspections.plan(
            db,
            manager,
            ranked[2],
            InspectionPlan(owner_user_id=collector_id, planned_date=date.today()),
        )
        inspections.record(
            db,
            manager,
            ranked[2],
            old.id,
            InspectionUpdate(status="resolved", outcome_note="Patched (demo)."),
        )
        inspections.reopen(
            db,
            manager,
            ranked[2],
            old.id,
            InspectionReopen(
                reason="Patch failed after rain (demo).",
                owner_user_id=collector_id,
                planned_date=soon,
            ),
        )
    demo.say("project 1: inspections planned, resolved with a photo, and reopened")

    session_factory = get_session_factory()

    def build_now(report_id: uuid.UUID) -> None:
        with session_factory() as worker_db:
            reports.build(worker_db, report_id)

    made = {}
    for fmt, unreviewed in (("csv", False), ("geojson", False), ("pdf", True)):
        made[fmt] = reports.request_report(
            db,
            manager,
            ReportRequest(format=fmt, filters=ReportFilters(), include_unreviewed=unreviewed),
            build_now,
        )
    db.expire_all()
    reports.share(db, manager, made["csv"], True)
    demo.say("project 1: CSV, GeoJSON and PDF reports (the CSV is shared with viewers)")

    # Project 2: a little review, so it differs from project 1.
    second = demo.review(
        project_ids[1],
        [("verify", {"severity_key": "medium"}), ("reject", {"reason": "Not damage (demo)."})],
    )
    demo.say(f"project 2: {len(second)} reviewed, the rest waiting for review")
    demo.say("project 3: everything waiting for review (shows the review queue)")

    print(
        "\nDone. Sign in at http://localhost:5173 with any of these (password: the one you typed):"
    )
    for key, (name, org_role, project_roles) in PEOPLE.items():
        roles = ", ".join(project_roles) or org_role
        print(f"  {key + '@' + EMAIL_DOMAIN:<28} {name:<24} {roles}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.demo_data", description=__doc__.split("\n")[0]
    )
    parser.parse_args(argv)
    try:
        password = _ask_password()
        with get_session_factory()() as db:
            build(db, password)
    except CommandError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
