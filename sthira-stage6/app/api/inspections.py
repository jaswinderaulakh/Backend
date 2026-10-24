from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, DbSession
from app.core import inspection_service
from app.core.schemas import InspectionResult

router = APIRouter(prefix="/inspections", tags=["Inspections"])


@router.post("", response_model=InspectionResult, status_code=201)
def create_inspection(
    photo: Annotated[UploadFile, File(description="Crack photo (JPEG or PNG) with the 5 cm marker in view")],
    wav: Annotated[UploadFile, File(description="3-second coin-tap recording, .wav, 48 kHz")],
    building_id: Annotated[int, Form()],
    floor: Annotated[str, Form(min_length=1, max_length=20)],
    location: Annotated[str, Form(min_length=1, max_length=200)],
    exposure_class: Annotated[Literal["mild", "moderate", "severe"], Form()],
    db: DbSession,
    user: CurrentUser,
):
    return inspection_service.create_inspection(
        db, user, building_id, floor, location, exposure_class, photo.file, wav.file)


@router.get("/{inspection_id}", response_model=InspectionResult)
def get_inspection(inspection_id: int, db: DbSession, user: CurrentUser):
    return inspection_service.get_inspection(db, inspection_id, user)


@router.get("/{inspection_id}/report.pdf")
def download_report(inspection_id: int, db: DbSession, user: CurrentUser):
    path = inspection_service.get_report_file(db, inspection_id, user)
    return FileResponse(path, media_type="application/pdf", filename=f"STHIRA_inspection_{inspection_id}.pdf")
