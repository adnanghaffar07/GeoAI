"""Shared setup for the analysis and review tests (loaded through `conftest.py`).

The queue is replaced by a function that runs the worker task straight away, so the whole
path (API -> job -> worker -> findings) runs inside the test.
"""

import dataclasses
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai import registry, stand_in
from app.core import queue
from app.workers.analysis_tasks import run_analysis_job
from tests.factories import add_member, add_to_project, create_project, make_org, sign_in
from tests.photos import INSIDE, make_photo

Detector = Callable[..., dict[str, Any]]


def _note(image_id: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "contract_version": 1,
        "model_version": stand_in.MODEL_VERSION,
        "image_id": image_id,
        "status": "ok",
        "failure_reason": None,
        "image_width_px": 400,
        "image_height_px": 300,
        "candidates": candidates,
        "processing_ms": 1,
    }


def two_candidates(photo_path: Path, *, image_id: str) -> dict[str, Any]:
    return _note(
        image_id,
        [
            {
                "detection_index": 0,
                "class_key": "pothole",
                "confidence": 0.91,
                "bbox_px": [10, 150, 110, 250],
            },
            {
                "detection_index": 1,
                "class_key": "surface_cracking",
                "confidence": 0.42,
                "bbox_px": [200, 160, 300, 290],
            },
        ],
    )


@pytest.fixture
def use_detector(monkeypatch: pytest.MonkeyPatch) -> Callable[[Detector], None]:
    """Swap the stand-in's detect function for a test one."""

    def swap(detect: Detector) -> None:
        spec = registry.MODELS[stand_in.MODEL_VERSION]
        monkeypatch.setitem(
            registry.MODELS, stand_in.MODEL_VERSION, dataclasses.replace(spec, detect=detect)
        )

    swap(two_candidates)
    return swap


@pytest.fixture
def worker(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Run jobs immediately instead of sending them to the queue. Yields the sent job IDs."""
    sent: list[str] = []

    def run_now(job_id: uuid.UUID) -> None:
        sent.append(str(job_id))
        run_analysis_job(str(job_id))

    monkeypatch.setattr(queue, "send_analysis_job", run_now)
    yield sent


@pytest.fixture
def queue_down(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(job_id: uuid.UUID) -> None:
        raise ConnectionError("queue is down")

    monkeypatch.setattr(queue, "send_analysis_job", refuse)


class Setup:
    def __init__(self, db: Session, make_client: Callable[[], TestClient]) -> None:
        org = make_org(db)
        self.ann = add_member(db, org, "ann@a.test", "org_member")
        self.bob = add_member(db, org, "bob@a.test", "org_member")
        self.rev = add_member(db, org, "rev@a.test", "org_member")
        self.view = add_member(db, org, "view@a.test", "org_member")
        self.admin = sign_in(make_client(), "admin@a.test")
        self.project_id = str(create_project(self.admin)["id"])
        for person, role in (
            (self.ann, "field_collector"),
            (self.bob, "field_collector"),
            (self.rev, "technical_reviewer"),
            (self.view, "viewer"),
        ):
            add_to_project(self.admin, self.project_id, person.user.id, role)
        self.ann_client = sign_in(make_client(), self.ann.email)
        self.bob_client = sign_in(make_client(), self.bob.email)
        self.reviewer = sign_in(make_client(), self.rev.email)
        self.viewer = sign_in(make_client(), self.view.email)

    def upload(self, client: TestClient, seed: int = 1, gps: bool = True) -> str:
        response = client.post(
            f"/api/v1/projects/{self.project_id}/images",
            files={
                "file": ("p.jpg", make_photo(seed=seed, gps=INSIDE if gps else None), "image/jpeg")
            },
        )
        assert response.status_code == 201, response.text
        image_id: str = response.json()["image"]["id"]
        return image_id

    def start(self, client: TestClient, image_ids: list[str] | None = None) -> Any:
        body = {"image_ids": image_ids} if image_ids is not None else {}
        return client.post(f"/api/v1/projects/{self.project_id}/analysis-jobs", json=body)

    def findings(self, client: TestClient, **params: str) -> Any:
        return client.get(f"/api/v1/projects/{self.project_id}/findings", params=params)


@pytest.fixture
def s(db: Session, make_client: Callable[[], TestClient]) -> Setup:
    return Setup(db, make_client)
