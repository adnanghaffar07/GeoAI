"""Road risk and alerts (F4c; api-spec.md section 3.10).

Levels only (owner decision F4-D2): high / medium / low with the main reasons, never a
percentage. Every risk response carries the TRIAL FORECAST label and the notice
"Risk estimate, not a confirmed defect."

Who may do what (permissions.py): `risk.view` project managers always; technical reviewers,
viewers and field collectors when the project's manager allows it (F4d; default reviewers and
viewers); `risk.configure` and `alert.view` project managers (org admins through the manager set).
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.core import queue
from app.core.auth import (
    CurrentUser,
    ProjectContext,
    get_current_user,
    load_project_context,
    require_project_permission,
)
from app.core.database import get_db
from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.permissions import Perm
from app.schemas.common import Page
from app.schemas.priority import InspectionOut, InspectionPlan
from app.schemas.road_risk import (
    AlertOut,
    AssistantAnswer,
    AssistantQuestion,
    ForecastSettingsIn,
    ForecastStatusOut,
    NotificationsOut,
    RiskListOut,
    SectionDetailOut,
    WeatherOut,
)
from app.services import inspections as inspections_service
from app.services import road_risk as service

project_router = APIRouter(prefix="/projects/{project_id}", tags=["road risk"])
notification_router = APIRouter(prefix="/notifications", tags=["road risk"])

LEVEL_FILTER = "^(high|medium|low)$"


def _send_setup(settings_id: uuid.UUID) -> None:
    queue.send_forecast_setup(settings_id)  # looked up at call time, so tests can replace it


def _send_tick() -> None:
    queue.send_forecast_tick()


def require_risk_view(
    project_id: uuid.UUID = Path(),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectContext:
    """`risk.view` plus the project's "who can see road risk" setting (F4d)."""
    ctx = load_project_context(db, current.user, project_id)
    if not service.can_view(db, ctx):
        raise PermissionDeniedError()
    return ctx


# ------------------------------------------------------------------ settings
@project_router.get("/forecast-settings", response_model=ForecastStatusOut)
def get_forecast_settings(
    ctx: ProjectContext = Depends(require_risk_view),
    db: Session = Depends(get_db),
) -> ForecastStatusOut:
    """Is forecasting on for this project, and how far has it got?"""
    return service.status_out(db, ctx)


@project_router.put("/forecast-settings", response_model=ForecastStatusOut)
def put_forecast_settings(
    body: ForecastSettingsIn,
    ctx: ProjectContext = Depends(require_project_permission(Perm.RISK_CONFIGURE)),
    db: Session = Depends(get_db),
) -> ForecastStatusOut:
    """Switch forecasting on (the area is set up in the background) or off (results are kept),
    and/or choose who else can see road risk (project managers always can)."""
    if body.visible_to_roles is not None:
        service.set_visibility(db, ctx, list(body.visible_to_roles))
    if body.assistant_enabled is not None:
        service.set_assistant(db, ctx, body.assistant_enabled)
    if body.enabled is not None:
        service.set_enabled(db, ctx, body.enabled, _send_setup)
    return service.status_out(db, ctx)


@project_router.post(
    "/risk-runs", response_model=ForecastStatusOut, status_code=status.HTTP_202_ACCEPTED
)
def request_risk_run(
    ctx: ProjectContext = Depends(require_project_permission(Perm.RISK_CONFIGURE)),
    db: Session = Depends(get_db),
) -> ForecastStatusOut:
    """Update now: new weather, risk factors and outlook (and Chicago levels) in the background."""
    service.request_update(db, ctx, _send_tick)
    return service.status_out(db, ctx)


# ------------------------------------------------------------------ risk
@project_router.get("/risk", response_model=RiskListOut)
def project_risk(
    ctx: ProjectContext = Depends(require_risk_view),
    db: Session = Depends(get_db),
    level: str | None = Query(default=None, pattern=LEVEL_FILTER),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> RiskListOut:
    """Road sections, inspect-first order, each with its level, main reasons and risk factors."""
    risk = service.project_risk(db, ctx)
    items = [i for i in risk.items if level is None or i.level == level]
    return RiskListOut(
        items=items[(page - 1) * page_size : page * page_size],
        page=page,
        page_size=page_size,
        total=len(items),
        status=service.status_out(db, ctx),
        levels_run=service.run_out(risk.levels_run),
        factors_run=service.run_out(risk.factors_run),
        counts=service.counts(risk.items),
    )


@project_router.get("/risk/map")
def project_risk_map(
    ctx: ProjectContext = Depends(require_risk_view),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Every section as GeoJSON with its level, for the map (word and icon on screen, never
    colour alone)."""
    return service.map_features(db, ctx)


@project_router.get("/road-sections/{section_id}/risk", response_model=SectionDetailOut)
def section_risk(
    section_id: uuid.UUID,
    ctx: ProjectContext = Depends(require_risk_view),
    db: Session = Depends(get_db),
) -> SectionDetailOut:
    """One section: level, reasons, factors, weekly history and inspections planned from it."""
    item, geometry, history, inspections, risk = service.section_detail(db, ctx, section_id)
    return SectionDetailOut(
        section=item,
        geometry=geometry,
        history=history,
        inspections=inspections,
        levels_run=service.run_out(risk.levels_run),
        factors_run=service.run_out(risk.factors_run),
    )


@project_router.get("/risk/export")
def export_risk(
    ctx: ProjectContext = Depends(require_risk_view),
    db: Session = Depends(get_db),
    file_format: str = Query(default="csv", alias="format", pattern="^(csv|geojson)$"),
) -> Response:
    """The road-risk list as a labelled CSV or GeoJSON file (recorded in the history)."""
    content, media, filename = service.export(db, ctx, file_format)
    return Response(
        content=content,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@project_router.post(
    "/road-sections/{section_id}/inspections",
    response_model=InspectionOut,
    status_code=status.HTTP_201_CREATED,
)
def plan_road_inspection(
    section_id: uuid.UUID,
    body: InspectionPlan,
    ctx: ProjectContext = Depends(require_project_permission(Perm.INSPECTION_PLAN)),
    db: Session = Depends(get_db),
) -> InspectionOut:
    """Plan an inspection of a road section, even with no photo finding there (F4d)."""
    if not service.section_in_project(db, ctx.project.id, section_id):
        raise NotFoundError("Road section not found in this project.")
    level_id = service.current_level_id(db, ctx.project.id, section_id)
    inspection = inspections_service.plan_road(db, ctx, section_id, level_id, body)
    return inspections_service.to_out(db, [inspection])[0]


@project_router.get("/road-sections/{section_id}/inspections", response_model=list[InspectionOut])
def road_inspections(
    section_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    project_id: uuid.UUID = Path(),
    db: Session = Depends(get_db),
) -> list[InspectionOut]:
    """All inspections of a road, oldest first. Managers and people who can see road risk see
    all; an inspection owner (e.g. a field collector) sees only the ones assigned to them."""
    ctx = load_project_context(db, current.user, project_id)
    items = inspections_service.road_history(db, ctx.project.id, section_id)
    if not (ctx.has(Perm.INSPECTION_PLAN) or service.can_view(db, ctx)):
        items = [item for item in items if inspections_service.can_record(ctx, item)]
        if not items:
            raise PermissionDeniedError()
    return inspections_service.to_out(db, items)


@project_router.post("/assistant", response_model=AssistantAnswer)
def ask_assistant(
    body: AssistantQuestion,
    ctx: ProjectContext = Depends(require_risk_view),
    db: Session = Depends(get_db),
) -> AssistantAnswer:
    """CR-006 "Ask about road risk": a short answer from the app's data, with links."""
    from app.services import assistant

    return assistant.ask(db, ctx, body.question)


@project_router.get("/weather", response_model=WeatherOut)
def project_weather(
    ctx: ProjectContext = Depends(require_risk_view),
    db: Session = Depends(get_db),
) -> WeatherOut:
    """The NWS 7-day outlook at the project's centre and the recent weather inputs."""
    return WeatherOut(
        outlook=service.outlook(db, ctx.project.id),
        recent=service.recent_weather(db, ctx.project.id),
    )


# ------------------------------------------------------------------ alerts
@project_router.get("/alerts", response_model=Page[AlertOut])
def project_alerts(
    ctx: ProjectContext = Depends(require_project_permission(Perm.ALERT_VIEW)),
    db: Session = Depends(get_db),
    include_closed: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[AlertOut]:
    items, total = service.project_alerts(db, ctx, include_closed, page, page_size)
    return Page(items=items, page=page, page_size=page_size, total=total)


@notification_router.get("", response_model=NotificationsOut)
def my_notifications(
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationsOut:
    """Alerts for the projects I manage (newest open ones first) and how many I have not read."""
    items, unread = service.notifications(db, current.user)
    managed = bool(service.managed_project_ids(db, current.user)) or service.has_personal(
        db, current.user
    )
    return NotificationsOut(items=items, unread_count=unread, manages_projects=managed)


@notification_router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Mark every alert of the projects I manage as read."""
    service.mark_all_read(db, current.user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@notification_router.get("/{alert_id}", response_model=AlertOut)
def get_notification(
    alert_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AlertOut:
    """One alert with its roads, reasons, dates and sources (F4e alert page)."""
    project_id = service.alert_project(db, alert_id)
    if project_id is None:
        raise NotFoundError("Alert not found.")
    ctx = load_project_context(db, current.user, project_id)
    alert = service.get_alert(db, alert_id)
    if not service.can_read_alert(ctx, alert):
        raise PermissionDeniedError()
    return service.alert_outs(db, current.user, [alert])[0]


@notification_router.post("/{alert_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_notification_read(
    alert_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    project_id = service.alert_project(db, alert_id)
    if project_id is None:
        raise NotFoundError("Alert not found.")
    ctx = load_project_context(db, current.user, project_id)  # 404 outside the person's projects
    alert = service.get_alert(db, alert_id)
    if not service.can_read_alert(ctx, alert):
        raise PermissionDeniedError()
    service.mark_read(db, current.user, alert)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
