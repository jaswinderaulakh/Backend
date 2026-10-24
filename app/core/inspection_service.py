"""Queue inspections, safely store uploads, and persist background results."""
import logging
import wave
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, List, Optional

from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.core import storage
from app.core.clock import utcnow
from app.core.config import load_upload_limits
from app.core.errors import BadRequestError, NotFoundError, TooLargeError
from app.core.schemas import InspectionResult
from app.core.settings import get_settings
from app.db import repository
from app.db.models import Inspection, User
from app.db.session import get_sessionmaker
from app.pipeline import run_pipeline
from app.audio.analyze import AudioAnalysisError
from app.crack.measure import CrackError
from app.vision.scale import ScaleError

log = logging.getLogger("sthira")

_PHOTO_TYPES = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
}


def _read_limited(stream: BinaryIO, what: str, limit_mb: int) -> bytes:
    limit = int(limit_mb) * 1024 * 1024
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise TooLargeError(f"The {what} is bigger than {limit_mb} MB.")
    return data


def _photo_extension(data: bytes) -> str:
    extension = next((ext for magic, ext in _PHOTO_TYPES.items() if data.startswith(magic)), None)
    if extension is None:
        raise BadRequestError("The photo must be a real JPEG or PNG image.")
    try:
        with Image.open(BytesIO(data)) as image:
            expected_format = "JPEG" if extension == ".jpg" else "PNG"
            if image.format != expected_format:
                raise BadRequestError("The photo file contents do not match a JPEG or PNG image.")
            image.verify()
    except BadRequestError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise BadRequestError("The photo could not be read as a normal JPEG or PNG image.") from exc
    return extension


def _check_wav(data: bytes) -> None:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise BadRequestError("The tap recording must contain a real WAV audio file.")
    try:
        with wave.open(BytesIO(data), "rb") as wav:
            if wav.getframerate() <= 0 or wav.getnchannels() <= 0 or wav.getsampwidth() <= 0:
                raise BadRequestError("The WAV recording has invalid audio settings.")
    except BadRequestError:
        raise
    except (wave.Error, EOFError) as exc:
        raise BadRequestError("The tap recording is damaged. Please upload a valid WAV file.") from exc


def row_to_result(row: Inspection) -> InspectionResult:
    """Rebuild the InspectionResult of a saved inspection."""
    if row.result_json:
        return InspectionResult.model_validate_json(row.result_json)
    return InspectionResult(
        inspection_id=row.id, building_id=row.building_id, building_name=row.building.name,
        floor=row.floor, location=row.location, exposure_class=row.exposure_class,
        created_by=row.user_id, created_at=row.created_at, completed_at=row.completed_at,
        status=row.status, error_message=row.error_message,
        photo_path=row.photo_path, audio_path=row.audio_path,
    )


def create_inspection(db: Session, user: User, building_id: int, floor: str, location: str,
                      exposure_class: str, photo_stream: BinaryIO,
                      wav_stream: Optional[BinaryIO] = None) -> InspectionResult:
    """Validate and store uploads, then return a processing result for HTTP 202."""
    building = repository.get_building(db, building_id)
    if building is None:
        raise NotFoundError("Building not found.")
    limits = load_upload_limits()
    photo_bytes = _read_limited(photo_stream, "photo", limits["photo_max_mb"])
    photo_ext = _photo_extension(photo_bytes)
    wav_bytes = _read_limited(wav_stream, "tap recording", limits["wav_max_mb"]) if wav_stream else None
    if wav_bytes is not None:
        _check_wav(wav_bytes)

    row = repository.create_inspection_row(db, building.id, user.id, floor.strip(), location.strip(), exposure_class)
    folder = storage.inspection_dir(row.id)
    photo_file = folder / f"photo{photo_ext}"  # ignore caller-supplied names
    photo_file.write_bytes(photo_bytes)
    row.photo_path = storage.to_relative(photo_file)
    if wav_bytes is not None:
        wav_file = folder / "tap.wav"
        wav_file.write_bytes(wav_bytes)
        row.audio_path = storage.to_relative(wav_file)
    row.status = "processing"
    db.commit()
    return row_to_result(row)


def process_inspection_task(inspection_id: int) -> None:
    """Run expensive analysis in a fresh background-task database session."""
    with get_sessionmaker()() as db:
        row = repository.get_inspection(db, inspection_id)
        if row is None or row.status != "processing":
            return
        try:
            photo_file = storage.resolve(row.photo_path)
            wav_file = storage.resolve(row.audio_path) if row.audio_path else None
            result = run_pipeline(photo_file, wav_file, row.exposure_class).model_copy(update=dict(
                inspection_id=row.id, building_id=row.building_id, building_name=row.building.name,
                floor=row.floor, location=row.location, created_by=row.user_id, created_at=row.created_at,
            ))
            row.status = result.status
            row.error_message = result.error_message
            row.completed_at = result.completed_at or utcnow()
            row.health_score = result.health_score
            row.result_json = result.model_dump_json()
        except (ScaleError, CrackError) as exc:
            log.info("Inspection %s could not be analysed: %s", row.id, exc.message)
            row.status = "failed"
            row.error_message = exc.message
            row.completed_at = utcnow()
        except Exception:
            log.exception("Unexpected error while processing inspection %s", row.id)
            row.status = "failed"
            row.error_message = "We couldn't finish this inspection. Please try again. If the problem continues, contact support."
            row.completed_at = utcnow()
        db.commit()


def get_inspection(db: Session, inspection_id: int, user: User | None = None) -> InspectionResult:
    row = repository.get_inspection(db, inspection_id)
    if row is None or (user is not None and user.role != "admin" and row.user_id != user.id):
        raise NotFoundError("Inspection not found.")
    return row_to_result(row)


def get_report_file(db: Session, inspection_id: int, user: User | None = None) -> Path:
    result = get_inspection(db, inspection_id, user)
    if result.cost is None or not result.cost.pdf_path:
        raise NotFoundError("This inspection has no report.")
    path = storage.resolve(result.cost.pdf_path)
    if not path.is_file():
        raise NotFoundError("The report file is missing.")
    return path


def list_for_building(db: Session, building_id: int, user: User | None = None) -> List[InspectionResult]:
    if repository.get_building(db, building_id) is None:
        raise NotFoundError("Building not found.")
    rows = repository.list_inspections_for_building(db, building_id)
    if user is not None and user.role != "admin":
        rows = [row for row in rows if row.user_id == user.id]
    return [row_to_result(row) for row in rows]
