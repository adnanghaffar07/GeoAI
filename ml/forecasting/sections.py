"""F1 step 2: turn the OpenStreetMap road download into road sections of about 100 m (F0 section 3).

1. Split every road at intersections (a node shared by two or more of the included roads, or used twice by one road).
2. Cut each piece between intersections into 100 m sections. A leftover shorter than 30 m is joined to the
   section before it (so sections are 30-129 m); a whole piece shorter than 30 m is not a section and is counted.

Lengths are measured in meters in the area's UTM zone (Chicago: zone 16N, EPSG:26916); sections are stored in EPSG:4326.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import LineString
from shapely.ops import substring

CHICAGO_CRS = "EPSG:26916"  # the default, so Chicago keeps exactly the same sections


@lru_cache(maxsize=8)
def transformers(crs: str = CHICAGO_CRS) -> tuple[Transformer, Transformer]:
    """(to meters, back to degrees) for a projected map zone."""
    return Transformer.from_crs("EPSG:4326", crs, always_xy=True), Transformer.from_crs(crs, "EPSG:4326", always_xy=True)


TO_METERS, TO_DEGREES = transformers(CHICAGO_CRS)


@dataclass(frozen=True)
class Way:
    id: int
    node_ids: tuple[int, ...]
    tags: dict[str, str]


@dataclass(frozen=True)
class Section:
    section_id: str
    osm_way_id: int
    highway: str
    name: str | None
    lanes: str | None
    surface: str | None
    length_m: float
    coords: tuple[tuple[float, float], ...]  # (lon, lat)

    def ewkt(self) -> str:
        return "SRID=4326;LINESTRING(" + ",".join(f"{lon:.7f} {lat:.7f}" for lon, lat in self.coords) + ")"


@dataclass
class SectionStats:
    ways: int = 0
    ways_missing_nodes: int = 0
    pieces_between_intersections: int = 0
    pieces_too_short: int = 0
    too_short_length_m: float = 0.0
    sections: int = 0
    by_highway: Counter = field(default_factory=Counter)


def parse_overpass(data: dict[str, Any]) -> tuple[list[Way], dict[int, tuple[float, float]]]:
    ways: list[Way] = []
    nodes: dict[int, tuple[float, float]] = {}
    for element in data.get("elements", []):
        if element["type"] == "node":
            nodes[element["id"]] = (element["lon"], element["lat"])
        elif element["type"] == "way":
            ways.append(Way(element["id"], tuple(element.get("nodes", ())), element.get("tags", {})))
    return ways, nodes


def junction_nodes(ways: Iterable[Way]) -> set[int]:
    """Nodes where roads meet: used by two or more roads, or twice by the same road (a loop)."""
    uses: Counter = Counter()
    for way in ways:
        uses.update(way.node_ids)
    return {node for node, count in uses.items() if count >= 2}


def split_at_junctions(node_ids: tuple[int, ...], junctions: set[int]) -> list[tuple[int, ...]]:
    pieces: list[tuple[int, ...]] = []
    start = 0
    for index in range(1, len(node_ids) - 1):
        if node_ids[index] in junctions:
            pieces.append(node_ids[start : index + 1])
            start = index
    pieces.append(node_ids[start:])
    return [piece for piece in pieces if len(piece) >= 2]


def cut_points(length_m: float, target_m: float = 100.0, min_piece_m: float = 30.0) -> list[tuple[float, float]]:
    """Start and end distances of the sections along one piece of road. Empty when the piece is shorter than min_piece_m."""
    if length_m < min_piece_m:
        return []
    full = int(length_m // target_m)
    if full == 0:
        return [(0.0, length_m)]
    leftover = length_m - full * target_m
    cuts = [(i * target_m, (i + 1) * target_m) for i in range(full)]
    if leftover >= min_piece_m:
        cuts.append((full * target_m, length_m))
    elif leftover > 0:
        cuts[-1] = (cuts[-1][0], length_m)  # join the short leftover to the last section
    return cuts


def build_sections(
    ways: list[Way],
    nodes: dict[int, tuple[float, float]],
    target_m: float = 100.0,
    min_piece_m: float = 30.0,
    crs: str = CHICAGO_CRS,
):
    to_meters, to_degrees = transformers(crs)
    stats = SectionStats(ways=len(ways))
    junctions = junction_nodes(ways)
    sections: list[Section] = []
    for way in ways:
        if any(node not in nodes for node in way.node_ids) or len(way.node_ids) < 2:
            stats.ways_missing_nodes += 1
            continue
        for piece_index, piece in enumerate(split_at_junctions(way.node_ids, junctions)):
            stats.pieces_between_intersections += 1
            xs, ys = to_meters.transform([nodes[n][0] for n in piece], [nodes[n][1] for n in piece])
            line = LineString(zip(xs, ys, strict=True))
            cuts = cut_points(line.length, target_m, min_piece_m)
            if not cuts:
                stats.pieces_too_short += 1
                stats.too_short_length_m += line.length
                continue
            for cut_index, (start, end) in enumerate(cuts):
                part = substring(line, start, end)
                lons, lats = to_degrees.transform(*part.xy)
                highway = way.tags.get("highway", "")
                sections.append(
                    Section(
                        section_id=f"{way.id}-{piece_index}-{cut_index}",
                        osm_way_id=way.id,
                        highway=highway,
                        name=way.tags.get("name"),
                        lanes=way.tags.get("lanes"),
                        surface=way.tags.get("surface"),
                        length_m=round(end - start, 2),
                        coords=tuple(zip(lons, lats, strict=True)),
                    )
                )
                stats.by_highway[highway] += 1
    stats.sections = len(sections)
    return sections, stats


def sample_points(section: Section, crs: str = CHICAGO_CRS) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    """Start, middle (half the length, measured in meters) and end of a section, rounded to 6 decimals (~0.1 m).

    Used for elevation; the download and the load call this same function, so their points always match.
    """
    to_meters, to_degrees = transformers(crs)
    xs, ys = to_meters.transform([c[0] for c in section.coords], [c[1] for c in section.coords])
    line = LineString(zip(xs, ys, strict=True))
    middle = line.interpolate(line.length / 2)
    mid_lon, mid_lat = to_degrees.transform(middle.x, middle.y)
    start, end = section.coords[0], section.coords[-1]
    return (
        (round(start[0], 6), round(start[1], 6)),
        (round(mid_lon, 6), round(mid_lat, 6)),
        (round(end[0], 6), round(end[1], 6)),
    )


def sections_from_file(path: Path, target_m: float = 100.0, min_piece_m: float = 30.0, crs: str = CHICAGO_CRS):
    data = json.loads(path.read_text(encoding="utf-8"))
    ways, nodes = parse_overpass(data)
    sections, stats = build_sections(ways, nodes, target_m, min_piece_m, crs)
    extract_date = (data.get("osm3s") or {}).get("timestamp_osm_base")
    return sections, stats, extract_date
