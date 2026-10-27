"""AI analysis jobs and candidate findings (P5).

Covers AC-19 (analysis runs in the background with a visible status), AC-20 (a broken
result saves nothing), AC-21 (retrying never duplicates findings), AC-22 (AI output is
only a suggestion: `ai_generated`, confidence is not severity) and AC-23 (who may see it).

Shared setup (fake detector, inline worker, people and project) is in
`tests/analysis_fixtures.py`.
"""

import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.ai import stand_in
from app.models import AnalysisJob, Finding, FindingImage
from app.services.analysis import REASON_QUEUE_DOWN
from app.workers.analysis_tasks import run_analysis_job
from tests.analysis_fixtures import Detector, Setup, _note, two_candidates
from tests.factories import make_org, sign_in
from tests.photos import INSIDE


def _count(db: Session, model: type) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


# ------------------------------------------------------------------ running jobs
def test_analysis_creates_candidate_findings(
    db: Session, s: Setup, worker: list[str], use_detector: Any
) -> None:
    """AC-19 and AC-22."""
    image_id = s.upload(s.admin)

    response = s.start(s.admin)

    assert response.status_code == 202, response.text
    assert response.json()["created"] == 1 and response.json()["reused"] == 0
    job = s.admin.get(f"/api/v1/analysis-jobs/{worker[0]}").json()
    assert job["status"] == "completed"
    assert job["attempts"] == 1
    assert job["candidate_count"] == 2
    assert job["is_test_detector"] is True

    findings = s.findings(s.admin).json()
    assert findings["total"] == 2
    first = next(f for f in findings["items"] if f["predicted_type_key"] == "pothole")
    assert first["review_status"] == "ai_generated"  # a suggestion, never verified
    assert first["origin"] == "ai"
    assert first["predicted_confidence"] == pytest.approx(0.91)
    assert first["predicted_bbox"] == [10, 150, 110, 250]
    assert first["model_version"] == stand_in.MODEL_VERSION
    assert first["is_test_detector"] is True
    assert first["photo"]["id"] == image_id
    assert first["location_source"] == "photo_gps"
    assert first["location_quality"] == "approximate"
    assert first["location"]["latitude"] == pytest.approx(INSIDE[0], abs=1e-4)
    assert first["severity_key"] is None  # confidence is never turned into severity
    assert first["type_key"] is None  # the AI guess is not the reviewed type

    image = s.admin.get(f"/api/v1/images/{image_id}").json()
    assert image["analysis"]["status"] == "completed"
    assert image["analysis"]["candidate_count"] == 2
    counts = s.admin.get(f"/api/v1/projects/{s.project_id}").json()["counts"]
    assert counts["images_analysed"] == 1 and counts["findings_to_review"] == 2
    assert counts["images_waiting_for_ai"] == 0


def test_new_photos_are_counted_as_waiting_for_the_ai(
    s: Setup, worker: list[str], use_detector: Any
) -> None:
    s.upload(s.admin, seed=1)
    s.start(s.admin)
    s.upload(s.admin, seed=2)  # uploaded after the first check
    s.upload(s.admin, seed=3)

    counts = s.admin.get(f"/api/v1/projects/{s.project_id}").json()["counts"]
    assert counts["images"] == 3 and counts["images_waiting_for_ai"] == 2
    dashboard = s.admin.get(
        f"/api/v1/organizations/{s.admin.get('/api/v1/auth/me').json()['memberships'][0]['organization_id']}/dashboard",
        params={"project_id": s.project_id},
    ).json()
    assert dashboard["totals"]["photos_waiting_for_ai"] == 2
    assert dashboard["projects"][0]["photos_waiting_for_ai"] == 2

    s.start(s.admin)  # "Check new photos" sends exactly those two
    counts = s.admin.get(f"/api/v1/projects/{s.project_id}").json()["counts"]
    assert counts["images_waiting_for_ai"] == 0 and len(worker) == 3


def test_photo_without_location_gives_findings_marked_missing(
    s: Setup, worker: list[str], use_detector: Any
) -> None:
    """Locations are never invented."""
    s.upload(s.admin, gps=False)
    s.start(s.admin)

    item = s.findings(s.admin).json()["items"][0]

    assert item["location"] is None
    assert item["location_quality"] == "missing"
    assert item["location_source"] == "none"


def test_empty_result_means_no_candidates(
    s: Setup, worker: list[str], use_detector: Callable[[Detector], None]
) -> None:
    use_detector(lambda path, *, image_id: _note(image_id, []))
    s.upload(s.admin)

    s.start(s.admin)

    job = s.admin.get(f"/api/v1/analysis-jobs/{worker[0]}").json()
    assert job["status"] == "completed" and job["candidate_count"] == 0
    assert s.findings(s.admin).json()["total"] == 0


def test_starting_again_never_duplicates(
    db: Session, s: Setup, worker: list[str], use_detector: Any
) -> None:
    """AC-21: one job per photo and model version; findings are never created twice."""
    image_id = s.upload(s.admin)
    s.start(s.admin)

    again = s.start(s.admin, [image_id])
    everything = s.start(s.admin)
    run_analysis_job(worker[0])  # the queue delivering the same message twice

    assert again.json()["created"] == 0 and again.json()["reused"] == 1
    assert everything.json()["created"] == 0
    assert _count(db, AnalysisJob) == 1
    assert _count(db, Finding) == 2
    assert _count(db, FindingImage) == 2
    assert len(worker) == 1  # finished jobs are not sent again


def test_broken_result_fails_the_job_and_saves_nothing(
    db: Session, s: Setup, worker: list[str], use_detector: Callable[[Detector], None]
) -> None:
    """AC-20: one bad candidate rejects the whole result."""

    def half_broken(path: Path, *, image_id: str) -> dict[str, Any]:
        note = two_candidates(path, image_id=image_id)
        note["candidates"][1]["confidence"] = 7
        return note

    use_detector(half_broken)
    s.upload(s.admin)

    s.start(s.admin)

    job = s.admin.get(f"/api/v1/analysis-jobs/{worker[0]}").json()
    assert job["status"] == "failed"
    assert job["failure_reason"].startswith("Invalid model output")
    assert _count(db, Finding) == 0


def test_detector_crash_fails_only_that_job(
    db: Session, s: Setup, worker: list[str], use_detector: Callable[[Detector], None]
) -> None:
    def crash(path: Path, *, image_id: str) -> dict[str, Any]:
        raise RuntimeError("boom")

    use_detector(crash)
    s.upload(s.admin)

    s.start(s.admin)

    job = s.admin.get(f"/api/v1/analysis-jobs/{worker[0]}").json()
    assert job["status"] == "failed"
    assert job["failure_reason"] == "The analysis could not read this photo."


def test_failed_job_can_be_retried_without_duplicates(
    db: Session, s: Setup, worker: list[str], use_detector: Callable[[Detector], None]
) -> None:
    """AC-21."""
    use_detector(lambda path, *, image_id: {"broken": True})
    s.upload(s.admin)
    s.start(s.admin)
    job_id = worker[0]
    assert s.admin.get(f"/api/v1/analysis-jobs/{job_id}").json()["status"] == "failed"

    use_detector(two_candidates)
    retried = s.admin.post(f"/api/v1/analysis-jobs/{job_id}/retry")

    assert retried.status_code == 202
    job = s.admin.get(f"/api/v1/analysis-jobs/{job_id}").json()
    assert job["status"] == "completed" and job["attempts"] == 2
    assert _count(db, Finding) == 2
    assert s.admin.post(f"/api/v1/analysis-jobs/{job_id}/retry").status_code == 409
    assert _count(db, AnalysisJob) == 1


def test_queue_down_marks_the_job_failed_with_a_reason(
    db: Session, s: Setup, queue_down: None
) -> None:
    """Nothing is left stuck in "waiting" when the queue cannot be reached."""
    s.upload(s.admin)

    response = s.start(s.admin)

    assert response.status_code == 202
    job = response.json()["jobs"][0]
    assert job["status"] == "failed" and job["failure_reason"] == REASON_QUEUE_DOWN
    listed = s.admin.get(f"/api/v1/projects/{s.project_id}/analysis-jobs").json()
    assert listed["status_counts"] == {"failed": 1}


def test_job_list_and_status_filter(s: Setup, worker: list[str], use_detector: Any) -> None:
    s.upload(s.admin, seed=1)
    s.upload(s.admin, seed=2)
    s.start(s.admin)

    listed = s.admin.get(f"/api/v1/projects/{s.project_id}/analysis-jobs").json()
    failed = s.admin.get(f"/api/v1/projects/{s.project_id}/analysis-jobs?status=failed").json()

    assert listed["total"] == 2 and listed["status_counts"] == {"completed": 2}
    assert failed["total"] == 0
    bad = s.admin.get(f"/api/v1/projects/{s.project_id}/analysis-jobs?status=nonsense")
    assert bad.status_code == 422


def test_unknown_photo_ids_are_refused(s: Setup, worker: list[str]) -> None:
    response = s.start(s.admin, [str(uuid.uuid4())])

    assert response.status_code == 404
    assert worker == []


# ------------------------------------------------------------------ who may see what
def test_collectors_analyse_and_see_only_their_own_photos(
    db: Session, s: Setup, worker: list[str], use_detector: Any
) -> None:
    """AC-23: collectors see job status for their own uploads, never the AI suggestions."""
    ann_photo = s.upload(s.ann_client, seed=1)
    bob_photo = s.upload(s.bob_client, seed=2)

    assert s.start(s.ann_client, [bob_photo]).status_code == 404
    started = s.start(s.ann_client)  # "everything" means her own photos only

    assert started.status_code == 202
    assert started.json()["created"] == 1
    assert started.json()["jobs"][0]["image_id"] == ann_photo
    job_id = started.json()["jobs"][0]["id"]
    own = s.ann_client.get(f"/api/v1/analysis-jobs/{job_id}").json()
    assert own["status"] == "completed"
    assert own["candidate_count"] is None  # suggestions hidden from collectors
    assert s.bob_client.get(f"/api/v1/analysis-jobs/{job_id}").status_code == 403
    assert s.bob_client.post(f"/api/v1/analysis-jobs/{job_id}/retry").status_code == 403
    assert s.bob_client.get(f"/api/v1/projects/{s.project_id}/analysis-jobs").json()["total"] == 0

    image = s.ann_client.get(f"/api/v1/images/{ann_photo}").json()
    assert image["analysis"]["status"] == "completed"
    assert image["analysis"]["candidate_count"] is None

    assert s.findings(s.ann_client).json()["total"] == 0  # no unreviewed suggestions
    finding_id = str(db.scalar(select(Finding.id)))
    assert s.ann_client.get(f"/api/v1/findings/{finding_id}").status_code == 404


def test_reviewers_see_suggestions_but_viewers_do_not(
    db: Session, s: Setup, worker: list[str], use_detector: Any
) -> None:
    s.upload(s.admin)
    s.start(s.admin)
    finding_id = str(db.scalar(select(Finding.id)))

    assert s.findings(s.reviewer).json()["total"] == 2
    assert s.reviewer.get(f"/api/v1/findings/{finding_id}").status_code == 200
    assert (
        s.reviewer.post(f"/api/v1/projects/{s.project_id}/analysis-jobs", json={}).status_code
        == 403
    )

    assert s.findings(s.viewer).json()["total"] == 0
    assert s.viewer.get(f"/api/v1/findings/{finding_id}").status_code == 404
    assert s.viewer.get(f"/api/v1/projects/{s.project_id}/analysis-jobs").status_code == 403


def test_other_organizations_get_not_found(
    db: Session,
    s: Setup,
    make_client: Callable[[], TestClient],
    worker: list[str],
    use_detector: Any,
) -> None:
    s.upload(s.admin)
    s.start(s.admin)
    finding_id = str(db.scalar(select(Finding.id)))
    make_org(db, name="City B", admin_email="admin@b.test")
    other = sign_in(make_client(), "admin@b.test")

    assert other.get(f"/api/v1/analysis-jobs/{worker[0]}").status_code == 404
    assert other.post(f"/api/v1/analysis-jobs/{worker[0]}/retry").status_code == 404
    assert other.get(f"/api/v1/findings/{finding_id}").status_code == 404
    assert other.get(f"/api/v1/projects/{s.project_id}/findings").status_code == 404
    assert other.post(f"/api/v1/projects/{s.project_id}/analysis-jobs", json={}).status_code == 404
    assert s.admin.get(f"/api/v1/analysis-jobs/{uuid.uuid4()}").status_code == 404
    assert s.admin.get(f"/api/v1/findings/{uuid.uuid4()}").status_code == 404


def test_collectors_cannot_withdraw_after_analysis(
    s: Setup, worker: list[str], use_detector: Any
) -> None:
    """Decision Q6: withdraw is allowed only before analysis."""
    photo = s.upload(s.ann_client)
    s.start(s.ann_client)

    response = s.ann_client.post(f"/api/v1/images/{photo}/withdraw")

    assert response.status_code == 409
    assert "already been sent for analysis" in response.json()["error"]["message"]


# ------------------------------------------------------------------ protection
def test_the_ai_original_can_never_be_changed(
    db: Session, s: Setup, worker: list[str], use_detector: Any
) -> None:
    """FR-33: the database itself refuses changes to the AI's original answer."""
    s.upload(s.admin)
    s.start(s.admin)
    finding_id = db.scalar(select(Finding.id))

    for column, value in (
        ("predicted_confidence", "0.1"),
        ("predicted_type_key", "'pothole_x'"),
        ("predicted_bbox", "ARRAY[0,0,1,1]"),
        ("model_version", "'other'"),
        ("original_location", "NULL"),
    ):
        with pytest.raises(DBAPIError, match="cannot be changed"):
            db.execute(
                text(f"UPDATE findings SET {column} = {value} WHERE id = :id"),  # noqa: S608
                {"id": finding_id},
            )
        db.rollback()

    # Reviewer columns stay editable (used from P6).
    db.execute(text("UPDATE findings SET notes = 'checked' WHERE id = :id"), {"id": finding_id})
    db.commit()


def test_audit_records_who_started_analysis(
    db: Session, s: Setup, worker: list[str], use_detector: Any
) -> None:
    s.upload(s.admin)
    s.start(s.admin)

    actions = db.scalars(
        text("SELECT action FROM audit_events WHERE action = 'analysis.started'")
    ).all()

    assert len(actions) == 1
