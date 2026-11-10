"""Traffic cameras (team lead items 8 and 10): view IDOT cameras in the area; save a snapshot."""

from typing import Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.auth import ProjectContext, require_project_permission
from app.core.database import get_db
from app.core.permissions import Perm
from app.schemas.images import UploadResult
from app.services import cameras as service
from app.services import images as image_service

router = APIRouter(prefix="/projects/{project_id}/cameras", tags=["cameras"])


@router.get("")
def list_cameras(
    ctx: ProjectContext = Depends(require_project_permission(Perm.PROJECT_VIEW)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """IDOT cameras inside the project area, with the address of each one's latest picture."""
    return service.list_cameras(db, ctx)


@router.post(
    "/{camera_id}/snapshot", response_model=UploadResult, status_code=status.HTTP_201_CREATED
)
def take_snapshot(
    camera_id: int,
    response: Response,
    ctx: ProjectContext = Depends(require_project_permission(Perm.IMAGE_UPLOAD)),
    db: Session = Depends(get_db),
) -> UploadResult:
    """Save the camera's current picture as a project photo (same as an upload)."""
    outcome = service.take_snapshot(db, ctx, camera_id)
    if outcome.duplicate:
        response.status_code = status.HTTP_200_OK
    return UploadResult(
        duplicate=outcome.duplicate, image=image_service.to_out([outcome.image], db)[0]
    )
