"""Database connection. The database file and tables are created automatically on first start."""
from functools import lru_cache

from sqlalchemy import create_engine, inspect
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
    engine = get_engine()
    models.Base.metadata.create_all(engine)
    _upgrade_stage6_sqlite_schema(engine)
    get_settings().storage_path.mkdir(parents=True, exist_ok=True)


def _upgrade_stage6_sqlite_schema(engine) -> None:
    """Add role data and make old SQLite building coordinates optional."""
    if not engine.dialect.name == "sqlite":
        return
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        user_columns = {column["name"] for column in inspect(connection).get_columns("users")}
        if "role" not in user_columns:
            connection.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'inspector'"
            )
            connection.commit()

        building_columns = inspect(connection).get_columns("buildings")
        required = {column["name"]: column for column in building_columns}
        if required.get("latitude", {}).get("nullable", True) is False or required.get("longitude", {}).get("nullable", True) is False:
            connection.exec_driver_sql("""
                CREATE TABLE buildings_stage6 (
                    id INTEGER NOT NULL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    latitude FLOAT,
                    longitude FLOAT,
                    created_at DATETIME NOT NULL
                )
            """)
            connection.exec_driver_sql("""
                INSERT INTO buildings_stage6 (id, name, latitude, longitude, created_at)
                SELECT id, name, latitude, longitude, created_at FROM buildings
            """)
            connection.exec_driver_sql("DROP TABLE buildings")
            connection.exec_driver_sql("ALTER TABLE buildings_stage6 RENAME TO buildings")
            connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")


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
