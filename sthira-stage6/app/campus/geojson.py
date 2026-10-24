"""Campus map as GeoJSON with current building-health summaries."""
from __future__ import annotations

import json
from datetime import datetime
from sqlalchemy.orm import Session

from app.campus.health import calculate_health_index, health_colour, latest_per_location
from app.db import repository


def _verdict(item):
    raw = getattr(item, "result_json", None)
    if raw:
        try:
            return (json.loads(raw).get("verdict") or {})
        except (ValueError, TypeError):
            return {}
    result = getattr(item, "verdict", None)
    if result is None:
        return {}
    if isinstance(result, dict):
        return result
    return {"label": getattr(result, "label", None), "severity": getattr(result, "severity", None)}


def _date(item):
    return getattr(item, "created_at", None) or getattr(item, "completed_at", None)


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else (str(value) if value else None)


def get_campus_map(db: Session) -> dict:
    features = []
    missing = []
    for building in repository.list_buildings(db):
        if building.latitude is None or building.longitude is None:
            missing.append({"building_id": building.id, "name": building.name})
            continue
        inspections = repository.list_inspections_for_building(db, building.id)
        current = latest_per_location(inspections)
        verdicts = [_verdict(item) for item in current]
        verdicts = [verdict for verdict in verdicts if verdict.get("severity") is not None]
        worst = max(verdicts, key=lambda verdict: int(verdict["severity"])) if verdicts else None
        index = calculate_health_index(inspections)
        dates = [_date(item) for item in inspections if _date(item) is not None]
        last_date = max(dates) if dates else None
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [building.longitude, building.latitude]},
            "properties": {
                "building_id": building.id,
                "name": building.name,
                "health_index": index,
                "colour": health_colour(index),
                "inspection_count": len(inspections),
                "worst_verdict": worst.get("label") if worst else None,
                "last_inspection_date": _iso(last_date),
            },
        })
    return {"type": "FeatureCollection", "features": features, "missing_location": missing}
