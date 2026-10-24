"""Create and list buildings."""
from typing import List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.api_schemas import BuildingCreate
from app.core.errors import ConflictError
from app.db import repository
from app.db.models import Building


def create_building(db: Session, data: BuildingCreate) -> Building:
    if repository.get_building_by_name(db, data.name):
        raise ConflictError("A building with that name already exists.")
    try:
        return repository.create_building(db, data.name, data.latitude, data.longitude)
    except IntegrityError:
        db.rollback()
        raise ConflictError("A building with that name already exists.")


def list_buildings(db: Session) -> List[Building]:
    return repository.list_buildings(db)
