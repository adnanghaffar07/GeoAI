"""Forecasting F2: learning table windows, no-cheating rules, measures, training rows, pass marks and the test lock."""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

import numpy as np
import pytest
from sklearn.metrics import average_precision_score

from forecasting import f2_build, f2_store, metrics, settings
from forecasting.f2_build import day_number, mondays
from forecasting.f2_store import FEATURES, FeatureStore, period_weeks

RULES = settings.rules()
CFG = settings.load_config("f2.yaml")


# ---------- windows: only days before the Monday; the answer is the Monday + 29 days ----------


def test_window_counts_history_and_label_edges():
    weeks = mondays(date(2020, 1, 6), date(2020, 3, 30))  # 13 Mondays
    monday = day_number(date(2020, 2, 3))
    w = int(np.flatnonzero(weeks == monday)[0])
    days = np.array([monday - 1, monday - 30, monday - 31, monday, monday + 29, monday + 30], dtype=np.int32)
    sections = np.zeros(len(days), dtype=np.int32)
    history = f2_build.window_counts(sections, days, weeks, 1, 30, 0)
    label = f2_build.window_counts(sections, days, weeks, 1, *f2_build.LABEL_WINDOW)
    # last 30 days before the Monday: the day before and 30 days before count; 31 days before and the Monday itself do not
    assert history[0, w] == 2
    # the answer: the Monday itself and Monday + 29 count, Monday + 30 does not
    assert label[0, w] == 2
    last_year = f2_build.window_counts(np.zeros(1, np.int32), np.array([monday - 340], np.int32), weeks, 1, 365, 335)
    assert last_year[0, w] == 1


def test_last_event_day_is_strictly_before_the_monday():
    weeks = mondays(date(2020, 1, 6), date(2020, 1, 27))
    days = np.array([weeks[1], weeks[1] - 3], dtype=np.int32)  # one ON the second Monday, one three days before
    last = f2_build.last_event_day(np.zeros(2, np.int32), days, weeks, 1)
    assert last[0].tolist() == [-1, weeks[1] - 3, weeks[1], weeks[1]]


def test_weather_uses_only_days_before_the_monday_and_skips_missing():
    first_day = day_number(date(2020, 1, 1))
    n = 60
    tmax, tmin = np.full(n, 5.0), np.full(n, 2.0)
    monday = date(2020, 2, 3)
    i = day_number(monday) - first_day
    tmin[i - 1] = -3.0  # freeze-thaw the day before
    tmin[i] = -3.0  # on the Monday itself: must not count
    tmax[i - 2], tmin[i - 2] = np.nan, np.nan  # missing day
    prcp = np.zeros(n)
    prcp[i - 3] = 30.0
    daily = {"tmax": tmax, "tmin": tmin, "prcp": prcp, "snow": np.zeros(n)}
    out = f2_build.weather_features(daily, first_day, np.array([day_number(monday)]))
    assert out["freeze_thaw_7d"][0] == 1
    assert out["heavy_rain_days_30d"][0] == 1 and out["rain_mm_7d"][0] == 30
    assert out["days_since_freeze"][0] == 1


def test_bands_and_static_facts():
    assert f2_build.band(None, [5000, 15000, 30000]) == 0
    assert [f2_build.band(v, [5000, 15000, 30000]) for v in (100, 5000, 20000, 90000)] == [1, 2, 3, 4]
    row = ("s1", "secondary", 100.0, "2;3", "asphalt", False, 12.0, -1.0, True, False, 9000, None, 2, "X")
    static = f2_build.static_arrays([row], [5000, 15000, 30000], [250, 1000, 2500])
    assert static["highway_code"][0] == 4 and static["lanes"][0] == 2 and static["surface_code"][0] == 1
    assert static["probably_bridge"][0] == 1 and static["traffic_band"][0] == 2 and static["heavy_vehicle_band"][0] == 0


# ---------- a small made-up city ----------


def synthetic_city(
    n_sections: int = 120,
    seed: int = 1,
    held_out_every: int = 6,
    last: date = date(2025, 6, 30),
    reports_until: date = date(2025, 8, 15),
) -> FeatureStore:
    """Sections with different pothole tendencies, reports from 2011 to 2025 (or later), and fake weather."""
    rng = np.random.default_rng(seed)
    first = date(2012, 1, 2)
    weeks = mondays(first, last)
    start_day, end_day = day_number(date(2011, 1, 1)), day_number(reports_until)
    tendency = rng.gamma(0.6, 1.0, n_sections) * 0.01  # reports per day
    sections, days = [], []
    for s in range(n_sections):
        count = rng.poisson(tendency[s] * (end_day - start_day))
        sections += [s] * count
        days += rng.integers(start_day, end_day, count).tolist()
    sections, days = np.array(sections, np.int32), np.array(days, np.int32)
    arrays = {"weeks": weeks}
    for name, (a, b) in f2_build.HISTORY_WINDOWS.items():
        arrays[name] = np.ascontiguousarray(f2_build.window_counts(sections, days, weeks, n_sections, a, b).T)
    label = f2_build.window_counts(sections, days, weeks, n_sections, *f2_build.LABEL_WINDOW)
    arrays["label"] = np.ascontiguousarray((label > 0).astype(np.int8).T)
    arrays["last_report_day"] = np.ascontiguousarray(f2_build.last_event_day(sections, days, weeks, n_sections).T)
    for name, values in f2_build.extra_history(sections, days, weeks, n_sections).items():
        arrays[name] = np.ascontiguousarray(values.T)
    dup = rng.random(len(days)) < 0.3  # pretend 30% of reports also had a duplicate
    for name, (a, b) in f2_build.DUPLICATE_WINDOWS.items():
        arrays[name] = np.ascontiguousarray(f2_build.window_counts(sections[dup], days[dup], weeks, n_sections, a, b).T)
    arrays["neighbour_rows"] = np.arange(n_sections - 1, dtype=np.int32)
    arrays["neighbour_cols"] = np.arange(1, n_sections, dtype=np.int32)
    arrays["station_of_section"] = np.zeros(n_sections, np.int16)
    for name in f2_store.WEATHER:
        arrays[f"weather__{name}"] = rng.random((1, len(weeks))).astype(np.float32) * 10
    for name in f2_store.STATIC:
        arrays[f"static__{name}"] = rng.integers(0, 4, n_sections).astype(np.float32)
    arrays["held_out"] = np.arange(n_sections) % held_out_every == 0
    meta = {"section_ids": [f"s{i}" for i in range(n_sections)], "stations": ["X"], "first_monday": str(first), "last_monday": str(last)}
    return FeatureStore(arrays, meta)


def test_feature_rows_match_the_arrays():
    store = synthetic_city(10)
    w = 100
    x = store.matrix(w)
    assert x.shape == (10, len(FEATURES))
    col = FEATURES.index("reports_90d")
    assert np.array_equal(x[:, col], store.a["reports_90d"][w].astype(np.float32))
    nb = FEATURES.index("neighbour_reports_30d")
    assert x[3, nb] == store.a["reports_30d"][w][4]  # section 3's only neighbour is section 4
    assert x[:, FEATURES.index("new_311_system")].max() == float(store.monday(w) >= date(2018, 12, 18))
    assert store.matrix(w, drop=["traffic_band"]).shape[1] == len(FEATURES) - 1


def test_purge_keeps_answer_windows_inside_the_period():
    store = synthetic_city(5)
    p = RULES["periods"]
    train = period_weeks(store, p["train"], p["validation"]["start"], 30)
    last_train = store.monday(int(train[-1]))
    assert last_train + timedelta(days=30) <= date.fromisoformat(str(p["validation"]["start"]))
    assert last_train < date.fromisoformat(str(p["train"]["end"]))  # the final Mondays were left out
    assert store.monday(int(train[0])) == date.fromisoformat(str(p["train"]["start"]))


# ---------- measures ----------


def test_top_mask_and_weekly_stats():
    rng = np.random.default_rng(0)
    rank = np.arange(200, dtype=float)
    label = np.zeros(200, dtype=np.int8)
    label[-2:] = 1  # the two highest-ranked sections are the only positives
    stats = metrics.weekly_stats(rank, rank / 200, label, rng, 0.01, 0.10)
    assert stats["precision_top"] == 1.0 and stats["recall_top"] == 1.0 and stats["positives"] == 2
    assert metrics.top_mask(np.zeros(1000), 0.01, rng).sum() == 10  # ties: still exactly 1%


def test_histogram_ap_matches_sklearn_for_distinct_scores():
    rng = np.random.default_rng(3)
    score = rng.random(500)
    label = (rng.random(500) < score).astype(int)
    order = np.argsort(-score)
    ap = metrics.ap_from_histograms(label[order].astype(float), 1 - label[order].astype(float))
    assert ap == pytest.approx(average_precision_score(label, score))


def test_scorer_summary_has_ranges():
    scorer = metrics.Scorer(0.01, 0.10, seed=1)
    rng = np.random.default_rng(1)
    for week in range(20):
        prob = rng.random(300)
        label = (rng.random(300) < prob * 0.3).astype(np.int8)
        scorer.add(week, prob, prob, label, winter=week % 2 == 0)
    summary = scorer.summary("all", resamples=200, bins=200)
    for name in ("precision_at_top_1pct", "recall_at_top_10pct", "pr_auc", "brier"):
        cell = summary[name]
        assert cell["low"] <= cell["value"] <= cell["high"]
    assert scorer.summary("winter", 50, 50)["mondays"] == 10


# ---------- training rows, pass marks, the full run and the test lock ----------


def test_training_rows_never_use_held_out_areas_and_weights_undo_sampling():
    from forecasting.f2_train import training_rows

    store = synthetic_city(60)
    weeks = np.arange(200, 260)
    x, y, w, info = training_rows(store, weeks, {"max_rows": 10_000_000, "negative_fraction": 0.2}, seed=5)
    assert len(y) == len(x) == len(w)
    held_rows = store.held_out
    # every positive among eligible sections is kept
    assert int(y.sum()) == sum(int(store.label(k)[~held_rows].sum()) for k in weeks)
    assert set(np.unique(w[y == 1])) == {1.0} and np.allclose(w[y == 0], 5.0)
    # rows never come from held-out sections: check via a unique static value
    store.a["static__length_m"] = np.where(held_rows, -999.0, 1.0).astype(np.float32)
    x2, *_ = training_rows(store, weeks, {"max_rows": 10_000_000, "negative_fraction": 0.2}, seed=5)
    assert not np.any(x2[:, FEATURES.index("length_m")] == -999.0)


def cell(value, low=None):
    return {"value": value, "low": value if low is None else low, "high": value}


def fake_results(main_p, base_p, main_ap, base_ap, main_brier, base_brier):
    def model(p, ap, brier):
        subset = {"precision_at_top_1pct": cell(p), "pr_auc": cell(ap), "brier": cell(brier)}
        return {"all": subset, "winter_nov_apr": subset, "held_out_areas": subset}

    return {
        "M_lightgbm": model(main_p, main_ap, main_brier),
        "B0_rule": model(base_p, base_ap, base_brier),
        "B1_logistic": model(0.1, 0.1, 0.2),
    }


def test_pass_marks_pass_partial_fail():
    from forecasting.f2_test import check_pass_marks

    marks = RULES["pass_marks"]
    assert check_pass_marks(fake_results(0.5, 0.4, 0.5, 0.4, 0.05, 0.06), "M_lightgbm", marks)["outcome"] == "PASS"
    partial = check_pass_marks(fake_results(0.42, 0.4, 0.5, 0.4, 0.05, 0.06), "M_lightgbm", marks)
    assert partial["outcome"] == "PARTIAL" and not partial["checks"]["1_precision_top_1pct_ratio"]["passed"]
    assert check_pass_marks(fake_results(0.3, 0.4, 0.3, 0.4, 0.07, 0.06), "M_lightgbm", marks)["outcome"] == "FAIL"


def test_main_model_ranks_by_raw_score_and_calibrates_only_the_probability():
    from forecasting.f2_train import make_predictors

    class Fixed:
        def predict_proba(self, x):
            p = x[:, 0] / 10
            return np.column_stack([1 - p, p])

    class Steps:  # a calibrator that maps everything to one value (the worst case for ties)
        def predict(self, raw):
            return np.full(len(raw), 0.2)

    predictors = make_predictors([0.1] * 11, None, Fixed(), Steps(), Fixed(), Steps(), [])
    rank, prob = predictors["M_lightgbm"][0](np.array([[1.0], [3.0], [2.0]]))
    assert rank.tolist() == pytest.approx([0.1, 0.3, 0.2]) and prob.tolist() == [0.2, 0.2, 0.2]


def test_full_run_on_a_made_up_city_and_the_test_runs_only_once(tmp_path):
    from forecasting import f2_report
    from forecasting.f2_test import run_locked_test
    from forecasting.f2_train import train_and_validate

    store = synthetic_city(150)
    cfg = dict(CFG)
    cfg["lightgbm_grid"] = [{"num_leaves": 7, "learning_rate": 0.1, "n_estimators": 40, "min_child_samples": 20}]
    cfg["training_sample"] = {"max_rows": 20_000, "negative_fraction": 0.2}
    rules = json.loads(json.dumps(RULES, default=str))
    rules["measures"]["bootstrap"]["resamples"] = 50
    models, reports = tmp_path / "models", tmp_path / "reports"
    result = train_and_validate(store, rules, cfg, models)
    val = result["validation"]
    # the made-up city has strong, stable section tendencies: history-based models must beat chance clearly
    assert val["M_lightgbm"]["all"]["pr_auc"]["value"] > val["M_lightgbm"]["all"]["base_rate"]
    assert (models / "f2-models.json").exists()
    assert "# F2 validation report" in f2_report.validation_markdown(result)

    with pytest.raises(SystemExit, match="main model"):
        run_locked_test(store, rules, cfg, models, reports, "bogus")
    test = run_locked_test(store, rules, cfg, models, reports, "with_traffic")
    assert test["verdict"]["outcome"] in {"PASS", "PARTIAL", "FAIL"}
    assert "# F2 locked test report" in f2_report.test_markdown(test)
    with pytest.raises(SystemExit, match="already been run"):
        run_locked_test(store, rules, cfg, models, reports, "with_traffic")

    # training again continues from the saved parts: no model is trained a second time
    import forecasting.f2_train as f2_train_module

    def no_training(*_args, **_kwargs):
        raise AssertionError("a saved part was trained again")

    original = f2_train_module.make_m
    f2_train_module.make_m = no_training
    try:
        again = train_and_validate(store, rules, cfg, models)
    finally:
        f2_train_module.make_m = original
    assert again["validation"]["M_lightgbm"]["all"] == val["M_lightgbm"]["all"]

    # a changed model file is refused
    (reports / "f2-test-usage.json").unlink()
    (models / "b0_table.json").write_text('{"cap": 10, "rates": []}')
    with pytest.raises(SystemExit, match="fingerprint"):
        run_locked_test(store, rules, cfg, models, reports, "with_traffic")


# ---------- the learning table from a real PostGIS database (the F1 test fixture) ----------

TEST_DB = os.environ.get("FORECAST_TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_DB, reason="set FORECAST_TEST_DATABASE_URL to run the PostGIS test")
def test_extract_from_the_database(tmp_path):

    from forecasting import load
    from tests.test_forecast_load import SRC, make_raw_dir

    raw = tmp_path / "raw"
    make_raw_dir(raw)
    load.run_load(TEST_DB, raw, SRC, RULES)
    out = tmp_path / "f2"
    with settings.connect(TEST_DB, SRC["schema"], autocommit=True) as conn:
        f2_build.build(conn, out, date(2017, 1, 2), date(2017, 3, 27), CFG, 20)
        progress = json.loads((out / "progress.json").read_text())
        assert {
            "sections",
            "history",
            "history_extra",
            "neighbours",
            "weather",
            "static",
            "events_2017",
            "events_2019",
            "duplicates_2017",
        } <= set(progress["done"])
        # a second run continues: nothing is redone (the saved parts are reused as they are)
        before = (out / "reports_30d.npy").stat().st_mtime_ns
        f2_build.build(conn, out, date(2017, 1, 2), date(2017, 3, 27), CFG, 20)
        assert (out / "reports_30d.npy").stat().st_mtime_ns == before
        # different settings: that folder starts fresh
        other = dict(CFG, neighbour_distance_m=150)
        f2_build.build(conn, out, date(2017, 1, 2), date(2017, 3, 27), other, 20)
        assert (out / "reports_30d.npy").stat().st_mtime_ns != before
        f2_build.build(conn, out, date(2017, 1, 2), date(2017, 3, 27), CFG, 20)
    store = FeatureStore.load(out)
    assert store.n_sections == 9 and len(store.weeks) == 13
    # report H1 (2017-02-01, ~11 m from the road) is the only usable one in 2017: answer = 1 for Mondays 2017-01-09 .. 2017-01-30
    w = store.week_index(date(2017, 1, 30))
    assert store.label(w).sum() >= 1 and store.label(store.week_index(date(2017, 1, 2))).sum() == 0
    after = store.matrix(store.week_index(date(2017, 2, 6)))
    assert after[:, FEATURES.index("reports_30d")].max() == 1  # counted in history only after the report day
    # H2 (2017-02-02) is a duplicate: an input in the duplicate count, never an answer
    assert after[:, FEATURES.index("duplicate_reports_30d")].max() == 1
    assert after[:, FEATURES.index("traffic_band")].max() == 2  # 12,000 vehicles per day = "medium" (5,000-15,000)

    # F4b: the inputs for one Monday, straight from the database, equal the learning table's
    from forecasting import weekly

    with settings.connect(TEST_DB, SRC["schema"]) as conn:
        assert weekly.seed_from_learning_table(conn, out)["events"] >= 1
        assert weekly.seed_from_learning_table(conn, out) == {"seeded": 0}  # only once
        conn.commit()
        result = weekly.check(conn, store, [date(2017, 1, 2), date(2017, 2, 6), date(2017, 3, 27)], CFG, "EPSG:26916")
        assert result["passed"], result
        assert weekly.match_new_reports(conn, 20) == 0  # every report was already looked at


def test_locked_test_continues_after_a_stop_and_then_locks(tmp_path):
    import forecasting.f2_test as f2_test_module
    from forecasting.f2_test import run_locked_test
    from forecasting.f2_train import train_and_validate

    store = synthetic_city(80)
    cfg = dict(CFG)
    cfg["lightgbm_grid"] = [{"num_leaves": 7, "learning_rate": 0.1, "n_estimators": 20, "min_child_samples": 20}]
    cfg["training_sample"] = {"max_rows": 10_000, "negative_fraction": 0.2}
    rules = json.loads(json.dumps(RULES, default=str))
    rules["measures"]["bootstrap"]["resamples"] = 20
    models, reports = tmp_path / "models", tmp_path / "reports"
    train_and_validate(store, rules, cfg, models)

    # first try stops after two models (simulated power cut)
    original = f2_test_module.summarise
    calls = {"n": 0}

    def stop_after_two(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] > 2:
            raise KeyboardInterrupt
        return original(*args, **kwargs)

    f2_test_module.summarise = stop_after_two
    try:
        with pytest.raises(KeyboardInterrupt):
            run_locked_test(store, rules, cfg, models, reports, "with_traffic")
    finally:
        f2_test_module.summarise = original
    assert json.loads((reports / "f2-test-usage.json").read_text())["status"] == "started"
    with pytest.raises(SystemExit, match="continue it with that choice"):
        run_locked_test(store, rules, cfg, models, reports, "without_traffic")

    # second try continues: only the last two models are scored
    counted = {"n": 0}

    def count(*args, **kwargs):
        counted["n"] += 1
        return original(*args, **kwargs)

    f2_test_module.summarise = count
    try:
        result = run_locked_test(store, rules, cfg, models, reports, "with_traffic")
    finally:
        f2_test_module.summarise = original
    assert counted["n"] == 2 and result["usage"]["status"] == "finished"
    with pytest.raises(SystemExit, match="already been run"):
        run_locked_test(store, rules, cfg, models, reports, "with_traffic")


def test_progress_and_checkpoints(tmp_path, capsys):
    from forecasting.checkpoints import Checkpoints, Progress

    progress = Progress("Mondays", 4, every=0)
    for _ in range(4):
        progress.step()
    out = capsys.readouterr().out
    assert "Mondays 1/4" in out and "Mondays 4/4" in out and "done" in out
    cp = Checkpoints(tmp_path / "work", "a")
    cp.mark("part1", {"x": 1})
    (tmp_path / "work" / "data.npy").write_bytes(b"x")
    assert Checkpoints(tmp_path / "work", "a").info("part1") == {"x": 1}
    fresh = Checkpoints(tmp_path / "work", "b")  # inputs changed
    assert not fresh.done("part1") and not (tmp_path / "work" / "data.npy").exists()


def test_extra_history_windows_only_look_back():
    weeks = mondays(date(2019, 1, 7), date(2020, 3, 30))
    monday = day_number(date(2020, 2, 3))
    w = int(np.flatnonzero(weeks == monday)[0])
    days = np.array(
        [
            monday - 3,  # last 7 days
            monday - 10,  # last 14 days
            monday - 365,  # same date a year ago: same season, and the last full year
            monday - 365 - 31,  # 31 days before last year's date: outside "same season"
            monday,  # the Monday itself: never an input
        ],
        dtype=np.int32,
    )
    out = f2_build.extra_history(np.zeros(len(days), np.int32), days, weeks, 1)
    assert out["reports_7d"][0, w] == 1 and out["reports_14d"][0, w] == 2
    assert out["reports_same_season_3y"][0, w] == 1
    assert out["years_with_reports_5y"][0, w] == 2  # this year's block and last year's block both had reports
    assert out["reports_all_before"][0, w] == 4


# ---------- F4a: refresh before percentages are shown ----------


def first_weeks(store: FeatureStore, n: int) -> FeatureStore:
    """The same city cut at its first n Mondays (what the F2 table holds when the extended table goes further)."""
    total = len(store.weeks)
    arrays = {}
    for name, values in store.a.items():
        values = np.asarray(values)
        if name == "weeks":
            arrays[name] = values[:n]
        elif name.startswith("weather__"):
            arrays[name] = values[:, :n]
        elif values.ndim == 2 and values.shape[0] == total:
            arrays[name] = values[:n]
        else:
            arrays[name] = values
    return FeatureStore(arrays, dict(store.meta))


def test_f4a_dates():
    from forecasting.f4a import last_complete_monday

    assert last_complete_monday(date(2026, 10, 27)) == date(2026, 9, 28)  # 28 Sep + 29 days = 27 Oct
    assert last_complete_monday(date(2026, 10, 26)) == date(2026, 9, 21)


def test_f4a_refresh_on_a_made_up_city(tmp_path):
    from forecasting import f4a
    from forecasting.f2_train import train_and_validate

    new = synthetic_city(150, last=date(2026, 9, 28), reports_until=date(2026, 10, 28))
    old = first_weeks(new, len(mondays(date(2012, 1, 2), date(2025, 6, 30))))
    cfg = dict(CFG)
    cfg["lightgbm_grid"] = [{"num_leaves": 7, "learning_rate": 0.1, "n_estimators": 40, "min_child_samples": 20}]
    cfg["training_sample"] = {"max_rows": 20_000, "negative_fraction": 0.2}
    rules = json.loads(json.dumps(RULES, default=str))
    rules["measures"]["bootstrap"]["resamples"] = 30
    models, reports = tmp_path / "models", tmp_path / "reports"
    train_and_validate(old, rules, cfg, models)
    result = f4a.run(new, old, rules, cfg, models, reports)
    assert result["overlap_with_f2"]["same"] is True
    assert result["periods"]["fresh_check"][0] == "2025-08-04"  # 30 days after the locked test, then the next Monday
    assert set(result["fresh_check"]) == {"B0_rule", "B1_logistic", "M_lightgbm", "M_lightgbm_without_traffic"}
    assert len(result["percentage_check"]["calibrated"]["table"]) == 10
    assert (models / "b1_logistic_v0.2.joblib").exists() and len(result["model_v02"]["fingerprints"]) == 2
    assert result["criteria"]["suggestion"] in {"show percentages for Chicago (TRIAL)", "show levels only"}
    assert "# F4a: Chicago model refresh" in f4a.markdown(result)
    # a second run continues from the saved parts and gives the same answer
    again = f4a.run(new, old, rules, cfg, models, reports)
    same = lambda x, y: json.dumps(x, default=str) == json.dumps(y, default=str)  # noqa: E731 (tuples come back as lists)
    assert same(again["fresh_check"], result["fresh_check"]) and same(again["percentage_check"], result["percentage_check"])
    # a changed F2 table is caught by the overlap check
    changed = first_weeks(new, len(old.weeks))
    changed.a["label"] = np.asarray(changed.a["label"]).copy()
    changed.a["label"][0, 0] = 1 - changed.a["label"][0, 0]
    assert f4a.compare_overlap(changed, new)["different"] == ["label"]
