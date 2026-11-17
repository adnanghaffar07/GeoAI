"""Map helpers: turn a searched place (road, address, area) into a survey area.

`POST /api/v1/geo/area-from-place`: any signed-in person. It only calculates a shape;
nothing is saved until the project is saved (which checks permissions as usual).
`POST /api/v1/geo/whole-road`: every piece of a named road in a chosen place (near a point, the
map view or the town limits), from OpenStreetMap or our own road database.
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.core.database import get_db
from app.schemas.geo import (
    AreaFromPlaceRequest,
    AreaFromPlaceResponse,
    WholeRoadRequest,
)
from app.services.geo import area_from_place
from app.services.whole_road import whole_road

router = APIRouter(prefix="/geo", tags=["map"])


@router.post("/area-from-place")
def make_area(
    body: AreaFromPlaceRequest,
    _current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AreaFromPlaceResponse:
    area, square_meters = area_from_place(db, body)
    return AreaFromPlaceResponse(area=area, area_square_meters=round(square_meters, 1))


@router.post("/whole-road")
def find_whole_road(
    body: WholeRoadRequest,
    _current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """The parts of the road with this name in a chosen place (near a point, the map view or the
    town limits), as one line. The answer says which source it came from (OpenStreetMap's
    Overpass servers, or our own road database)."""
    return whole_road(db, body)
