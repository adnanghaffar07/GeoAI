"""Turn a searched place into a survey area with PostGIS.

- A road (line) becomes a strip of the chosen width along the road.
- An address (point) becomes a circle 150 m around it, so the nearby block is covered.
- An area (city, neighbourhood) keeps its outline.
Optionally the result is joined (union) with the current area, so several roads can be
selected one after another and overlapping strips merge into one valid shape.
"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailedError
from app.schemas.geo import AreaFromPlaceRequest
from app.schemas.projects import MAX_BOUNDARY_POINTS

POINT_RADIUS_M = 150

_MAKE_SHAPE = text(
    """
    WITH input AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:shape), 4326) AS g)
    SELECT CASE
        WHEN GeometryType(g) = 'POINT'
            THEN ST_Buffer(g::geography, :point_radius)::geometry
        WHEN GeometryType(g) IN ('LINESTRING', 'MULTILINESTRING')
            THEN ST_Buffer(g::geography, :half_width, 'endcap=round join=round')::geometry
        ELSE ST_MakeValid(g)
    END AS shape
    FROM input
    """
)

_FINISH = text(
    """
    WITH joined AS (
        SELECT ST_CollectionExtract(ST_MakeValid(
            CASE WHEN CAST(:add_to AS text) IS NULL THEN CAST(:made AS geometry)
                 ELSE ST_Union(
                    ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(CAST(:add_to AS text)), 4326)),
                    CAST(:made AS geometry))
            END), 3) AS g
    ),
    small AS (
        SELECT CASE WHEN ST_NPoints(g) > :max_points
                    THEN ST_CollectionExtract(
                        ST_MakeValid(ST_SimplifyPreserveTopology(g, 0.00002)), 3)
                    ELSE g END AS g
        FROM joined
    )
    SELECT ST_AsGeoJSON(g, 7), ST_Area(g::geography), ST_NPoints(g), ST_IsEmpty(g) FROM small
    """
)


def area_from_place(db: Session, body: AreaFromPlaceRequest) -> tuple[dict[str, Any], float]:
    """Return (GeoJSON Polygon or MultiPolygon, size in square meters)."""
    made = db.scalar(
        _MAKE_SHAPE,
        {
            "shape": body.shape.model_dump_json(),
            "point_radius": POINT_RADIUS_M,
            "half_width": body.road_width_m / 2,
        },
    )
    add_to = body.add_to.model_dump_json() if body.add_to else None
    geojson, square_meters, points, empty = db.execute(
        _FINISH, {"made": made, "add_to": add_to, "max_points": MAX_BOUNDARY_POINTS - 500}
    ).one()
    if empty or not geojson or not square_meters:
        raise ValidationFailedError("This place has no area that can be used. Try another result.")
    if points > MAX_BOUNDARY_POINTS:
        raise ValidationFailedError(
            "This place is too detailed to use as a survey area. Draw the area by hand instead."
        )
    return json.loads(geojson), float(square_meters)
