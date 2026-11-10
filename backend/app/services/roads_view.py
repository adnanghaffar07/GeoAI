# ruff: noqa: E501
"""Roads-only view (team lead plan, item 11): every road section of the project with its name, road details and
the levels the screen can colour by (risk, freeze-thaw weather, traffic, road roughness). Optionally only the
sections inside a chosen box ("w,s,e,n")."""

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import ProjectContext
from app.core.errors import ValidationFailedError
from app.models import ForecastSection
from app.services.road_risk import project_risk

COLOUR_FACTORS = {
    "climate": "freeze_thaw_30d",
    "traffic": "traffic_band",
    "roughness": "road_roughness",
}


def parse_box(box: str | None) -> tuple[float, float, float, float] | None:
    if not box:
        return None
    try:
        w, s, e, n = (float(v) for v in box.split(","))
    except ValueError:
        raise ValidationFailedError(
            "The area must be four numbers: west,south,east,north."
        ) from None
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise ValidationFailedError("The area is not a valid box.")
    return w, s, e, n


def roads_geojson(db: Session, ctx: ProjectContext, box: str | None = None) -> dict[str, Any]:
    bounds = parse_box(box)
    risk = project_risk(db, ctx)
    items = {item.section_id: item for item in risk.items}
    features: list[dict[str, Any]] = []
    if not items:
        return {"type": "FeatureCollection", "features": features, "box": bounds}
    query = select(ForecastSection, func.ST_AsGeoJSON(ForecastSection.line, 6)).where(
        ForecastSection.id.in_(list(items))
    )
    if bounds:
        query = query.where(
            func.ST_Intersects(ForecastSection.line, func.ST_MakeEnvelope(*bounds, 4326))
        )
    for section, geometry in db.execute(query).all():
        item = items[section.id]
        by_factor = {f.factor: f for f in item.factors}
        props: dict[str, Any] = {
            "section_id": str(section.id),
            "name": section.name,
            "road_type": section.road_type,
            "length_m": round(section.length_m, 1),
            "level": item.level,
            "speed_limit_mph": section.speed_limit_mph,
            "lanes": section.lanes,
            "surface": section.surface,
            "oneway": section.oneway,
        }
        for key, factor in COLOUR_FACTORS.items():
            found = by_factor.get(factor)
            props[f"{key}_level"] = found.level if found else "missing"
        features.append({"type": "Feature", "geometry": json.loads(geometry), "properties": props})
    return {"type": "FeatureCollection", "features": features, "box": bounds}
