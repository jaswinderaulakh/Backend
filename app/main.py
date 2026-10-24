"""STHIRA backend entry point. Start locally with: uvicorn app.main:app"""
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import auth, buildings, campus, health, inspections
from app.core.errors import AppError
from app.core.settings import PROJECT_ROOT, Settings, get_settings
from app.db.session import init_db


def validate_startup_settings() -> Settings:
    """Create local folders and refuse unsafe or incomplete production settings."""
    settings = get_settings()
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "logs").mkdir(parents=True, exist_ok=True)

    origins = settings.cors_origins
    if any(origin == "*" for origin in origins):
        raise RuntimeError("Startup configuration error: CORS_ALLOWED_ORIGINS must list exact origins; '*' is not allowed.")

    if not settings.debug:
        problems: list[str] = []
        secret = settings.secret_key.strip()
        if (len(secret) < 32 or any(word in secret.lower() for word in ("change-me", "replace-with", "dev-only", "your-secret"))):
            problems.append("SECRET_KEY (set a private random value of at least 32 characters)")
        if not origins or any("localhost" in origin.lower() or ".example" in origin.lower() for origin in origins):
            problems.append("CORS_ALLOWED_ORIGINS (set your exact app/web origin; do not use '*')")
        if not settings.database_url.strip():
            problems.append("DATABASE_URL (set a SQLite URL or another supported SQLAlchemy URL)")
        if problems:
            raise RuntimeError("Production startup is blocked. Set valid environment variables: " + "; ".join(problems) + ".")
    return settings


def configure_file_logging() -> None:
    log_path = (PROJECT_ROOT / "logs" / "sthira.log").resolve()
    logger = logging.getLogger("sthira")
    logger.setLevel(logging.INFO)
    if not any(getattr(handler, "baseFilename", None) == str(log_path) for handler in logger.handlers):
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_startup_settings()
    configure_file_logging()
    init_db()
    yield


app = FastAPI(
    title="STHIRA Backend",
    version=__version__,
    description="Campus structural-health monitoring API with photo, scale, crack and tap analysis.",
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(AppError)
async def handle_app_error(request, exc: AppError):
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)


for module in (health, auth, buildings, inspections, campus):
    app.include_router(module.router)
