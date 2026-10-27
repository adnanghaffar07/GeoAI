"""The Overview dashboard: numbers and chart data across the projects a person can see.

Every number follows the same permission rules as the rest of the app, project by project:
- photos and analysis: managers and reviewers see all; field collectors their own uploads;
  viewers none;
- unreviewed AI suggestions and field checks: only roles allowed to see candidates;
- verified findings: everyone on the project; rejected: only roles allowed to see them;
- inspection priority and inspections: managers, reviewers and viewers; collectors only the
  inspections assigned to them.
Totals are "as of now"; the date range only shapes the activity chart.
"""

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Date, and_, cast, exists, false, func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import OrgContext, ProjectContext, load_project_context
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.permissions import Perm
from app.models import AnalysisJob, Finding, FindingType, Image, Inspection
from app.models.priority import ACTIVE_INSPECTION_STATES
from app.schemas.dashboard import (
    ActivityDay,
    Dashboard,
    DashboardAccess,
    DashboardScope,
    DashboardTotals,
    LabelItem,
    MapPoint,
    ProjectRow,
    TopPriority,
)
from app.services import findings as findings_service
from app.services import priority as priority_service
from app.services import projects as projects_service

WAITING = ("ai_generated", "awaiting_review")
MAP_LIMIT = 2000
MAX_DAYS = 366


@dataclass
class _Access:
    """Which projects allow which kind of number for this person."""

    photos_all: list[uuid.UUID] = field(default_factory=list)
    photos_own: list[uuid.UUID] = field(default_factory=list)
    candidates: list[uuid.UUID] = field(default_factory=list)
    verified: list[uuid.UUID] = field(default_factory=list)
    rejected: list[uuid.UUID] = field(default_factory=list)
    priority: list[uuid.UUID] = field(default_factory=list)
    own_inspections: list[uuid.UUID] = field(default_factory=list)


def _access(contexts: list[ProjectContext]) -> _Access:
    access = _Access()
    for ctx in contexts:
        pid = ctx.project.id
        if ctx.has(Perm.IMAGE_STATUS_VIEW):
            if ctx.is_unconditional(Perm.IMAGE_STATUS_VIEW):
                access.photos_all.append(pid)
            else:
                access.photos_own.append(pid)
        if ctx.has(Perm.FINDING_VIEW_CANDIDATES):
            access.candidates.append(pid)
        if ctx.has(Perm.FINDING_VIEW_VERIFIED):
            access.verified.append(pid)
        if ctx.has(Perm.FINDING_VIEW_REJECTED):
            access.rejected.append(pid)
        if ctx.has(Perm.PRIORITY_VIEW):
            access.priority.append(pid)
        elif ctx.has(Perm.INSPECTION_RECORD):
            access.own_inspections.append(pid)
    return access


def _in(column: Any, ids: list[uuid.UUID]) -> Any:
    return column.in_(ids) if ids else false()


def _date_range(
    db: Session, days: int | None, photo_filter: Any, project_ids: list[uuid.UUID]
) -> tuple[date, date]:
    today = datetime.now().date()
    if days:
        return today - timedelta(days=days - 1), today
    first = db.scalar(select(func.min(Image.created_at)).where(photo_filter))
    first_finding = db.scalar(
        select(func.min(Finding.created_at)).where(_in(Finding.project_id, project_ids))
    )
    candidates = [d.date() for d in (first, first_finding) if d is not None]
    start = min(candidates) if candidates else today - timedelta(days=29)
    return max(start, today - timedelta(days=MAX_DAYS - 1)), today


def build(
    db: Session, org_ctx: OrgContext, *, project_id: uuid.UUID | None, days: int | None
) -> Dashboard:
    visible = projects_service.visible_projects(db, org_ctx.user, org_ctx, include_archived=False)
    if project_id is not None:
        visible = [(p, roles) for p, roles in visible if p.id == project_id]
        if not visible:
            raise NotFoundError("Project not found.")
    contexts = [load_project_context(db, org_ctx.user, project.id) for project, _ in visible]
    names = {ctx.project.id: ctx.project.name for ctx in contexts}
    a = _access(contexts)
    user_id = org_ctx.user.id
    project_ids = [ctx.project.id for ctx in contexts]

    # ---------------------------------------------------------------- photos
    photo_filter = and_(
        Image.status == "stored",
        or_(
            _in(Image.project_id, a.photos_all),
            and_(_in(Image.project_id, a.photos_own), Image.uploaded_by == user_id),
        ),
    )
    photos_by_project = dict(
        db.execute(
            select(Image.project_id, func.count()).where(photo_filter).group_by(Image.project_id)
        ).all()
    )
    analysed = db.scalar(
        select(func.count())
        .select_from(Image)
        .join(AnalysisJob, AnalysisJob.image_id == Image.id)
        .where(
            photo_filter,
            AnalysisJob.status == "completed",
            AnalysisJob.model_version == get_settings().analysis_model_version,
        )
    )
    missing = db.scalar(
        select(func.count()).select_from(Image).where(photo_filter, Image.location_source == "none")
    )
    # Not yet sent to the current AI model, per project (the "Check new photos" to-do).
    waiting_for_ai = dict(
        db.execute(
            select(Image.project_id, func.count())
            .where(
                photo_filter,
                ~exists().where(
                    AnalysisJob.image_id == Image.id,
                    AnalysisJob.model_version == get_settings().analysis_model_version,
                ),
            )
            .group_by(Image.project_id)
        ).all()
    )

    # ---------------------------------------------------------------- findings
    status_rows = db.execute(
        select(Finding.project_id, Finding.review_status, func.count())
        .where(_in(Finding.project_id, project_ids))
        .group_by(Finding.project_id, Finding.review_status)
    ).all()
    per_project: dict[uuid.UUID, Counter[str]] = defaultdict(Counter)
    review: Counter[str] = Counter()
    for pid, status, count in status_rows:
        if status in WAITING and pid in a.candidates:
            key = "waiting"
        elif status == "needs_field_check" and pid in a.candidates:
            key = "needs_field_check"
        elif status == "verified" and pid in a.verified:
            key = "verified"
        elif status == "rejected" and pid in a.rejected:
            key = "rejected"
        else:
            continue
        per_project[pid][key] += int(count)
        review[key] += int(count)

    verified_filter = and_(_in(Finding.project_id, a.verified), Finding.review_status == "verified")
    by_type = {
        key or "unknown": int(n)
        for key, n in db.execute(
            select(Finding.type_key, func.count()).where(verified_filter).group_by(Finding.type_key)
        ).all()
    }
    by_severity = {
        key or "not_set": int(n)
        for key, n in db.execute(
            select(Finding.severity_key, func.count())
            .where(verified_filter)
            .group_by(Finding.severity_key)
        ).all()
    }
    unconfirmed = db.scalar(
        select(func.count())
        .select_from(Finding)
        .where(verified_filter, Finding.location_quality != "reviewer_confirmed")
    )

    # ---------------------------------------------------------------- inspections
    inspection_status: dict[str, int] = {}
    prio_verified = and_(_in(Finding.project_id, a.priority), Finding.review_status == "verified")
    if a.priority:
        inspection_status = {
            status: int(n)
            for status, n in db.execute(
                select(Finding.inspection_status, func.count())
                .where(prio_verified)
                .group_by(Finding.inspection_status)
            ).all()
        }
    inspection_scope = or_(
        _in(Finding.project_id, a.priority),
        and_(_in(Finding.project_id, a.own_inspections), Inspection.owner_user_id == user_id),
    )
    inspection_rows = db.execute(
        select(Finding.project_id, Inspection.status, func.count())
        .join(Finding, Finding.id == Inspection.finding_id)
        .where(inspection_scope)
        .group_by(Finding.project_id, Inspection.status)
    ).all()
    open_by_project: Counter[uuid.UUID] = Counter()
    resolved_total = 0
    own_status: Counter[str] = Counter()
    for pid, status, n in inspection_rows:
        if status in ACTIVE_INSPECTION_STATES:
            open_by_project[pid] += int(n)
        if status == "resolved":
            resolved_total += int(n)
        if pid in a.own_inspections and status != "reopened":
            own_status[status] += int(n)
    if not a.priority and own_status:
        inspection_status = dict(own_status)

    # ---------------------------------------------------------------- activity
    start, end = _date_range(db, days, photo_filter, project_ids)
    since = datetime.combine(start, time.min)
    photo_days = dict(
        db.execute(
            select(cast(Image.created_at, Date), func.count())
            .where(photo_filter, Image.created_at >= since)
            .group_by(cast(Image.created_at, Date))
        ).all()
    )
    suggestion_days = dict(
        db.execute(
            select(cast(Finding.created_at, Date), func.count())
            .where(_in(Finding.project_id, a.candidates), Finding.created_at >= since)
            .group_by(cast(Finding.created_at, Date))
        ).all()
    )
    verified_days = dict(
        db.execute(
            select(cast(Finding.reviewed_at, Date), func.count())
            .where(verified_filter, Finding.reviewed_at >= since)
            .group_by(cast(Finding.reviewed_at, Date))
        ).all()
    )
    activity = []
    day = start
    while day <= end:
        activity.append(
            ActivityDay(
                date=day,
                photos=int(photo_days.get(day, 0)),
                suggestions=int(suggestion_days.get(day, 0)),
                verified=int(verified_days.get(day, 0)),
            )
        )
        day += timedelta(days=1)

    # ---------------------------------------------------------------- top priority
    top: list[TopPriority] = []
    for ctx in contexts:
        if ctx.project.id not in a.priority:
            continue
        candidates = list(
            db.scalars(
                select(Finding).where(
                    Finding.project_id == ctx.project.id,
                    Finding.review_status == "verified",
                    Finding.inspection_status != "resolved",
                )
            )
        )
        if not candidates:
            continue
        _, scores = priority_service.scores_for(db, ctx.project, candidates, keep=False)
        for finding in candidates:
            score, breakdown = scores[finding.id]
            top.append(
                TopPriority(
                    finding_id=finding.id,
                    project_id=ctx.project.id,
                    project_name=ctx.project.name,
                    type_key=finding.type_key,
                    severity_key=finding.severity_key,
                    score=score,
                    weight_covered=breakdown.weight_covered,
                    inspection_status=finding.inspection_status,
                )
            )
    top.sort(key=lambda item: -item.score)

    # ---------------------------------------------------------------- map
    location = func.coalesce(Finding.corrected_location, Finding.original_location)
    located = verified_filter & location.is_not(None)
    map_total = db.scalar(select(func.count()).select_from(Finding).where(located)) or 0
    map_points = [
        MapPoint(
            finding_id=fid,
            project_id=pid,
            latitude=lat,
            longitude=lon,
            type_key=type_key,
            severity_key=severity_key,
        )
        for fid, pid, lat, lon, type_key, severity_key in db.execute(
            select(
                Finding.id,
                Finding.project_id,
                func.ST_Y(location),
                func.ST_X(location),
                Finding.type_key,
                Finding.severity_key,
            )
            .where(located)
            .order_by(Finding.reviewed_at.desc().nulls_last(), Finding.id)
            .limit(MAP_LIMIT)
        ).all()
    ]

    # ---------------------------------------------------------------- labels
    types = db.execute(
        select(FindingType.key, FindingType.label).where(
            FindingType.organization_id == org_ctx.organization.id
        )
    ).all()
    rubric = findings_service.current_rubric(db, org_ctx.organization.id)

    totals = DashboardTotals(
        photos=sum(int(n) for n in photos_by_project.values()),
        photos_analysed=int(analysed or 0),
        photos_waiting_for_ai=sum(int(n) for n in waiting_for_ai.values()),
        photos_missing_location=int(missing or 0),
        waiting_review=review["waiting"],
        needs_field_check=review["needs_field_check"],
        verified=review["verified"],
        rejected=review["rejected"],
        verified_location_unconfirmed=int(unconfirmed or 0),
        inspections_open=sum(open_by_project.values()),
        inspections_resolved=resolved_total,
    )
    roles = {project.id: roles for project, roles in visible}
    return Dashboard(
        scope=DashboardScope(project_id=project_id, days=days, date_from=start, date_to=end),
        access=DashboardAccess(
            photos=bool(a.photos_all or a.photos_own),
            photos_own_only=bool(a.photos_own and not a.photos_all),
            candidates=bool(a.candidates),
            verified=bool(a.verified),
            rejected=bool(a.rejected),
            priority=bool(a.priority),
            own_inspections=bool(a.own_inspections),
        ),
        totals=totals,
        review_status=dict(review),
        verified_by_type=by_type,
        verified_by_severity=by_severity,
        inspection_status=inspection_status,
        activity=activity,
        top_priority=top[:5],
        map_points=map_points,
        map_truncated=map_total > len(map_points),
        projects=[
            ProjectRow(
                id=pid,
                name=names[pid],
                my_roles=roles.get(pid, []),
                photos=int(photos_by_project.get(pid, 0)),
                photos_waiting_for_ai=int(waiting_for_ai.get(pid, 0)),
                waiting_review=per_project[pid]["waiting"],
                verified=per_project[pid]["verified"],
                rejected=per_project[pid]["rejected"],
                inspections_open=open_by_project[pid],
            )
            for pid in project_ids
        ],
        finding_types=[LabelItem(key=key, label=label) for key, label in types],
        severity_levels=[LabelItem(key=lvl["key"], label=lvl["label"]) for lvl in rubric.levels],
    )
