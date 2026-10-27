"""Reports and exports (P7, FR-45 to FR-50).

Checks: counts match the filters, verified-only by default, unreviewed data labelled,
map exports flag unconfirmed locations and leave out findings without one, every export
states its date/filters/status/limitations, exports and downloads are logged, and sharing
with viewers.
"""

import csv
import json
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import queue
from app.services.reports import REASON_QUEUE_DOWN
from app.workers.report_tasks import generate_report
from tests.analysis_fixtures import Setup
from tests.factories import make_org, sign_in


@pytest.fixture
def report_worker(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Build reports straight away instead of sending them to the queue."""
    monkeypatch.setattr(queue, "send_report_job", lambda report_id: generate_report(str(report_id)))
    yield


@pytest.fixture
def data(s: Setup, worker: list[str], use_detector: Any, report_worker: None) -> dict[str, Any]:
    """Two photos (one without GPS) -> 4 suggestions; 2 verified (one without a location)."""
    s.upload(s.admin, seed=1)
    s.upload(s.admin, seed=2, gps=False)
    s.start(s.admin)
    items = s.findings(s.reviewer).json()["items"]
    located = next(i for i in items if i["location"])
    unlocated = next(i for i in items if not i["location"])
    verified = []
    for finding, severity in ((located, "high"), (unlocated, "low")):
        response = s.reviewer.post(
            f"/api/v1/findings/{finding['id']}/review",
            json={
                "action": "verify",
                "version": finding["version"],
                "type_key": "pothole",
                "severity_key": severity,
                "notes": '=HYPERLINK("http://x")',
            },
        )
        assert response.status_code == 200, response.text
        verified.append(response.json())
    return {"located": verified[0], "unlocated": verified[1]}


def _request(client: TestClient, s: Setup, fmt: str, **body: Any) -> Any:
    return client.post(f"/api/v1/projects/{s.project_id}/reports", json={"format": fmt, **body})


def _download(client: TestClient, report: dict[str, Any]) -> Any:
    return client.get(f"/api/v1/reports/{report['id']}/file")


def _csv(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    lines = content.decode("utf-8-sig").splitlines()
    notes = [line[2:] for line in lines if line.startswith("# ")]
    rows = list(csv.DictReader(line for line in lines if not line.startswith("# ")))
    return notes, rows


def test_csv_is_verified_only_by_default_and_describes_itself(
    s: Setup, data: dict[str, Any]
) -> None:
    """FR-46, FR-48."""
    response = _request(s.admin, s, "csv")

    assert response.status_code == 202, response.text
    report = s.admin.get(f"/api/v1/reports/{response.json()['id']}").json()
    assert report["status"] == "completed"
    assert report["record_count"] == 2
    assert report["settings_used"]["severity_scale"] == {"version": 1, "is_placeholder": True}
    assert report["settings_used"]["includes_test_detector"] is True
    file = _download(s.admin, report)
    assert file.status_code == 200
    assert file.headers["content-type"].startswith("text/csv")
    assert report["file_name"] in file.headers["content-disposition"]
    notes, rows = _csv(file.content)
    assert "Review status included: verified findings only" in notes
    assert "Records: 2 (1 without a location)" in notes
    assert "Filters: none (all findings)" in notes
    assert any(note.startswith("Generated: ") for note in notes)
    assert any("PLACEHOLDER" in note for note in notes)
    assert any("TEST DETECTOR" in note for note in notes)
    assert any("approximate camera positions" in note for note in notes)
    assert {row["review_label"] for row in rows} == {"Verified"}
    # Highest inspection priority first; the location note says it is not confirmed.
    assert rows[0]["severity"] == "High"
    assert rows[0]["location_note"] == "Approximate (not confirmed)"
    assert rows[1]["location_note"] == "No location"
    # Text that a spreadsheet would run as a formula is neutralised.
    assert rows[0]["notes"].startswith("'=")


def test_counts_match_the_filters(s: Setup, data: dict[str, Any]) -> None:
    """FR-47: the export and the findings list agree for the same filters."""
    for filters, expected in (
        ({"severity_key": ["high"]}, 1),
        ({"has_location": False}, 1),
        ({"type_key": ["surface_cracking"]}, 0),
        ({"created_from": "2000-01-01", "created_to": "2000-01-02"}, 0),
    ):
        report = _request(s.admin, s, "csv", filters=filters).json()
        listed = s.admin.get(
            f"/api/v1/projects/{s.project_id}/findings",
            params={"review_status": "verified", **filters},
        ).json()
        assert report["record_count"] == expected == listed["total"], filters
        _, rows = _csv(_download(s.admin, report).content)
        assert len(rows) == expected


def test_unreviewed_data_is_labelled_and_never_shared(s: Setup, data: dict[str, Any]) -> None:
    report = _request(s.admin, s, "csv", include_unreviewed=True).json()

    assert report["record_count"] == 4
    notes, rows = _csv(_download(s.admin, report).content)
    assert any("UNREVIEWED AI suggestions" in note for note in notes)
    assert sorted(row["review_label"] for row in rows) == [
        "UNREVIEWED - not confirmed",
        "UNREVIEWED - not confirmed",
        "Verified",
        "Verified",
    ]
    shared = s.admin.post(f"/api/v1/reports/{report['id']}/share", json={"shared": True})
    assert shared.status_code == 409


def test_geojson_leaves_out_and_flags_locations(s: Setup, data: dict[str, Any]) -> None:
    """FR-49."""
    report = _request(s.admin, s, "geojson").json()

    document = json.loads(_download(s.admin, report).content)

    assert report["record_count"] == 2
    assert len(document["features"]) == 1
    assert document["metadata"]["left_out_without_location"] == 1
    assert document["metadata"]["left_out_ids"] == [data["unlocated"]["id"]]
    feature = document["features"][0]
    assert feature["properties"]["location_confirmed"] is False
    assert feature["properties"]["review_label"] == "Verified"
    assert feature["geometry"]["coordinates"][0] == pytest.approx(-122.42, abs=1e-3)


def test_pdf_report(s: Setup, data: dict[str, Any]) -> None:
    report = _request(s.admin, s, "pdf", include_unreviewed=True).json()

    file = _download(s.admin, report)

    assert report["status"] == "completed", report
    assert file.headers["content-type"] == "application/pdf"
    assert file.content.startswith(b"%PDF-")


def test_exports_and_downloads_are_logged(db: Session, s: Setup, data: dict[str, Any]) -> None:
    """FR-48."""
    report = _request(s.admin, s, "csv").json()
    _download(s.admin, report)

    actions = db.scalars(
        text("SELECT action FROM audit_events WHERE action LIKE 'report.%' ORDER BY created_at")
    ).all()

    assert actions == ["report.generated", "report.downloaded"]


def test_sharing_with_viewers(s: Setup, data: dict[str, Any]) -> None:
    """FR-50: viewers see only shared reports; they cannot create them."""
    report = _request(s.admin, s, "csv").json()
    url = f"/api/v1/reports/{report['id']}"

    assert s.viewer.get(f"/api/v1/projects/{s.project_id}/reports").json()["total"] == 0
    assert s.viewer.get(url).status_code == 404
    assert s.reviewer.post(f"{url}/share", json={"shared": True}).status_code == 404

    assert s.admin.post(f"{url}/share", json={"shared": True}).json()["shared_with_viewers"] is True

    assert s.viewer.get(f"/api/v1/projects/{s.project_id}/reports").json()["total"] == 1
    assert _download(s.viewer, report).status_code == 200
    assert _request(s.viewer, s, "csv").status_code == 403
    assert _request(s.reviewer, s, "csv").status_code == 403  # Q8: reviewers view, not generate
    assert s.ann_client.get(f"/api/v1/projects/{s.project_id}/reports").status_code == 403


def test_other_organizations_get_not_found(
    db: Session, s: Setup, data: dict[str, Any], make_client: Callable[[], TestClient]
) -> None:
    report = _request(s.admin, s, "csv").json()
    make_org(db, name="City B", admin_email="admin@b.test")
    other = sign_in(make_client(), "admin@b.test")

    assert other.get(f"/api/v1/reports/{report['id']}").status_code == 404
    assert _download(other, report).status_code == 404
    assert other.get(f"/api/v1/reports/{uuid.uuid4()}").status_code == 404


def test_queue_down_marks_the_report_failed(s: Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(report_id: uuid.UUID) -> None:
        raise ConnectionError("queue is down")

    monkeypatch.setattr(queue, "send_report_job", refuse)

    report = _request(s.admin, s, "csv").json()

    assert report["status"] == "failed" and report["failure_reason"] == REASON_QUEUE_DOWN
    assert _download(s.admin, report).status_code == 409


def test_bad_requests(s: Setup) -> None:
    assert _request(s.admin, s, "xlsx").status_code == 422
    bad_dates = {"created_from": "2026-10-10", "created_to": "2026-10-01"}
    assert _request(s.admin, s, "csv", filters=bad_dates).status_code == 422


def test_filter_values_must_be_codes(s: Setup) -> None:
    """A filter value can never inject a new line (or a formula) into the export header."""
    bad = {"type_key": ['x\n=HYPERLINK("http://evil","c")']}
    assert _request(s.admin, s, "csv", filters=bad).status_code == 422
