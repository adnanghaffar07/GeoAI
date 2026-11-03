"""Forecasting command line. Run from the ml/ folder. Every command takes --area (default: chicago).

python -m forecasting.run --area naperville area-check        # boundary, weather stations, roads -> reports/<area>/area-check.md
python -m forecasting.run --area naperville download          # all raw files into forecasting/data/<area>/raw/
python -m forecasting.run --area naperville load              # into the area's schema of the separate `forecast` database
python -m forecasting.run --area naperville level1            # Level 1 risk factors -> reports/<area>/level1-risk-factors.md

Chicago (Level 2, has pothole history):
python -m forecasting.run download --terms-confirmed          # city portal data needs the owner's OK of its terms
python -m forecasting.run report                              # reports/chicago/f1-data-report.md
python -m forecasting.run f2-build | f2-train | f2-test ...   # F2 learning table, training, locked test (used once)
python -m forecasting.run move-to-areas                       # one-time move of the old one-area files and tables
python -m forecasting.run same-results-check                  # proves Chicago gives the same results with this code
python -m forecasting.run risk-cutoffs-draft                  # Level 1 cut-offs drafted from Chicago's training years
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from forecasting import areas, settings
from forecasting.download import download_all, read_manifest
from forecasting.load import run_load
from forecasting.report import write_report

LEVEL2_STEPS = {"report", "f2-build", "f2-train", "f2-test", "same-results-check", "risk-cutoffs-draft", "f4a-refresh", "weekly-check"}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m forecasting.run", description="Forecasting pipeline for one area.")
    parser.add_argument(
        "--area", default="chicago", help=f"area file in config/areas/ (default chicago; have: {', '.join(areas.available())})"
    )
    steps = parser.add_subparsers(dest="step", required=True)
    for name, text in (("area-check", "what data the area has; chooses weather stations"), ("download", "download raw files")):
        cmd = steps.add_parser(name, help=text)
        cmd.add_argument("--terms-confirmed", "--chicago-terms-confirmed", dest="terms_confirmed", action="store_true",
                         help="you read and accept the city open data portal's terms")  # fmt: skip
        if name == "download":
            cmd.add_argument("--only", help="download one item, e.g. potholes_current or osm_roads")
            cmd.add_argument("--force", action="store_true", help="download again even if the file exists")
    steps.add_parser("load", help="load raw files into the area's schema of the forecast database")
    steps.add_parser("level1", help="Level 1 risk factors for every section (factors, never a percentage)")
    steps.add_parser("report", help="write the F1 data report (areas with pothole history)")
    f2_build_cmd = steps.add_parser("f2-build", help="F2: build the learning table (continues after a stop)")
    f2_build_cmd.add_argument("--restart", action="store_true", help="throw away saved parts and start again")
    f2_train_cmd = steps.add_parser("f2-train", help="F2: train B0, B1, M and write the validation report (continues after a stop)")
    f2_train_cmd.add_argument("--restart", action="store_true", help="throw away saved parts and start again")
    test = steps.add_parser("f2-test", help="F2: the locked test, run once, only with the owner's go-ahead")
    test.add_argument("--owner-go-ahead", action="store_true", help="the owner has read the validation report and approves")
    test.add_argument("--main-model", choices=["with_traffic", "without_traffic"], default="without_traffic")
    steps.add_parser("move-to-areas", help="one-time: move the old one-area files and tables into the chicago area")
    steps.add_parser("same-results-check", help="Chicago: reload and rebuild with this code and compare with the saved results")
    steps.add_parser("risk-cutoffs-draft", help="Chicago: draft the Level 1 cut-offs from the training years")
    steps.add_parser("weekly-check", help="Chicago: one-Monday inputs (for the app) must equal the learning table's")
    steps.add_parser("f4a-refresh", help="Chicago: fresh check on never-used months, percentage check, model forecast-chicago-0.2")
    args = parser.parse_args(argv)

    rules = settings.rules()
    if args.step == "move-to-areas":
        from forecasting import migrate

        moved = migrate.run(settings.database_url())
        print("Moved tables: " + (", ".join(moved["tables"]) or "none (already done)"))
        print("Moved folders: " + ("; ".join(moved["files"]) or "none (already done)"))
        return
    area = areas.load_area(areas.check_name(args.area))
    old_layout = settings.FORECAST_DIR / "data" / "raw"
    if area.key == "chicago" and old_layout.exists() and not area.raw_dir.exists():
        raise SystemExit("Chicago's files are still in the old layout. Run `python -m forecasting.run move-to-areas` first.")
    if args.step in LEVEL2_STEPS and not area.has_potholes:
        raise SystemExit(f"{area.name} has no pothole history (Level 1 only): '{args.step}' needs a Level 2 area.")

    if args.step == "area-check":
        from forecasting import area_check

        path = area_check.run(area, rules, args.terms_confirmed)
        print(f"Area check written: {path}")
    elif args.step == "download":
        download_all(
            area.raw_dir,
            areas.ready_sources(area, need_box=False),
            rules,
            terms_confirmed=args.terms_confirmed,
            only=args.only,
            force=args.force,
        )
        print(f"Done. Files and manifest in {area.raw_dir}")
    elif args.step == "load":
        details = run_load(settings.database_url(), area.raw_dir, areas.ready_sources(area), rules, schema=area.schema)
        built, held = details["sections"]["sections_built"], details["held_out_community_areas"]
        print(f"Loaded {area.name}. {built:,} sections built; held-out areas: {held}")
    elif args.step == "level1":
        from forecasting import risk_factors

        with settings.connect(settings.database_url(), area.schema) as conn:
            path = risk_factors.run(conn, areas.ready_sources(area), settings.load_config("f2.yaml"), area.reports_dir)
        print(f"Level 1 risk factors written: {path}")
    elif args.step == "report":
        with settings.connect(settings.database_url(), area.schema) as conn:
            path = write_report(conn, rules, areas.ready_sources(area), read_manifest(area.raw_dir), area.reports_dir)
        print(f"Report written: {path}")
    else:
        run_level2(args, rules, area)


def f2_settings(area: areas.Area) -> dict:
    cfg = settings.load_config("f2.yaml")
    if area.src.get("snow_station"):
        cfg["snow_station"] = area.src["snow_station"]  # Chicago: O'Hare, the same value as in f2.yaml
    return cfg


def run_level2(args: argparse.Namespace, rules: dict, area: areas.Area) -> None:
    from forecasting import f2_build, f2_report  # imported here so the data steps run without the F2 packages
    from forecasting.f2_store import FeatureStore

    cfg = f2_settings(area)
    url = settings.database_url()
    if args.step == "same-results-check":
        from forecasting import check

        path, passed = check.run(url, area, rules, cfg)
        print(f"Same-results check {'PASSED' if passed else 'FAILED'}: {path}")
        if not passed:
            raise SystemExit(4)
        return
    if args.step == "weekly-check":
        from forecasting import weekly

        f4a_dir = area.data_dir / "f4a"
        table = FeatureStore.load(f4a_dir)
        with settings.connect(url, area.schema) as conn:
            print("  filling report_matches from the learning table (once; a minute or two)", flush=True)
            seeded = weekly.seed_from_learning_table(conn, f4a_dir)
            conn.commit()
            print(f"  seeded: {seeded}", flush=True)
            mondays = weekly.default_check_mondays(table)
            print(f"  comparing {len(mondays)} Mondays: {', '.join(map(str, mondays))}", flush=True)
            result = weekly.check(conn, table, mondays, cfg, area.crs)
        lines = ["# Weekly inputs check (one Monday vs the learning table)", "",
                 f"Result: **{'PASSED' if result['passed'] else 'FAILED'}**", "",
                 "| Monday | Sections | Same | Differing inputs |", "|---|---|---|---|"]  # fmt: skip
        for r in result["mondays"]:
            lines.append(f"| {r['monday']} | {r['sections']:,} | {'yes' if r['same'] else '**NO**'} | {r['differing_inputs']} |")
        path = f2_report.write(result, area.reports_dir, "weekly-check", "\n".join(lines) + "\n")
        print(f"Weekly inputs check {'PASSED' if result['passed'] else 'FAILED'}: {path}")
        if not result["passed"]:
            raise SystemExit(4)
        return
    if args.step == "f4a-refresh":
        from forecasting import f4a

        with settings.connect(url, area.schema) as conn:
            last_report = conn.execute("SELECT max(created_at)::date FROM pothole_reports").fetchone()[0]
        last_monday = f4a.last_complete_monday(last_report - timedelta(days=1))  # the download day itself may be partial
        f4a_dir = area.data_dir / "f4a"
        print(
            f"  extended learning table: Mondays 2012-01-02 to {last_monday} (reports up to {last_report}; saved part by part)", flush=True
        )
        with settings.connect(url, area.schema, autocommit=True) as conn:
            f2_build.build(
                conn,
                f4a_dir,
                date.fromisoformat(str(rules["periods"]["train"]["start"])),
                last_monday,
                cfg,
                rules["target"]["match_distance_m"],
                crs=area.crs,
            )
        result = f4a.run(FeatureStore.load(f4a_dir), FeatureStore.load(area.f2_dir), rules, cfg, area.models_dir, area.reports_dir)
        path = f2_report.write(result, area.reports_dir, "f4a-refresh-report", f4a.markdown(result))
        print(f"F4a report written: {path}  Suggestion: {result['criteria']['suggestion']}")
        return
    if args.step == "f2-build":
        periods = rules["periods"]
        with settings.connect(url, area.schema, autocommit=True) as conn:
            f2_build.build(
                conn,
                area.f2_dir,
                date.fromisoformat(str(periods["train"]["start"])),
                date.fromisoformat(str(periods["test_locked"]["end"])),
                cfg,
                rules["target"]["match_distance_m"],
                fresh=args.restart,
                crs=area.crs,
            )
        print(f"Learning table saved in {area.f2_dir}")
        return
    store = FeatureStore.load(area.f2_dir)
    if args.step == "risk-cutoffs-draft":
        from forecasting import risk_factors

        cutoffs, evidence, base_rate = risk_factors.draft_cutoffs(store, rules, int(cfg["purge_days"]))
        area.reports_dir.mkdir(parents=True, exist_ok=True)
        md = area.reports_dir / "risk-factor-cutoffs-draft.md"
        risk_factors.write_cutoffs_draft(cutoffs, evidence, base_rate, risk_factors.CUTOFFS_FILE, md)
        print(f"Draft cut-offs written: {risk_factors.CUTOFFS_FILE} and {md}")
        return
    if args.step == "f2-train":
        from forecasting.f2_train import train_and_validate

        result = train_and_validate(store, rules, cfg, area.models_dir, fresh=args.restart, version=f"forecast-{area.key}-0.1")
        path = f2_report.write(result, area.reports_dir, "f2-validation-report", f2_report.validation_markdown(result))
        print(f"Validation report written: {path}")
        return
    if not args.owner_go_ahead:
        raise SystemExit("The locked test runs once, only after the owner has read the validation report. Add --owner-go-ahead.")
    from forecasting.f2_test import run_locked_test

    with settings.connect(url, area.schema) as conn:
        result = run_locked_test(store, rules, cfg, area.models_dir, area.reports_dir, args.main_model, conn)
    path = f2_report.write(result, area.reports_dir, "f2-test-report", f2_report.test_markdown(result))
    print(f"Locked test finished: {result['verdict']['outcome']}. Report: {path}")


if __name__ == "__main__":
    main()
