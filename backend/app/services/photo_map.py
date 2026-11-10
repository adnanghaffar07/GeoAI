# ruff: noqa: E501
"""Analysed photos on the map (team lead plan, Phase 1, item 5).

One point per photo with a location that the AI has checked, with the defects the person may see (the same review
statuses as the findings list) and their boxes, so the screen can draw them on the photo.
"""

from collections import defaultdict
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.core.auth import ProjectContext
from app.models import AnalysisJob, Finding, FindingImage, Image
from app.services.findings import visible_statuses

MAP_LIMIT = 2000
WORST = {"verified": 3, "ai_generated": 2, "awaiting_review": 2, "needs_field_check": 2}


def photos_geojson(db: Session, ctx: ProjectContext) -> dict[str, Any]:
    checked = exists().where(AnalysisJob.image_id == Image.id, AnalysisJob.status == "completed")
    rows = db.execute(
        select(
            Image.id,
            Image.original_filename,
            Image.width_px,
            Image.height_px,
            Image.captured_at,
            Image.created_at,
            func.ST_X(Image.original_location),
            func.ST_Y(Image.original_location),
        )
        .where(
            Image.project_id == ctx.project.id,
            Image.withdrawn_at.is_(None),
            Image.original_location.is_not(None),
            checked,
        )
        .order_by(Image.created_at.desc())
        .limit(MAP_LIMIT)
    ).all()
    ids = [row[0] for row in rows]
    statuses = visible_statuses(ctx, include_rejected=False)
    defects: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    if ids and statuses:
        for image_id, finding in db.execute(
            select(FindingImage.image_id, Finding)
            .join(Finding, Finding.id == FindingImage.finding_id)
            .where(FindingImage.image_id.in_(ids), Finding.review_status.in_(statuses))
        ).all():
            defects[image_id].append(
                {
                    "id": str(finding.id),
                    "type_key": finding.type_key or finding.predicted_type_key,
                    "severity_key": finding.severity_key,
                    "review_status": finding.review_status,
                    "bbox": finding.predicted_bbox,
                }
            )
    features = []
    for image_id, name, width, height, captured, created, lon, lat in rows:
        found = defects.get(image_id, [])
        worst = max((WORST.get(d["review_status"], 1) for d in found), default=0)
        features.append(
            {
                "type": "Feature",
                "id": str(image_id),
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "id": str(image_id),
                    "original_filename": name,
                    "width_px": width,
                    "height_px": height,
                    "taken_at": (captured or created).isoformat(),
                    "defect_count": len(found),
                    # 3 = a verified defect, 2 = an AI suggestion waiting for review, 0 = nothing found
                    "worst": worst,
                    "defects": found,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features, "truncated": len(rows) >= MAP_LIMIT}
