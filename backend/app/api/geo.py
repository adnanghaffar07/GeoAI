"""Map helpers: turn a searched place (road, address, area) into a survey area.

`POST /api/v1/geo/area-from-place`: any signed-in person. It only calculates a shape;
nothing is saved until the project is saved (which checks permissions as usual).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.core.database import get_db
from app.schemas.geo import AreaFromPlaceRequest, AreaFromPlaceResponse
from app.services.geo import area_from_place

router = APIRouter(prefix="/geo", tags=["map"])


@router.post("/area-from-place")
def make_area(
    body: AreaFromPlaceRequest,
    _current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AreaFromPlaceResponse:
    area, square_meters = area_from_place(db, body)
    return AreaFromPlaceResponse(area=area, area_square_meters=round(square_meters, 1))
