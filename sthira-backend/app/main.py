"""STHIRA backend entry point. Start with:  uvicorn app.main:app --reload"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app import __version__
from app.api import auth, buildings, campus, health, inspections
from app.core.errors import AppError
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # creates the database file, tables and storage/ folder on first start
    yield


app = FastAPI(
    title="STHIRA Backend",
    version=__version__,
    description="Structural Health Inspector & Risk Assessment. STAGE 1: all analysis results are FAKE.",
    lifespan=lifespan,
)


@app.exception_handler(AppError)
async def handle_app_error(request, exc: AppError):
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)


for module in (health, auth, buildings, inspections, campus):
    app.include_router(module.router)
