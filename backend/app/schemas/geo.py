"""Shapes for turning a searched place into a survey area."""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.projects import MAX_BOUNDARY_POINTS, GeoJsonArea

MAX_PLACE_POINTS = 20_000


def _count_points(value: Any) -> int:
    is_point = isinstance(value, list) and len(value) >= 2
    if is_point and all(isinstance(v, int | float) for v in value[:2]):
        lon, lat = value[0], value[1]
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("Points must be longitude -180..180, latitude -90..90.")
        return 1
    if isinstance(value, list) and value:
        return sum(_count_points(item) for item in value)
    raise ValueError("Points must be [longitude, latitude] numbers.")


class PlaceShape(BaseModel):
    """The shape of a searched place: a point (address), a line (road) or an area."""

    type: Literal["Point", "LineString", "MultiLineString", "Polygon", "MultiPolygon"]
    coordinates: list[Any]

    @model_validator(mode="after")
    def check_points(self) -> "PlaceShape":
        if _count_points(self.coordinates) > MAX_PLACE_POINTS:
            raise ValueError(f"The place has too many points (maximum {MAX_PLACE_POINTS}).")
        return self


class AreaFromPlaceRequest(BaseModel):
    shape: PlaceShape
    # Total width of the strip made along a road, in meters (road plus sidewalks).
    road_width_m: int = Field(default=30, ge=10, le=200)
    # When given, the new shape is joined to this area instead of replacing it.
    add_to: GeoJsonArea | None = None


class WholeRoadRequest(BaseModel):
    """A road name (or route number) and a point on it; pieces within `radius_m` are used."""

    name: str = Field(min_length=1, max_length=200)
    by_ref: bool = False  # True: `name` is a route number such as "IL 59"
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_m: int = Field(default=5000, ge=500, le=10_000)


class AreaFromPlaceResponse(BaseModel):
    area: dict[str, Any]
    area_square_meters: float


__all__ = [
    "MAX_BOUNDARY_POINTS",
    "AreaFromPlaceRequest",
    "AreaFromPlaceResponse",
    "PlaceShape",
    "WholeRoadRequest",
]
