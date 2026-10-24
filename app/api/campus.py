from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.campus.geojson import get_campus_map

router = APIRouter(prefix="/campus", tags=["Campus map"])


@router.get("/map")
def campus_map(db: DbSession, user: CurrentUser):
    """GeoJSON of all buildings with their health index (0-100)."""
    return get_campus_map(db)
