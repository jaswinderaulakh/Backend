"""Building detail and per-building health history."""
from sqlalchemy.orm import Session

from app.campus.health import calculate_health_index, health_colour, health_index_trend
from app.core.api_schemas import BuildingOut
from app.core.errors import NotFoundError
from app.core.inspection_service import row_to_result
from app.db import repository
from app.db.models import User


def get_building_detail(db: Session, building_id: int, user: User) -> dict:
    building = repository.get_building(db, building_id)
    if building is None:
        raise NotFoundError("Building not found.")
    rows = repository.list_inspections_for_building(db, building_id)
    if user.role != "admin":
        rows = [row for row in rows if row.user_id == user.id]
    results = [row_to_result(row) for row in rows]
    index = calculate_health_index(rows)
    return {
        "building": BuildingOut(id=building.id, name=building.name, latitude=building.latitude,
                                 longitude=building.longitude, created_at=building.created_at).model_dump(mode="json"),
        "health_index": index,
        "colour": health_colour(index),
        "inspection_count": len(rows),
        "inspection_history": [result.model_dump(mode="json") for result in results],
        "health_index_trend": health_index_trend(rows),
    }
