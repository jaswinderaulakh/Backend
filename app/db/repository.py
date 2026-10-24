"""All database reads and writes live here."""
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Building, Inspection, User


# ---- users
def create_user(db: Session, username: str, password_hash: str, role: str = "inspector") -> User:
    user = User(username=username, password_hash=password_hash, role=role)
    db.add(user)
    db.commit()
    return user


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.scalar(select(User).where(User.username == username))


def get_user(db: Session, user_id: int) -> Optional[User]:
    return db.get(User, user_id)


# ---- buildings
def create_building(db: Session, name: str, latitude: Optional[float], longitude: Optional[float]) -> Building:
    building = Building(name=name, latitude=latitude, longitude=longitude)
    db.add(building)
    db.commit()
    return building


def list_buildings(db: Session) -> List[Building]:
    return list(db.scalars(select(Building).order_by(Building.id)))


def get_building(db: Session, building_id: int) -> Optional[Building]:
    return db.get(Building, building_id)


def get_building_by_name(db: Session, name: str) -> Optional[Building]:
    return db.scalar(select(Building).where(Building.name == name))


# ---- inspections
def create_inspection_row(db: Session, building_id: int, user_id: int, floor: str,
                          location: str, exposure_class: str) -> Inspection:
    row = Inspection(building_id=building_id, user_id=user_id, floor=floor, location=location,
                     exposure_class=exposure_class, status="processing")
    db.add(row)
    db.commit()
    return row


def get_inspection(db: Session, inspection_id: int) -> Optional[Inspection]:
    return db.get(Inspection, inspection_id)


def list_inspections_for_building(db: Session, building_id: int) -> List[Inspection]:
    query = (select(Inspection).where(Inspection.building_id == building_id)
             .order_by(Inspection.created_at.desc(), Inspection.id.desc()))
    return list(db.scalars(query))


def health_scores_by_building(db: Session) -> Dict[int, List[float]]:
    """Health scores of all finished inspections, grouped by building id."""
    query = select(Inspection.building_id, Inspection.health_score).where(
        Inspection.status == "completed", Inspection.health_score.is_not(None))
    scores: Dict[int, List[float]] = {}
    for building_id, score in db.execute(query):
        scores.setdefault(building_id, []).append(score)
    return scores
