"""Create inspections (save files, run the pipeline, store the result) and read them back."""
import logging
from pathlib import Path
from typing import BinaryIO, List

from sqlalchemy.orm import Session

from app.core import storage
from app.core.clock import utcnow
from app.core.errors import BadRequestError, NotFoundError, TooLargeError
from app.core.schemas import InspectionResult
from app.core.settings import get_settings
from app.db import repository
from app.db.models import Inspection, User
from app.pipeline import run_pipeline

log = logging.getLogger("sthira")

_PHOTO_TYPES = {  # first bytes of the file -> file ending to save it with
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG": ".png",
}


def _read_limited(stream: BinaryIO, what: str) -> bytes:
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise TooLargeError(f"The {what} is bigger than {get_settings().max_upload_mb} MB.")
    if not data:
        raise BadRequestError(f"The {what} file is empty.")
    return data


def _photo_extension(data: bytes) -> str:
    for magic, extension in _PHOTO_TYPES.items():
        if data.startswith(magic):
            return extension
    raise BadRequestError("The photo must be a JPEG or PNG image.")


def _check_wav(data: bytes) -> None:
    if not (data[:4] == b"RIFF" and data[8:12] == b"WAVE"):
        raise BadRequestError("The tap recording must be a .wav file.")


def row_to_result(row: Inspection) -> InspectionResult:
    """Rebuild the InspectionResult of a saved inspection."""
    if row.result_json:
        return InspectionResult.model_validate_json(row.result_json)
    return InspectionResult(  # an inspection that failed before any analysis was saved
        inspection_id=row.id, building_id=row.building_id, building_name=row.building.name,
        floor=row.floor, location=row.location, exposure_class=row.exposure_class,
        created_by=row.user_id, created_at=row.created_at, completed_at=row.completed_at,
        status=row.status, error_message=row.error_message,
        photo_path=row.photo_path, audio_path=row.audio_path)


def create_inspection(db: Session, user: User, building_id: int, floor: str, location: str,
                      exposure_class: str, photo_stream: BinaryIO, wav_stream: BinaryIO) -> InspectionResult:
    building = repository.get_building(db, building_id)
    if building is None:
        raise NotFoundError("Building not found.")

    photo_bytes = _read_limited(photo_stream, "photo")
    wav_bytes = _read_limited(wav_stream, "tap recording")
    photo_ext = _photo_extension(photo_bytes)
    _check_wav(wav_bytes)

    row = repository.create_inspection_row(db, building.id, user.id, floor.strip(), location.strip(), exposure_class)
    folder = storage.inspection_dir(row.id)
    photo_file: Path = folder / f"photo{photo_ext}"
    wav_file: Path = folder / "tap.wav"
    photo_file.write_bytes(photo_bytes)
    wav_file.write_bytes(wav_bytes)
    row.photo_path = storage.to_relative(photo_file)
    row.audio_path = storage.to_relative(wav_file)

    try:
        result = run_pipeline(photo_file, wav_file, exposure_class).model_copy(update=dict(
            inspection_id=row.id, building_id=building.id, building_name=building.name,
            floor=row.floor, location=row.location, created_by=user.id, created_at=row.created_at))
        row.status = "completed"
        row.completed_at = result.completed_at or utcnow()
        row.health_score = result.health_score
        row.result_json = result.model_dump_json()
    except Exception as exc:  # the analysis must never crash the server
        log.exception("Analysis failed for inspection %s", row.id)
        row.status = "failed"
        row.error_message = f"The analysis failed: {exc}"
        row.completed_at = utcnow()
    db.commit()
    return row_to_result(row)


def get_inspection(db: Session, inspection_id: int) -> InspectionResult:
    row = repository.get_inspection(db, inspection_id)
    if row is None:
        raise NotFoundError("Inspection not found.")
    return row_to_result(row)


def get_report_file(db: Session, inspection_id: int) -> Path:
    result = get_inspection(db, inspection_id)
    if result.cost is None or not result.cost.pdf_path:
        raise NotFoundError("This inspection has no report.")
    path = storage.resolve(result.cost.pdf_path)
    if not path.is_file():
        raise NotFoundError("The report file is missing.")
    return path


def list_for_building(db: Session, building_id: int) -> List[InspectionResult]:
    if repository.get_building(db, building_id) is None:
        raise NotFoundError("Building not found.")
    return [row_to_result(row) for row in repository.list_inspections_for_building(db, building_id)]
