"""Reports and exports: CSV, GeoJSON and PDF (FR-45 to FR-50).

Rules:
- Verified findings only by default. Unreviewed AI suggestions only when asked for, by
  people allowed to, and then every such record is labelled "UNREVIEWED". Rejected and
  merged findings are never exported.
- The number of records always matches the filters: the export uses the same query as the
  findings list (`findings.filtered_query`).
- Every export states its date, filters, review status, settings versions, and location
  limitations, and is logged (the `reports` row plus history events).
- Map exports (GeoJSON) contain only findings with a location; each says whether a reviewer
  confirmed it, and the ones left out are counted in the metadata (FR-49).
- Reports with unreviewed data are never shared with viewers.
- Files are built in the background and kept in private storage.
"""

import csv
import html
import io
import json
import logging
import re
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from string import Template
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.core.auth import ProjectContext
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.permissions import Perm
from app.models import Finding, FindingType, Project, Report, SeverityRubric, User
from app.models.base import utc_now
from app.schemas.findings import FindingFilters, FindingOut
from app.schemas.reports import ReportOut, ReportRequest
from app.services import findings as findings_service
from app.services import priority as priority_service
from app.services.audit import record_event

log = logging.getLogger(__name__)

VERIFIED = ["verified"]
UNREVIEWED = ["ai_generated", "awaiting_review", "needs_field_check"]
STUCK_AFTER = timedelta(minutes=10)  # a build this old was interrupted and may be redone
REASON_QUEUE_DOWN = "The report service could not be reached. Try again in a moment."
MEDIA_TYPES = {"csv": "text/csv", "geojson": "application/geo+json", "pdf": "application/pdf"}

LIMITATIONS = [
    "AI results are suggestions until a technical reviewer verifies them; "
    "unreviewed records are labelled UNREVIEWED.",
    "Locations are approximate camera positions (photo GPS or a point picked on the map) "
    "unless a reviewer confirmed them; they are not survey-grade positions.",
    "Inspection priority only ranks what to inspect first. "
    "It does not decide repairs, costs or compliance.",
    "Severity follows the organization's severity scale; the AI score is never used as severity.",
]
PDF_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "report_pdf.html"


# ----------------------------------------------------------------- requesting
def visible(ctx: ProjectContext, report: Report) -> bool:
    if ctx.has(Perm.REPORT_VIEW_ALL):
        return True
    return ctx.has(Perm.REPORT_VIEW_SHARED) and report.shared_with_viewers


def request_report(
    db: Session, ctx: ProjectContext, body: ReportRequest, send: Callable[[uuid.UUID], None]
) -> Report:
    if not ctx.has(Perm.REPORT_GENERATE):
        raise PermissionDeniedError()
    if body.include_unreviewed and not ctx.has(Perm.REPORT_INCLUDE_UNREVIEWED):
        raise PermissionDeniedError("You may not include unreviewed data in reports.")
    report = Report(
        project_id=ctx.project.id,
        requested_by=ctx.user.id,
        format=body.format,
        filters=body.filters.model_dump(mode="json"),
        include_unreviewed=body.include_unreviewed,
        status="queued",
    )
    db.add(report)
    db.flush()
    record_event(
        db,
        action="report.generated",
        organization_id=ctx.project.organization_id,
        project_id=ctx.project.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="report",
        target_id=report.id,
        details={
            "format": body.format,
            "filters": report.filters,
            "include_unreviewed": body.include_unreviewed,
        },
    )
    db.commit()
    try:
        send(report.id)
    except Exception:  # any queue problem means the same thing to the user
        log.warning("Could not queue report %s", report.id, exc_info=True)
        report.status = "failed"
        report.failure_reason = REASON_QUEUE_DOWN
        report.completed_at = utc_now()
        db.commit()
    db.refresh(report)
    return report


def share(db: Session, ctx: ProjectContext, report: Report, shared: bool) -> Report:
    """Approve and share a report with viewers (FR-50), or stop sharing it."""
    if not ctx.has(Perm.REPORT_SHARE):
        raise PermissionDeniedError()
    if report.status != "completed":
        raise ConflictError("Only a finished report can be shared.")
    if shared and report.include_unreviewed:
        raise ConflictError(
            "This report contains unreviewed AI suggestions, so it cannot be shared with viewers."
        )
    report.shared_with_viewers = shared
    record_event(
        db,
        action="report.shared" if shared else "report.unshared",
        organization_id=ctx.project.organization_id,
        project_id=ctx.project.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="report",
        target_id=report.id,
        details={"format": report.format},
    )
    db.commit()
    db.refresh(report)
    return report


def log_download(db: Session, ctx: ProjectContext, report: Report) -> None:
    record_event(
        db,
        action="report.downloaded",
        organization_id=ctx.project.organization_id,
        project_id=ctx.project.id,
        actor_user_id=ctx.user.id,
        actor_roles=ctx.actor_roles,
        target_type="report",
        target_id=report.id,
        details={"format": report.format, "record_count": report.record_count},
    )
    db.commit()


def file_name(project_name: str, report: Report) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", project_name.lower()).strip("-")[:40] or "project"
    return f"geoinfralens-{slug}-{report.created_at:%Y%m%d-%H%M}.{report.format}"


def to_out(db: Session, reports: list[Report], project_name: str) -> list[ReportOut]:
    ids = {r.requested_by for r in reports}
    names = (
        dict(db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all())
        if ids
        else {}
    )
    return [
        ReportOut(
            id=r.id,
            project_id=r.project_id,
            format=r.format,
            filters=r.filters,
            include_unreviewed=r.include_unreviewed,
            settings_used=r.settings_used,
            status=r.status,
            record_count=r.record_count,
            shared_with_viewers=r.shared_with_viewers,
            failure_reason=r.failure_reason,
            requested_by_name=names.get(r.requested_by),
            created_at=r.created_at,
            completed_at=r.completed_at,
            file_name=file_name(project_name, r) if r.status == "completed" else None,
        )
        for r in reports
    ]


# ----------------------------------------------------------------- building (worker)
def build(db: Session, report_id: uuid.UUID) -> None:
    """Build one report file. A finished report is skipped, so running twice is safe."""
    report = db.scalar(select(Report).where(Report.id == report_id).with_for_update())
    if report is None:
        log.warning("Report %s not found; nothing to do", report_id)
        return
    if report.status == "completed" or (
        report.status == "processing" and utc_now() - report.created_at < STUCK_AFTER
    ):
        db.rollback()  # done, or another worker is building it right now
        return
    report.status = "processing"
    db.commit()
    try:
        content, count, settings_used = _render(db, report)
        key = f"reports/project/{report.project_id}/{report.id}.{report.format}"
        storage.save_bytes(key, content)
    except Exception:  # a broken report fails on its own, never the worker
        log.exception("Report %s failed", report.id)
        db.rollback()
        report.status = "failed"
        report.failure_reason = "The report could not be created. Try again, or contact support."
        report.completed_at = utc_now()
        db.commit()
        return
    report.storage_key = key
    report.record_count = count
    report.settings_used = settings_used
    report.status = "completed"
    report.completed_at = utc_now()
    db.commit()
    log.info("Report built: report=%s format=%s records=%s", report.id, report.format, count)


def _render(db: Session, report: Report) -> tuple[bytes, int, dict[str, Any]]:
    project = db.get(Project, report.project_id)
    assert project is not None  # foreign key
    filters = FindingFilters(**report.filters)
    statuses = VERIFIED + (UNREVIEWED if report.include_unreviewed else [])
    findings = list(
        db.scalars(
            findings_service.filtered_query(project.id, statuses, filters).order_by(
                Finding.created_at, Finding.id
            )
        )
    )
    config, scores = priority_service.scores_for(db, project, findings, keep=False)
    rubric = findings_service.current_rubric(db, project.organization_id)
    outs = findings_service.to_out(db, findings)
    # Highest inspection priority first; unreviewed records (no score) after them.
    outs.sort(key=lambda out: -(scores[out.id][0] if out.id in scores else -1))
    settings_used = {
        "severity_scale": {"version": rubric.version, "is_placeholder": rubric.is_placeholder},
        "priority_settings": {"version": config.version, "is_placeholder": config.is_placeholder},
        "ai_model_versions": sorted({f.model_version for f in findings if f.model_version}),
        "includes_test_detector": any(out.is_test_detector for out in outs),
        "includes_trial_model": any(out.is_trial_model for out in outs),
    }
    context = _Context(
        db=db,
        report=report,
        project=project,
        findings=outs,
        scores={key: value[0] for key, value in scores.items()},
        rubric=rubric,
        settings_used=settings_used,
    )
    builder = {"csv": _csv, "geojson": _geojson, "pdf": _pdf}[report.format]
    return builder(context), len(outs), settings_used


class _Context:
    def __init__(
        self,
        *,
        db: Session,
        report: Report,
        project: Project,
        findings: list[FindingOut],
        scores: dict[uuid.UUID, float],
        rubric: SeverityRubric,
        settings_used: dict[str, Any],
    ) -> None:
        self.report = report
        self.project = project
        self.findings = findings
        self.scores = scores
        self.settings_used = settings_used
        self.type_labels = dict(
            db.execute(
                select(FindingType.key, FindingType.label).where(
                    FindingType.organization_id == project.organization_id
                )
            ).all()
        )
        self.severity_labels = {level["key"]: level["label"] for level in rubric.levels}
        self.requested_by = db.scalar(select(User.full_name).where(User.id == report.requested_by))

    def type_label(self, finding: FindingOut) -> str:
        key = finding.type_key or finding.predicted_type_key
        label = self.type_labels.get(key or "", key or "")
        return label if finding.type_key else f"{label} (AI suggestion)"

    def status_label(self, finding: FindingOut) -> str:
        return "Verified" if finding.review_status == "verified" else "UNREVIEWED - not confirmed"

    def location_note(self, finding: FindingOut) -> str:
        if finding.location is None:
            return "No location"
        if finding.location_quality == "reviewer_confirmed":
            return "Confirmed by reviewer"
        return "Approximate (not confirmed)"

    def header_lines(self) -> list[str]:
        """Date, filters, review status, settings and limitations (FR-48)."""
        report = self.report
        f = report.filters
        parts = []
        if f.get("type_key"):
            parts.append("types: " + ", ".join(self.type_labels.get(k, k) for k in f["type_key"]))
        if f.get("severity_key"):
            parts.append(
                "severity: " + ", ".join(self.severity_labels.get(k, k) for k in f["severity_key"])
            )
        if f.get("created_from"):
            parts.append(f"added from {f['created_from']}")
        if f.get("created_to"):
            parts.append(f"added until {f['created_to']}")
        if f.get("has_location") is True:
            parts.append("with a location only")
        elif f.get("has_location") is False:
            parts.append("without a location only")
        scale = self.settings_used["severity_scale"]
        prio = self.settings_used["priority_settings"]
        without_location = sum(1 for item in self.findings if item.location is None)
        lines = [
            f"GeoInfraLens AI report - project: {self.project.name}",
            f"Generated: {utc_now():%Y-%m-%d %H:%M} UTC by {self.requested_by or 'unknown'}",
            "Filters: " + ("; ".join(parts) if parts else "none (all findings)"),
            "Review status included: "
            + (
                "verified findings AND UNREVIEWED AI suggestions (not confirmed problems)"
                if report.include_unreviewed
                else "verified findings only"
            ),
            f"Records: {len(self.findings)} ({without_location} without a location)",
            f"Severity scale: version {scale['version']}"
            + (" (PLACEHOLDER until the customer confirms)" if scale["is_placeholder"] else ""),
            f"Inspection priority settings: version {prio['version']}"
            + (" (PLACEHOLDER weights)" if prio["is_placeholder"] else ""),
        ]
        if self.settings_used["includes_test_detector"]:
            lines.append("Includes results of the TEST DETECTOR: these are not real detections.")
        if self.settings_used.get("includes_trial_model"):
            lines.append(
                "Includes results of a TRIAL MODEL whose accuracy is not approved: "
                "it misses much of the damage."
            )
        return lines + [f"Note: {text}" for text in LIMITATIONS]

    def row(self, finding: FindingOut) -> dict[str, Any]:
        score = self.scores.get(finding.id)
        return {
            "finding_id": str(finding.id),
            "review_status": finding.review_status,
            "review_label": self.status_label(finding),
            "type": self.type_label(finding),
            "severity": self.severity_labels.get(
                finding.severity_key or "", finding.severity_key or ""
            ),
            "severity_scale_version": finding.severity_rubric_version or "",
            "inspection_priority": "" if score is None else score,
            "inspection_status": finding.inspection_status,
            "latitude": finding.location.latitude if finding.location else "",
            "longitude": finding.location.longitude if finding.location else "",
            "location_note": self.location_note(finding),
            "location_source": finding.location_source,
            "origin": "AI" if finding.origin == "ai" else "Added by a person",
            "ai_suggested_type": finding.predicted_type_key or "",
            "ai_score_not_severity": ""
            if finding.predicted_confidence is None
            else finding.predicted_confidence,
            "ai_model_version": finding.model_version or "",
            "test_detector": "yes" if finding.is_test_detector else "",
            "trial_model": "yes" if finding.is_trial_model else "",
            "notes": finding.notes or "",
            "reviewed_by": finding.reviewed_by_name or "",
            "reviewed_at": finding.reviewed_at.isoformat() if finding.reviewed_at else "",
            "added_at": finding.created_at.isoformat(),
        }


def _one_line(text: str) -> str:
    """No line breaks or control characters: a filter value can never start a new line."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", text)


def _safe_cell(value: Any) -> Any:
    """Spreadsheet programs run text starting with = + - @ (or tab/CR first) as formulas:
    such text gets a leading apostrophe so it is shown, not run."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{value}"
    return value


def _csv(ctx: _Context) -> bytes:
    """Lines starting with '#' describe the export; the table follows."""
    buffer = io.StringIO()
    for line in ctx.header_lines():
        buffer.write(f"# {_one_line(line)}\n")
    rows = [ctx.row(finding) for finding in ctx.findings]
    columns = list(ctx.row(ctx.findings[0]).keys()) if rows else list(_EMPTY_COLUMNS)
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _safe_cell(value) for key, value in row.items()})
    return buffer.getvalue().encode("utf-8-sig")  # BOM so Excel reads UTF-8 correctly


_EMPTY_COLUMNS = (
    "finding_id",
    "review_status",
    "review_label",
    "type",
    "severity",
    "inspection_priority",
    "latitude",
    "longitude",
    "location_note",
)


def _geojson(ctx: _Context) -> bytes:
    """Map export: only findings with a location, each flagged confirmed or approximate."""
    features = []
    left_out = []
    for finding in ctx.findings:
        if finding.location is None:
            left_out.append(str(finding.id))
            continue
        properties = ctx.row(finding)
        properties.pop("latitude")
        properties.pop("longitude")
        properties["location_confirmed"] = finding.location_quality == "reviewer_confirmed"
        features.append(
            {
                "type": "Feature",
                "id": str(finding.id),
                "geometry": {
                    "type": "Point",
                    "coordinates": [finding.location.longitude, finding.location.latitude],
                },
                "properties": properties,
            }
        )
    document = {
        "type": "FeatureCollection",
        "metadata": {
            "description": ctx.header_lines(),
            "filters": ctx.report.filters,
            "include_unreviewed": ctx.report.include_unreviewed,
            "settings_used": ctx.settings_used,
            "record_count": len(ctx.findings),
            "left_out_without_location": len(left_out),
            "left_out_ids": left_out,
            "coordinate_reference_system": "WGS 84 (EPSG:4326), longitude then latitude",
        },
        "features": features,
    }
    return json.dumps(document, ensure_ascii=False, indent=1, default=str).encode("utf-8")


def _pdf(ctx: _Context) -> bytes:
    from weasyprint import HTML  # heavy import: only when a PDF is made

    e = html.escape
    by_status = Counter(ctx.status_label(f) for f in ctx.findings)
    by_type = Counter(ctx.type_label(f) for f in ctx.findings)
    by_severity = Counter(
        ctx.severity_labels.get(f.severity_key or "", "Not set") for f in ctx.findings
    )

    def counts(title: str, counter: Counter[str]) -> str:
        rows = "".join(
            f"<tr><td>{e(k)}</td><td class=n>{v}</td></tr>" for k, v in counter.most_common()
        )
        rows = rows or "<tr><td>None</td></tr>"
        return f"<div class=box><h3>{e(title)}</h3><table>{rows}</table></div>"

    rows = []
    for rank, finding in enumerate(ctx.findings, start=1):
        row = ctx.row(finding)
        unreviewed = finding.review_status != "verified"
        location = (
            f"{finding.location.latitude:.5f}, {finding.location.longitude:.5f}"
            if finding.location
            else "-"
        )
        rows.append(
            f"<tr class='{'unrev' if unreviewed else ''}'><td class=n>{rank}</td>"
            f"<td>{e(row['type'])}</td><td>{e(row['review_label'])}</td>"
            f"<td>{e(str(row['severity']) or '-')}</td>"
            f"<td class=n>{e(str(row['inspection_priority']) or '-')}</td>"
            f"<td>{e(finding.inspection_status)}</td><td>{e(location)}</td>"
            f"<td>{e(row['location_note'])}</td></tr>"
        )
    warning = (
        "<p class=warn>This report includes UNREVIEWED AI suggestions. They are not confirmed "
        "problems and must not be used as verified results.</p>"
        if ctx.report.include_unreviewed
        else ""
    )
    empty = "<tr><td colspan=8>No findings match these filters.</td></tr>"
    document = Template(PDF_TEMPLATE.read_text(encoding="utf-8")).substitute(
        title=e(f"{ctx.project.name}: findings report"),
        warning=warning,
        header="".join(f"<li>{e(line)}</li>" for line in ctx.header_lines()),
        summary=counts("Review status", by_status)
        + counts("Type", by_type)
        + counts("Severity", by_severity),
        rows="".join(rows) or empty,
    )
    pdf: bytes = HTML(string=document).write_pdf()
    return pdf


def get_report(db: Session, ctx: ProjectContext, report_id: uuid.UUID) -> Report:
    report = db.scalar(
        select(Report).where(Report.id == report_id, Report.project_id == ctx.project.id)
    )
    if report is None or not visible(ctx, report):
        raise NotFoundError("Report not found.")
    return report
