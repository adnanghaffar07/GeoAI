# ruff: noqa: E501
"""Where the organization's files are kept (team lead plan, Phase 2).

GET: every member can see where and how their files are stored. PUT: organization admins only; the connection is
tested before anything is saved. The secret key is never sent back.
"""

from datetime import datetime

from app.core.auth import OrgContext, require_org_permission
from app.core.database import get_db
from app.core.permissions import Perm
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services import data_storage as service

router = APIRouter(prefix="/organizations/{org_id}/data-storage", tags=["organizations"])


class DataStorageOut(BaseModel):
    kind: str
    place: str
    endpoint: str | None
    bucket: str | None
    region: str | None
    prefix: str | None
    access_key_id: str | None
    has_secret: bool
    location_note: str | None
    verified_at: datetime | None
    updated_at: datetime | None
    encryption: str
    can_edit: bool = False


class DataStorageIn(BaseModel):
    kind: str
    endpoint: str | None = None
    bucket: str | None = None
    region: str | None = None
    prefix: str | None = None
    access_key_id: str | None = None
    secret_key: str | None = None  # empty: keep the saved one
    location_note: str | None = None


@router.get("", response_model=DataStorageOut)
def get_data_storage(
    ctx: OrgContext = Depends(require_org_permission(Perm.ORG_VIEW)),
    db: Session = Depends(get_db),
) -> DataStorageOut:
    row = service.get(db, ctx.organization.id)
    return DataStorageOut(**service.out(row), can_edit=Perm.ORG_SETTINGS_EDIT in ctx.permissions)


@router.put("", response_model=DataStorageOut)
def save_data_storage(
    body: DataStorageIn,
    ctx: OrgContext = Depends(require_org_permission(Perm.ORG_SETTINGS_EDIT)),
    db: Session = Depends(get_db),
) -> DataStorageOut:
    row = service.save(db, ctx.organization.id, ctx.user.id, body.model_dump())
    return DataStorageOut(**service.out(row), can_edit=True)
