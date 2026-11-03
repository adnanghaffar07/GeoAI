"""Road-risk forecasting in the app (F4b; documentation/04-design/forecasting-f4b-design.md).

Only the results the screens need live here. The heavy data (road map, weather history, map
layers, 311 history) stays in the separate `forecast` database, one schema per area.

- `forecast_settings`: forecasting on/off per project, its level (1 = risk factors, 2 = tested
  Chicago levels) and status.
- `forecast_sections`: the ~100 m road pieces of an area, copied once per area.
- `risk_runs`: every job run per project (weekly levels, daily factors, outlook), kept as history.
- `risk_levels`: Level 2 only: rank and level (high / medium / low) with reasons. Owner decision
  F4-D2 (2026-10-30): no percentage is shown; `monitor_value` keeps the raw model value only for
  the monthly check (`forecast_monitoring`).
- `risk_factor_values`: the risk factors and background facts per section (both levels).
- `weather_outlooks`: the NWS 7-day forecast at the project's centre.
- `alerts`, `alert_reads`: automatic alerts for project managers (F4e; roadmap section 7.5).
- `forecast_monitoring`: monthly comparison of raw model values with what happened.
"""

import uuid
from datetime import date, datetime
from typing import Any

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, sql_in_list, updated_at_column, uuid_pk

FORECAST_STATUSES: tuple[str, ...] = ("setting_up", "ready", "failed", "too_large", "off")
RUN_KINDS: tuple[str, ...] = ("setup", "weekly_levels", "daily_factors", "outlook", "monitor")
RUN_STATUSES: tuple[str, ...] = ("running", "completed", "failed")
RISK_LEVELS: tuple[str, ...] = ("high", "medium", "low")
FACTOR_LEVELS: tuple[str, ...] = ("high", "medium", "low", "missing")
FACTOR_KINDS: tuple[str, ...] = ("risk", "background")
# F4d: roles a project manager can let see road risk, and the default (the approved F4 plan).
VISIBILITY_ROLES: tuple[str, ...] = ("technical_reviewer", "viewer", "field_collector")
DEFAULT_VISIBLE_ROLES: tuple[str, ...] = ("technical_reviewer", "viewer")
ALERT_TYPES: tuple[str, ...] = (
    "turned_high",
    "freeze_thaw_coming",
    "heavy_rain_coming",
    "data_problem",
    "inspection_assigned",  # personal: someone was asked to inspect (2026-11-03)
)


class ForecastSettings(Base):
    __tablename__ = "forecast_settings"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_forecast_settings_project"),
        CheckConstraint("level IN (1, 2)", name="level_allowed"),
        CheckConstraint(f"status IN ({sql_in_list(FORECAST_STATUSES)})", name="status_allowed"),
        CheckConstraint("area_km2 IS NULL OR area_km2 >= 0", name="area_not_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    level: Mapped[int] = mapped_column(Integer)
    # The area in the forecast database: "chicago" for Chicago projects, else one area per project.
    area_key: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(
        String(20), default="setting_up", server_default="setting_up"
    )
    area_km2: Mapped[float | None] = mapped_column(Float)
    last_weekly_run: Mapped[date | None] = mapped_column(Date)
    last_daily_run: Mapped[date | None] = mapped_column(Date)
    message: Mapped[str | None] = mapped_column(Text)
    # F4d (owner request): who else, besides project managers, can see road risk.
    visible_to_roles: Mapped[list[str]] = mapped_column(
        JSONB,
        default=lambda: list(DEFAULT_VISIBLE_ROLES),
        server_default=text('\'["technical_reviewer", "viewer"]\'::jsonb'),
    )
    # CR-006: "Ask about road risk" switched on by the project manager (off by default).
    assistant_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    changed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class ForecastSection(Base):
    __tablename__ = "forecast_sections"
    __table_args__ = (
        UniqueConstraint("area_key", "section_key", name="uq_forecast_sections_area_section"),
        CheckConstraint("length_m > 0", name="length_positive"),
        Index("ix_forecast_sections_line", "line", postgresql_using="gist"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    area_key: Mapped[str] = mapped_column(String(60))
    section_key: Mapped[str] = mapped_column(String(80))  # the section id in the forecast database
    name: Mapped[str | None] = mapped_column(String(200))
    road_type: Mapped[str] = mapped_column(String(40))
    length_m: Mapped[float] = mapped_column(Float)
    line: Mapped[WKBElement] = mapped_column(Geometry("LINESTRING", srid=4326, spatial_index=False))
    created_at: Mapped[datetime] = created_at_column()


class RiskRun(Base):
    __tablename__ = "risk_runs"
    __table_args__ = (
        CheckConstraint(f"kind IN ({sql_in_list(RUN_KINDS)})", name="kind_allowed"),
        CheckConstraint(f"status IN ({sql_in_list(RUN_STATUSES)})", name="status_allowed"),
        Index("ix_risk_runs_project_kind_as_of", "project_id", "kind", "as_of"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(20))
    as_of: Mapped[date] = mapped_column(Date)  # inputs use only data from before this day
    model_version: Mapped[str] = mapped_column(String(60))  # "forecast-chicago-0.2" or "level1"
    data_dates: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="running", server_default="running")
    message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = created_at_column()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RiskLevel(Base):
    __tablename__ = "risk_levels"
    __table_args__ = (
        UniqueConstraint("run_id", "section_id", name="uq_risk_levels_run_section"),
        CheckConstraint(f"level IN ({sql_in_list(RISK_LEVELS)})", name="level_allowed"),
        CheckConstraint("rank >= 1", name="rank_positive"),
        Index("ix_risk_levels_run_rank", "run_id", "rank"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("risk_runs.id", ondelete="RESTRICT"))
    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("forecast_sections.id", ondelete="RESTRICT")
    )
    rank: Mapped[int] = mapped_column(Integer)  # 1 = riskiest in the whole area that Monday
    level: Mapped[str] = mapped_column(String(10))
    # [{"input": "reports_365d", "value": 4, "contribution": 0.8}, ...] largest first
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    missing_inputs: Mapped[list[str]] = mapped_column(JSONB, default=list)
    monitor_value: Mapped[float | None] = mapped_column(
        Float
    )  # raw model value; never shown (F4-D2)


class RiskFactorValue(Base):
    __tablename__ = "risk_factor_values"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "section_id", "factor", name="uq_risk_factor_values_run_section_factor"
        ),
        CheckConstraint(f"level IN ({sql_in_list(FACTOR_LEVELS)})", name="level_allowed"),
        CheckConstraint(f"kind IN ({sql_in_list(FACTOR_KINDS)})", name="kind_allowed"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("risk_runs.id", ondelete="RESTRICT"))
    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("forecast_sections.id", ondelete="RESTRICT")
    )
    factor: Mapped[str] = mapped_column(String(40))
    value: Mapped[float | None] = mapped_column(Float)  # None = missing, never guessed
    level: Mapped[str] = mapped_column(String(10))
    kind: Mapped[str] = mapped_column(String(12))


class WeatherOutlook(Base):
    __tablename__ = "weather_outlooks"
    __table_args__ = (
        CheckConstraint(
            "freeze_thaw_days >= 0 AND frost_days >= 0 AND heavy_rain_days >= 0",
            name="counts_not_negative",
        ),
        Index("ix_weather_outlooks_project_issued", "project_id", "issued_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # when NWS issued it
    source: Mapped[str] = mapped_column(String(120))  # e.g. "NWS LOT grid 74,71"
    # next 7 days: [{"date": "2026-11-02", "max_c": 3.1, "min_c": -2.4, "rain_mm": 0, "snow_mm": 5}]
    days: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    freeze_thaw_days: Mapped[int] = mapped_column(Integer)
    frost_days: Mapped[int] = mapped_column(Integer)
    heavy_rain_days: Mapped[int] = mapped_column(Integer)
    snow_mm: Mapped[float] = mapped_column(Float)
    fetched_at: Mapped[datetime] = created_at_column()


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(f"type IN ({sql_in_list(ALERT_TYPES)})", name="type_allowed"),
        # One open alert per event key and project (roadmap 7.5: no repeats while it is open).
        Index(
            "uq_alerts_one_open_per_event",
            "project_id",
            "event_key",
            unique=True,
            postgresql_where=text("closed_at IS NULL"),
        ),
        Index("ix_alerts_project_created", "project_id", "created_at"),
        Index("ix_alerts_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"))
    type: Mapped[str] = mapped_column(String(30))
    event_key: Mapped[str] = mapped_column(String(120))  # e.g. "freeze_thaw:2026-11-02"
    title: Mapped[str] = mapped_column(String(300))
    # sections, values, reasons, sources, data dates, model version, run id
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("risk_runs.id", ondelete="RESTRICT")
    )
    # Empty: a project alert for its managers. Set: a personal notification for this person only.
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = created_at_column()
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AlertRead(Base):
    __tablename__ = "alert_reads"
    __table_args__ = (UniqueConstraint("alert_id", "user_id", name="uq_alert_reads_alert_user"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alerts.id", ondelete="RESTRICT"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    read_at: Mapped[datetime] = created_at_column()


class ForecastMonitoring(Base):
    __tablename__ = "forecast_monitoring"
    __table_args__ = (
        UniqueConstraint(
            "area_key", "month", "model_version", name="uq_forecast_monitoring_area_month"
        ),
        CheckConstraint("sections >= 0", name="sections_not_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    area_key: Mapped[str] = mapped_column(String(60))
    month: Mapped[date] = mapped_column(Date)  # first day of the month checked
    model_version: Mapped[str] = mapped_column(String(60))
    sections: Mapped[int] = mapped_column(Integer)
    # ten groups low to high: [{"predicted": 0.012, "happened": 0.011, "rows": 7198}, ...]
    groups: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    largest_gap: Mapped[float | None] = mapped_column(Float)
    within_rule: Mapped[bool | None] = mapped_column(Boolean)  # largest gap <= 2 points (F4-D2)
    created_at: Mapped[datetime] = created_at_column()
