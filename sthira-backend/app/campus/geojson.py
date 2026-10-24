"""Campus map as GeoJSON. Stage 1 version: health index = average score of a building's inspections."""
from sqlalchemy.orm import Session

from app.db import repository


def get_campus_map(db: Session) -> dict:
    scores = repository.health_scores_by_building(db)
    features = []
    for building in repository.list_buildings(db):
        values = scores.get(building.id, [])
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [building.longitude, building.latitude]},  # GeoJSON order: longitude first
            "properties": {
                "building_id": building.id,
                "name": building.name,
                "health_index": round(sum(values) / len(values), 1) if values else None,  # 0-100, None = no inspections yet
                "inspection_count": len(values),
            },
        })
    return {"type": "FeatureCollection", "features": features}
