"""Naperville plan, option A: a project in a city whose transfer test passed gets tested levels."""

from types import SimpleNamespace
from typing import Any

import pytest

from app.services import forecasting, road_risk


@pytest.fixture
def fake_live(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    pytest.importorskip("forecasting")
    from forecasting import live

    state = {"chicago": False, "passed": True, "inside": True}
    monkeypatch.setattr(live, "in_chicago", lambda _c, _e: state["chicago"])
    monkeypatch.setattr(live, "passed_transfer_test", lambda _a: state["passed"])
    monkeypatch.setattr(live, "in_area_boundary", lambda _c, _a, _e: state["inside"])
    monkeypatch.setattr(forecasting, "_area", lambda key: SimpleNamespace(key=key, name=key))
    return state


def test_which_tested_area_a_project_is_in(fake_live: dict[str, bool]) -> None:
    assert forecasting.tested_area_of(None, "POINT") == "naperville"
    fake_live["chicago"] = True
    assert forecasting.tested_area_of(None, "POINT") == "chicago"  # Chicago first, as before
    fake_live.update(chicago=False, passed=False)
    assert forecasting.tested_area_of(None, "POINT") is None  # no PASS: risk factors only
    fake_live.update(passed=True, inside=False)
    assert forecasting.tested_area_of(None, "POINT") is None  # outside the city


def test_an_area_not_set_up_here_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("forecasting")
    from forecasting import live

    def missing(_key: str) -> Any:
        raise SystemExit("no such area on this computer")

    monkeypatch.setattr(live, "in_chicago", lambda _c, _e: False)
    monkeypatch.setattr(forecasting, "_area", missing)
    assert forecasting.tested_area_of(None, "POINT") is None


def test_the_level_label_names_where_the_levels_were_tested() -> None:
    def row(level: int, key: str) -> Any:
        return SimpleNamespace(level=level, area_key=key)

    assert road_risk.level_label(row(2, "chicago")) == "Tested Chicago risk levels"
    assert road_risk.level_label(row(2, "naperville")) == (
        "Tested risk levels (Chicago model, tested on this city's reports)"
    )
    assert road_risk.level_label(row(1, "p_123")) == "Risk factors only (no pothole history here)"
