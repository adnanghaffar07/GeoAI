# ruff: noqa: E501
"""CR-006 "Ask about road risk" (free local model).

Answers from the app's data, links, "I don't know", no percentage, permissions, the on/off switch,
the daily limit, and the model reply check."""

from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AuditEvent
from app.services import assistant
from tests.analysis_fixtures import Setup
from tests.test_road_risk import _url, seed


@pytest.fixture
def no_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assistant, "call_model", lambda _q, _f: None)


def _on(s: Setup) -> None:
    response = s.admin.put(_url(s, "forecast-settings"), json={"assistant_enabled": True})
    assert response.status_code == 200 and response.json()["assistant_enabled"] is True


def _ask(client: Any, s: Setup, question: str) -> Any:
    return client.post(_url(s, "assistant"), json={"question": question})


def test_off_until_the_manager_switches_it_on(s: Setup, db: Session, no_model: None) -> None:
    seed(db, s.project_id)
    assert _ask(s.admin, s, "Which roads first?").status_code == 409
    assert (
        s.viewer.put(_url(s, "forecast-settings"), json={"assistant_enabled": True}).status_code
        == 403
    )
    _on(s)
    assert _ask(s.viewer, s, "Which roads should we inspect first?").status_code == 200
    assert (
        _ask(s.ann_client, s, "Which roads first?").status_code == 403
    )  # road risk hidden from collectors


def test_answers_come_from_the_data_with_links(s: Setup, db: Session, no_model: None) -> None:
    data = seed(db, s.project_id)
    _on(s)
    top = _ask(s.reviewer, s, "Which roads should we inspect first, and why?").json()
    assert top["used_model"] is False and top["answer"].startswith(
        "The levels are from Monday 2026-10-26"
    )
    assert (
        "Road A is high risk (number 1 on the list) because of: Pothole reports here, last 12 months: 4"
        in top["answer"]
    )
    assert {
        "label": "Road A",
        "path": f"/projects/{s.project_id}/road-risk/{data['sections']['a'].id}",
    } in top["sources"]
    assert "%" not in str(top) and top["label"].startswith("TRIAL FORECAST")

    why = _ask(s.reviewer, s, "Why is Road B risky?").json()
    assert "Road B is medium risk" in why["answer"] and len(why["sources"]) == 1

    unknown_road = _ask(s.reviewer, s, "Why is Elm Avenue high risk?").json()
    assert unknown_road["answer"].startswith("I don't know")

    cost = _ask(s.reviewer, s, "How much will the repairs cost?").json()
    assert cost["answer"].startswith("I don't know") and cost["sources"] == []

    waiting = _ask(s.reviewer, s, "Which high-risk roads have no inspection planned?").json()
    assert (
        "High-risk roads with no open inspection" in waiting["answer"]
        and "Road A" in waiting["answer"]
    )

    weather = _ask(s.reviewer, s, "Will the weather this week affect our roads?").json()
    assert (
        "1 freeze-thaw days" in weather["answer"]
        and "National Weather Service" in weather["answer"]
    )

    alerts = _ask(s.viewer, s, "Any alerts?").json()
    assert alerts["answer"].endswith("Alerts go to project managers only.")


def test_model_replies_are_checked(s: Setup, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    seed(db, s.project_id)
    _on(s)
    monkeypatch.setattr(
        assistant, "call_model", lambda _q, _f: "Road A has a 73% chance of potholes."
    )
    bad = _ask(s.admin, s, "Which roads first?").json()
    assert bad["used_model"] is False and "73" not in bad["answer"]  # refused: a percentage
    monkeypatch.setattr(
        assistant,
        "call_model",
        lambda _q, _f: "Inspect Road A first: it is high risk with 4 reports in 12 months.",
    )
    good = _ask(s.admin, s, "Which roads first?").json()
    assert good["used_model"] is True and good["answer"].startswith("Inspect Road A first")
    assert assistant.check_reply("Road A had 9 reports.", "Road A: 4") is False  # a new number


def test_questions_are_kept_and_limited(
    s: Setup, db: Session, no_model: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(db, s.project_id)
    _on(s)
    monkeypatch.setenv("ASSISTANT_DAILY_LIMIT", "2")
    get_settings.cache_clear()
    try:
        assert _ask(s.reviewer, s, "Which roads first?").json()["questions_left_today"] == 1
        assert _ask(s.reviewer, s, "Which roads first?").status_code == 200
        assert _ask(s.reviewer, s, "Which roads first?").status_code == 429
    finally:
        get_settings.cache_clear()
    events = list(db.scalars(select(AuditEvent).where(AuditEvent.action == "assistant.asked")))
    assert len(events) == 2 and events[0].details["question"] == "Which roads first?"
    switched = db.execute(
        text("SELECT count(*) FROM audit_events WHERE action = 'assistant.switched_on'")
    ).scalar()
    assert switched == 1
