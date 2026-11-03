"""Forecasting F1: road sections of about 100 m, split at intersections (F0 section 3)."""

from __future__ import annotations

import pytest

from forecasting.sections import TO_DEGREES, Way, build_sections, cut_points, parse_overpass, split_at_junctions


@pytest.mark.parametrize(
    ("length", "expected"),
    [
        (25.0, []),  # whole piece shorter than 30 m: not a section
        (80.0, [(0.0, 80.0)]),
        (100.0, [(0.0, 100.0)]),
        (250.0, [(0.0, 100.0), (100.0, 200.0), (200.0, 250.0)]),  # 50 m end piece kept (>= 30 m)
        (215.0, [(0.0, 100.0), (100.0, 215.0)]),  # 15 m leftover joined to the last section
    ],
)
def test_cut_points(length, expected):
    assert cut_points(length) == expected


def test_split_at_junctions_only_at_inner_shared_nodes():
    assert split_at_junctions((1, 2, 3, 4, 5), {3, 1}) == [(1, 2, 3), (3, 4, 5)]
    assert split_at_junctions((1, 2, 3), set()) == [(1, 2, 3)]


def meters_to_lonlat(x: float, y: float) -> tuple[float, float]:
    return TO_DEGREES.transform(440000 + x, 4630000 + y)  # a point in Chicago, UTM 16N


def test_build_sections_splits_at_the_crossing_and_cuts_100m_pieces():
    nodes = {
        1: meters_to_lonlat(0, 0),
        2: meters_to_lonlat(180, 0),  # crossing with road 20
        3: meters_to_lonlat(400, 0),
        4: meters_to_lonlat(180, -20),
        5: meters_to_lonlat(180, 60),
    }
    ways = [
        Way(10, (1, 2, 3), {"highway": "residential", "name": "W Test St"}),
        Way(20, (4, 2, 5), {"highway": "tertiary"}),
        Way(30, (1, 99), {"highway": "residential"}),  # node 99 missing from the download
    ]
    sections, stats = build_sections(ways, nodes)

    by_id = {s.section_id: s for s in sections}
    # Road 10: 180 m -> 100 + 80; 220 m -> 100 + 120 (20 m leftover joined). Road 20: 20 m piece dropped, 60 m kept.
    assert sorted(by_id) == ["10-0-0", "10-0-1", "10-1-0", "10-1-1", "20-1-0"]
    assert [round(by_id[i].length_m) for i in ("10-0-0", "10-0-1", "10-1-0", "10-1-1", "20-1-0")] == [100, 80, 100, 120, 60]
    assert by_id["10-0-0"].name == "W Test St"
    assert by_id["20-1-0"].highway == "tertiary"
    assert stats.ways_missing_nodes == 1
    assert stats.pieces_too_short == 1
    assert round(stats.too_short_length_m) == 20
    assert stats.by_highway == {"residential": 4, "tertiary": 1}
    assert by_id["10-0-0"].ewkt().startswith("SRID=4326;LINESTRING(-87.")


def test_parse_overpass():
    ways, nodes = parse_overpass(
        {
            "elements": [
                {"type": "way", "id": 1, "nodes": [5, 6], "tags": {"highway": "primary"}},
                {"type": "node", "id": 5, "lat": 41.8, "lon": -87.6},
            ]
        }
    )
    assert ways == [Way(1, (5, 6), {"highway": "primary"})]
    assert nodes == {5: (-87.6, 41.8)}
