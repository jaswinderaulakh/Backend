"""Database connection. The database file and tables are created automatically on first start."""
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import get_settings
from app.db import models


@lru_cache
def get_engine():
    url = get_settings().resolved_database_url
    options = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    return create_engine(url, **options)


@lru_cache
def get_sessionmaker() -> sessionmaker:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def init_db() -> None:
    """Create the tables and the storage/ folder if they do not exist yet."""
    models.Base.metadata.create_all(get_engine())
    get_settings().storage_path.mkdir(parents=True, exist_ok=True)


def get_db():
    """FastAPI dependency: one database session per request."""
    db: Session = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()


def reset_engine() -> None:
    """Close the connection and forget cached settings (used by tests)."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_settings.cache_clear()
