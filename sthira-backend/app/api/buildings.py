from typing import List

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core import building_service, inspection_service
from app.core.api_schemas import BuildingCreate, BuildingOut
from app.core.schemas import InspectionResult

router = APIRouter(prefix="/buildings", tags=["Buildings"])


@router.post("", response_model=BuildingOut, status_code=201)
def create_building(data: BuildingCreate, db: DbSession, user: CurrentUser):
    return building_service.create_building(db, data)


@router.get("", response_model=List[BuildingOut])
def list_buildings(db: DbSession, user: CurrentUser):
    return building_service.list_buildings(db)


@router.get("/{building_id}/inspections", response_model=List[InspectionResult])
def building_history(building_id: int, db: DbSession, user: CurrentUser):
    """All inspections of one building, newest first."""
    return inspection_service.list_for_building(db, building_id)
