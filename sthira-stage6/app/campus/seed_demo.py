"""Seed six fictional Pune-area buildings and sample inspection histories.

Run with ``python -m app.campus.seed_demo``. The entries are demonstrations,
not real campus data; running the command again does not duplicate them.
"""
from datetime import timedelta

from app.core.clock import utcnow
from app.core.config import load_thresholds
from app.core.schemas import AudioResult, CrackResult, InspectionResult, Verdict
from app.db.models import Inspection
from app.db.repository import create_building, get_building_by_name
from app.db.session import get_sessionmaker, init_db

_BUILDINGS = [
    ("Demo — Shivajinagar Block", 18.5308, 73.8475),
    ("Demo — Deccan Hall", 18.5167, 73.8410),
    ("Demo — Kothrud Centre", 18.5074, 73.8077),
    ("Demo — Aundh Annex", 18.5590, 73.8077),
    ("Demo — Hadapsar Workshop", 18.5089, 73.9260),
    ("Demo — Viman Nagar Lab", 18.5679, 73.9143),
]
_SCENARIOS = [
    (5, 0.6, "Shear risk: inspect first"),
    (4, 0.45, "Void risk: inspect"),
    (3, 0.22, "Minor: seal and monitor"),
    (2, 0.38, "Plaster spalling: cosmetic"),
    (1, 0.05, "Hairline shrinkage: no action"),
    (4, 0.5, "Void risk: inspect"),
]


def main() -> None:
    init_db()
    thresholds = load_thresholds()
    now = utcnow()
    added = 0
    with get_sessionmaker()() as db:
        for building_index, (name, latitude, longitude) in enumerate(_BUILDINGS):
            building = get_building_by_name(db, name)
            if building is None:
                building = create_building(db, name, latitude, longitude)
            # This marker makes reruns safe even if a building already existed.
            marker = f"Demo sample location {building_index + 1}"
            existing = db.query(Inspection).filter(
                Inspection.building_id == building.id,
                Inspection.location == marker,
            ).first()
            if existing:
                continue
            for entry_number, scenario_index in enumerate(((building_index + 1) % len(_SCENARIOS), building_index), start=1):
                severity, width, label = _SCENARIOS[scenario_index]
                created = now - timedelta(days=35 - building_index * 3 - entry_number)
                crack = CrackResult(max_width_mm=width, mean_width_mm=width * 0.6,
                                    length_mm=500 + building_index * 125, angle_deg=12 if severity != 5 else 45)
                audio = AudioResult(dominant_hz=700 if severity == 4 else 1700,
                                    classification="void" if severity == 4 else "solid")
                verdict = Verdict(label=label, severity=severity,
                                  reason=f"Demo-only sample: measured crack width {width:g} mm at fictional building {name}.")
                exposure = ("mild", "moderate", "severe")[entry_number - 1]
                result = InspectionResult(
                    inspection_id=0, building_id=building.id, building_name=building.name,
                    floor=str(entry_number), location=marker if entry_number == 1 else f"East wall {building_index + 1}",
                    exposure_class=exposure, created_at=created, completed_at=created, status="completed",
                    crack=crack, audio=audio, verdict=verdict,
                    exceeds_is456_limit=width > thresholds["is456_crack_limit_mm"][exposure],
                    health_score=float(thresholds["health_score"]["severity_to_score"][severity]),
                )
                row = Inspection(building_id=building.id, user_id=None, floor=result.floor,
                                 location=result.location, exposure_class=exposure, status="completed",
                                 health_score=result.health_score, created_at=created, completed_at=created)
                db.add(row)
                db.flush()
                row.result_json = result.model_copy(update={"inspection_id": row.id}).model_dump_json()
                added += 1
            db.commit()
    print(f"Demo seed complete: six fictional Pune buildings; added {added} sample inspections.")


if __name__ == "__main__":
    main()
