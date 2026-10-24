from fastapi import APIRouter
from sqlalchemy import text

from app import __version__
from app.api.deps import DbSession
from app.core.api_schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health(db: DbSession):
    db.execute(text("SELECT 1"))
    return HealthResponse(status="ok", version=__version__, database="ok")
