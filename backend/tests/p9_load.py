# ruff: noqa: E501, S608  (test-only SQL built from fixed table names in this file)
"""P9.5 speed test at the expected volume (p9-system-testing-plan.md, P9-D1 PLACEHOLDER volume).

Not part of the normal test run (the file name does not start with test_). Run it with
scripts\\p9-load-test.bat, which calls:  python -m pytest tests/p9_load.py -s

It fills the throwaway TEST database (never the app database) with one busy organization:
20 projects, about 10,000 photos, 5,000 findings, 1,000 planned inspections and a road-risk project
with about 6,000 road sections. A few real rows are made through the API (upload, AI check,
review, planning), then copied in SQL, so every copy follows the database rules. Then each main
screen's request is timed 5 times, reports are built, and backend/p9-load-report.md is written.
The test database is emptied afterwards, as after every test.

Targets: pages and lists 2 seconds; reports and downloads 1 minute.
"""

import statistics
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import queue
from tests.analysis_fixtures import Setup
from tests.factories import create_project
from tests.test_road_risk import seed

PAGE_TARGET, REPORT_TARGET, REPEATS = 2.0, 60.0, 5
REPORT = Path(__file__).resolve().parents[1] / "p9-load-report.md"


def _columns(db: Session, table: str) -> list[str]:
    return list(
        db.scalars(
            text(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' "
                "AND table_name = :t AND is_generated = 'NEVER' ORDER BY ordinal_position"
            ),
            {"t": table},
        )
    )


def _copy(
    db: Session,
    table: str,
    source: str,
    where: str,
    change: dict[str, str],
    params: dict[str, Any] | None = None,
) -> int:
    """INSERT copies of the rows of `table` (alias s) for every row of `source` (alias g)."""
    cols = _columns(db, table)
    picked = ", ".join(change.get(c, f"s.{c}") for c in cols)
    sql = f"INSERT INTO {table} ({', '.join(cols)}) SELECT {picked} FROM {table} s CROSS JOIN {source} WHERE {where}"
    count = db.execute(text(sql), params or {}).rowcount
    db.commit()
    return count


JITTER = "ST_Translate({col}, (random() - 0.5) * 0.01, (random() - 0.5) * 0.01)"
LAST_YEAR = "now() - random() * interval '365 days'"


def _fill(s: Setup, db: Session) -> dict[str, Any]:
    pid = s.project_id
    s.upload(s.admin, seed=1)
    s.upload(s.admin, seed=2, gps=False)
    s.start(s.admin)
    items = s.findings(s.reviewer).json()["items"]
    for finding, severity in zip(items[:2], ("high", "low"), strict=True):
        answer = s.reviewer.post(
            f"/api/v1/findings/{finding['id']}/review",
            json={
                "action": "verify",
                "version": finding["version"],
                "type_key": "pothole",
                "severity_key": severity,
            },
        )
        assert answer.status_code == 200, answer.text
    planned = s.admin.post(
        f"/api/v1/findings/{items[0]['id']}/inspections",
        json={"owner_user_id": str(s.ann.user.id), "planned_date": "2026-11-20"},
    )
    assert planned.status_code in (200, 201), planned.text

    p = {"p": pid}
    images = _copy(
        db,
        "images",
        "generate_series(1, 4999) g",
        "s.project_id = :p",
        {
            "id": "gen_random_uuid()",
            "sha256": "md5(random()::text) || md5(random()::text)",
            "original_location": JITTER.format(col="s.original_location"),
            "created_at": LAST_YEAR,
        },
        p,
    )
    findings = _copy(
        db,
        "findings",
        "generate_series(1, 1250) g",
        "s.project_id = :p",
        {
            "id": "gen_random_uuid()",
            "detection_index": "s.detection_index + g * 100",
            "original_location": JITTER.format(col="s.original_location"),
            "corrected_location": JITTER.format(col="s.corrected_location"),
            "created_at": LAST_YEAR,
        },
        p,
    )
    free = (
        "(SELECT f.id AS fid FROM findings f WHERE f.project_id = :p AND f.review_status = 'verified' "
        "AND NOT EXISTS (SELECT 1 FROM inspections i WHERE i.finding_id = f.id) LIMIT 999) g"
    )
    inspections = _copy(
        db,
        "inspections",
        free,
        "s.project_id = :p",
        {"id": "gen_random_uuid()", "finding_id": "g.fid"},
        p,
    )

    for n in range(19):
        create_project(s.admin, name=f"Load test project {n + 2}")

    data = seed(db, pid)
    sections = _copy(
        db,
        "forecast_sections",
        "generate_series(1, 2000) g",
        "s.area_key = 'chicago'",
        {
            "id": "gen_random_uuid()",
            "section_key": "s.section_key || '-' || g",
            "line": "ST_Translate(s.line, 0, g * 0.0000001)",
        },
    )
    pairs = "forecast_sections o, forecast_sections g"
    match = "o.id = s.section_id AND g.area_key = o.area_key AND g.section_key LIKE o.section_key || '-%'"
    levels = _copy(
        db, "risk_levels", pairs, match, {"id": "gen_random_uuid()", "section_id": "g.id"}
    )
    _copy(db, "risk_factor_values", pairs, match, {"id": "gen_random_uuid()", "section_id": "g.id"})
    db.execute(text("ANALYZE"))
    db.commit()

    count = lambda t: db.scalar(text(f"SELECT count(*) FROM {t}"))  # noqa: E731
    return {
        "section": str(data["sections"]["a"].id),
        "finding": items[0]["id"],
        "made": {
            "projects": count("projects"),
            "photos": count("images"),
            "findings": count("findings"),
            "verified findings": db.scalar(
                text("SELECT count(*) FROM findings WHERE review_status = 'verified'")
            ),
            "inspections": count("inspections"),
            "road sections": count("forecast_sections"),
            "road risk levels": count("risk_levels"),
        },
        "copied": {
            "images": images,
            "findings": findings,
            "inspections": inspections,
            "sections": sections,
            "levels": levels,
        },
    }


def _time(call: Callable[[], Any], repeats: int = REPEATS) -> tuple[float, float, int]:
    seconds, status = [], 0
    for _ in range(repeats):
        start = time.perf_counter()
        status = call().status_code
        seconds.append(time.perf_counter() - start)
    return statistics.median(seconds), max(seconds), status


def test_speed_at_expected_volume(
    s: Setup, db: Session, worker: list[str], use_detector: Any, monkeypatch: Any
) -> None:
    from app.workers.report_tasks import generate_report

    monkeypatch.setattr(queue, "send_report_job", lambda report_id: generate_report(str(report_id)))
    started = time.perf_counter()
    made = _fill(s, db)
    fill_minutes = (time.perf_counter() - started) / 60

    pid, c = s.project_id, s.admin
    org = c.get("/api/v1/auth/me").json()["memberships"][0]["organization_id"]
    pages = [
        ("Projects list", f"/api/v1/organizations/{org}/projects"),
        ("Home dashboard", f"/api/v1/organizations/{org}/dashboard"),
        ("Project page", f"/api/v1/projects/{pid}"),
        ("Photos list", f"/api/v1/projects/{pid}/images"),
        ("Findings list", f"/api/v1/projects/{pid}/findings"),
        ("Findings list, verified only", f"/api/v1/projects/{pid}/findings?review_status=verified"),
        ("Findings map", f"/api/v1/projects/{pid}/findings.geojson"),
        ("Review: one finding", f"/api/v1/findings/{made['finding']}"),
        ("Review: finding history", f"/api/v1/findings/{made['finding']}/history"),
        ("Priority list", f"/api/v1/projects/{pid}/priority-list"),
        ("Inspections", f"/api/v1/projects/{pid}/inspections"),
        ("Road risk list", f"/api/v1/projects/{pid}/risk"),
        ("Road risk map", f"/api/v1/projects/{pid}/risk/map"),
        ("Road risk: one road", f"/api/v1/projects/{pid}/road-sections/{made['section']}/risk"),
        ("Alerts", "/api/v1/notifications"),
    ]
    rows = []
    for name, url in pages:
        median, slowest, status = _time(lambda url=url: c.get(url))
        rows.append((name, median, slowest, PAGE_TARGET, status))

    def report(fmt: str) -> Callable[[], Any]:
        def build() -> Any:
            made_report = c.post(f"/api/v1/projects/{pid}/reports", json={"format": fmt}).json()
            return c.get(f"/api/v1/reports/{made_report['id']}/file")

        return build

    for name, call in [
        ("Report: CSV", report("csv")),
        ("Report: map file (GeoJSON)", report("geojson")),
        ("Report: PDF", report("pdf")),
        (
            "Road risk download (CSV)",
            lambda: c.get(f"/api/v1/projects/{pid}/risk/export?format=csv"),
        ),
    ]:
        median, slowest, status = _time(call, repeats=2)
        rows.append((name, median, slowest, REPORT_TARGET, status))

    ok = lambda r: r[4] == 200 and r[2] <= r[3]  # noqa: E731
    lines = [
        "# P9.5 Speed test results",
        "",
        f"Run {datetime.now():%Y-%m-%d %H:%M} on the laptop (Docker), test database. Filling took {fill_minutes:.1f} minutes.",
        "Volume (P9-D1, PLACEHOLDER until the partner confirms): "
        + ", ".join(f"{v:,} {k}" for k, v in made["made"].items())
        + ".",
        "Each page was asked 5 times (reports 2 times) by a signed-in manager; times are inside the app, without the internet.",
        "",
        "| Screen | Usual (median) | Slowest | Target | Result |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        result = "OK" if ok(r) else (f"FAILED (answer {r[4]})" if r[4] != 200 else "TOO SLOW")
        lines.append(f"| {r[0]} | {r[1]:.2f} s | {r[2]:.2f} s | {r[3]:.0f} s | {result} |")
    slow = [r[0] for r in rows if not ok(r)]
    lines += ["", "**All within target.**" if not slow else f"**Needs work:** {', '.join(slow)}."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines))
    assert not slow, f"Slower than target or failed: {slow}"
