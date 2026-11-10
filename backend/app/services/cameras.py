# ruff: noqa: E501
"""Traffic cameras (team lead plan, items 8 and 10): IDOT's Illinois Gateway cameras inside the project area.

View mode: the browser loads each camera's latest image straight from IDOT (no storage here).
"Take snapshot": the server downloads that one image and saves it as an ordinary project photo (AI check, review,
findings, photo map). Only the camera's id comes from the browser; the image address is always read again from
IDOT's own list and must be on IDOT's camera server (so no other address can be fetched).

Source: Illinois Department of Transportation, "Illinois Gateway Traffic Cameras" (ArcGIS, owner IDOTAdmin).
Licence: Creative Commons Attribution-ShareAlike 2.0 (credit IDOT; snapshots keep the same licence).
"""

import io
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import ProjectContext
from app.core.errors import NotFoundError, PayloadTooLargeError, ServiceUnavailableError
from app.models import Project
from app.schemas.images import LatLon
from app.services import images
from app.services.audit import record_event

log = logging.getLogger(__name__)

LAYER = "https://services2.arcgis.com/aIrBD8yn1TDTEXoz/arcgis/rest/services/TrafficCamerasTM_Public/FeatureServer/0"
IMAGE_HOSTS = {"cctv.travelmidwest.com"}
SOURCE = "Illinois Department of Transportation (Gateway Traveler Information)"
LICENCE = "CC BY-SA 2.0"
LICENCE_URL = "https://creativecommons.org/licenses/by-sa/2.0/"
FIELDS = "OBJECTID,CameraLocation,CameraDirection,y,x,SnapShot,ImgPath,AgeInMinutes,TooOld"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
CACHE_SECONDS = 300
MAX_CAMERAS = 500
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = "GeoInfraLens AI (road condition app)"
    return session


def _get_json(params: dict[str, Any]) -> dict[str, Any]:
    try:
        answer = _session().get(f"{LAYER}/query", params=params, timeout=30)
        answer.raise_for_status()
        data = answer.json()
    except (requests.RequestException, ValueError) as error:
        log.warning("IDOT camera list failed: %s", error)
        raise ServiceUnavailableError(
            "The IDOT camera service could not be reached. Try again in a few minutes."
        ) from error
    if "error" in data:
        raise ServiceUnavailableError(
            "The IDOT camera service answered with a problem. Try again in a few minutes."
        )
    return data


def _get_image(url: str) -> bytes:
    try:
        with _session().get(url, timeout=30, stream=True) as answer:
            answer.raise_for_status()
            if not answer.headers.get("Content-Type", "").startswith("image/"):
                raise ServiceUnavailableError(
                    "The camera did not send a picture. Try again in a few minutes."
                )
            body = io.BytesIO()
            for chunk in answer.iter_content(64 * 1024):
                body.write(chunk)
                if body.tell() > MAX_IMAGE_BYTES:
                    raise PayloadTooLargeError("The camera picture is too large.")
            return body.getvalue()
    except requests.RequestException as error:
        log.warning("IDOT camera image failed: %s", error)
        raise ServiceUnavailableError(
            "The camera picture could not be downloaded. Try again in a few minutes."
        ) from error


def _camera(attributes: dict[str, Any]) -> dict[str, Any] | None:
    url = str(attributes.get("SnapShot") or "")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in IMAGE_HOSTS:
        return None  # only pictures from IDOT's own camera server
    try:
        age = int(attributes.get("AgeInMinutes"))
    except (TypeError, ValueError):
        age = None
    return {
        "id": int(attributes["OBJECTID"]),
        "location": str(attributes.get("CameraLocation") or "Camera")[:120],
        "direction": str(attributes.get("CameraDirection") or "NONE")[:4],
        "latitude": float(attributes["y"]),
        "longitude": float(attributes["x"]),
        "image_url": url,
        "page_url": attributes.get("ImgPath"),
        "age_minutes": age,
        "too_old": str(attributes.get("TooOld")).lower() == "true",
    }


def _project_box(db: Session, project_id: Any) -> tuple[float, float, float, float]:
    row = db.execute(
        select(
            func.ST_XMin(func.ST_Envelope(Project.boundary)),
            func.ST_YMin(func.ST_Envelope(Project.boundary)),
            func.ST_XMax(func.ST_Envelope(Project.boundary)),
            func.ST_YMax(func.ST_Envelope(Project.boundary)),
        ).where(Project.id == project_id)
    ).one()
    return float(row[0]), float(row[1]), float(row[2]), float(row[3])


def list_cameras(db: Session, ctx: ProjectContext) -> dict[str, Any]:
    """Cameras inside the project area (cached for 5 minutes per project area)."""
    box = _project_box(db, ctx.project.id)
    key = ",".join(f"{v:.4f}" for v in box)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        cameras = cached[1]
    else:
        data = _get_json(
            {
                "where": "1=1",
                "geometry": key,
                "geometryType": "esriGeometryEnvelope",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": FIELDS,
                "returnGeometry": "false",
                "resultRecordCount": MAX_CAMERAS,
                "f": "json",
            }
        )
        cameras = [
            c for c in (_camera(f.get("attributes") or {}) for f in data.get("features", [])) if c
        ]
        _cache[key] = (time.monotonic(), cameras)
    inside = [
        c
        for c in cameras
        if images._inside_project(db, ctx.project.id, c["latitude"], c["longitude"])
    ]
    inside.sort(key=lambda c: (c["location"], c["direction"]))
    return {"cameras": inside, "source": SOURCE, "licence": LICENCE, "licence_url": LICENCE_URL}


def take_snapshot(db: Session, ctx: ProjectContext, camera_id: int) -> images.UploadOutcome:
    """Save the camera's current picture as a project photo, located at the camera."""
    data = _get_json(
        {
            "where": f"OBJECTID={int(camera_id)}",
            "outFields": FIELDS,
            "returnGeometry": "false",
            "f": "json",
        }
    )
    found = [c for c in (_camera(f.get("attributes") or {}) for f in data.get("features", [])) if c]
    if not found or not images._inside_project(
        db, ctx.project.id, found[0]["latitude"], found[0]["longitude"]
    ):
        raise NotFoundError("Camera not found in this project's area.")
    camera = found[0]
    picture = _get_image(camera["image_url"])
    now = datetime.now(UTC)
    taken = now - timedelta(minutes=camera["age_minutes"] or 0)
    safe = "".join(ch if ch.isalnum() else "-" for ch in camera["location"]).strip("-")
    filename = f"IDOT-camera-{safe}-{camera['direction']}-{taken:%Y%m%d-%H%M}.jpg"
    outcome = images.upload_image(
        db,
        ctx,
        upload=io.BytesIO(picture),
        filename=filename,
        device_location=LatLon(latitude=camera["latitude"], longitude=camera["longitude"]),
    )
    if not outcome.duplicate:
        image = outcome.image
        if image.captured_at is None:
            image.captured_at = taken
        record_event(
            db,
            action="image.camera_snapshot",
            organization_id=ctx.project.organization_id,
            project_id=ctx.project.id,
            actor_user_id=ctx.user.id,
            actor_roles=ctx.actor_roles,
            target_type="image",
            target_id=image.id,
            details={
                "camera_id": camera["id"],
                "camera": f"{camera['location']} ({camera['direction']})",
                "source": SOURCE,
                "licence": LICENCE,
                "image_url": camera["image_url"],
                "taken_at": taken.isoformat(),
            },
        )
        db.commit()
        db.refresh(image)
    return outcome
