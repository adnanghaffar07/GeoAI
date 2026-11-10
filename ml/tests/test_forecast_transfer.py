"""Naperville plan N3: the transfer test's rules (no database)."""

from datetime import date
from types import SimpleNamespace

import pytest

from forecasting import transfer


def test_only_mondays_with_a_complete_30_day_answer():
    mondays = transfer.test_mondays(date(2025, 1, 1), newest_report=date(2025, 2, 10))
    assert mondays[0] == date(2025, 1, 6) and mondays[-1] == date(2025, 1, 6)  # 2025-01-13 + 30 days > 2025-02-10
    assert all(m.weekday() == 0 for m in transfer.test_mondays(date(2025, 1, 6), date(2026, 11, 9)))


def test_locked_test_needs_the_go_ahead_and_runs_once(tmp_path):
    area = SimpleNamespace(name="Testville", reports_dir=tmp_path)
    with pytest.raises(SystemExit, match="go-ahead"):
        transfer.run(None, area, {}, {}, {}, tmp_path, date(2025, 1, 6), owner_go_ahead=False)
    (tmp_path / transfer.RESULT_FILE).write_text("{}")
    with pytest.raises(SystemExit, match="once only"):
        transfer.run(None, area, {}, {}, {}, tmp_path, date(2025, 1, 6), owner_go_ahead=True)


def test_report_states_the_outcome_and_the_limits():
    m = {"value": 0.1, "low": 0.05, "high": 0.2}
    result = {
        "area": "Testville", "outcome": "PARTIAL", "pass_marks_note": "PLACEHOLDER", "model": "forecast-chicago-0.2",
        "test_mondays": ["2025-01-06", "2026-10-05", 92], "reports_from": "2023-01-01", "reports_to": "2026-11-09",
        "sections": 6000, "section_mondays_with_a_new_report": 900, "same_pothole_repeats_marked": 12,
        "results": {k: {"all": {"precision_at_top_1pct": m, "pr_auc": m}, "winter": {}} for k in ("B1", "B0")},
        "checks": {"1_precision_top_1pct_ratio": {"value": 1.0, "needed": ">= 1.15", "passed": False}},
    }  # fmt: skip
    text = transfer.markdown(result)
    assert "**Outcome: PARTIAL**" in text and "used unchanged" in text and "## Limits" in text
