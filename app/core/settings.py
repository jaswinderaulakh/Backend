"""Settings read from the .env file (or the computer's environment variables)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(PROJECT_ROOT / ".env"), extra="ignore")

    database_url: str = "sqlite:///./sthira.db"
    storage_dir: str = "./storage"
    # Development-only default. Set a real secret in .env before deploying (Stage 9).
    secret_key: str = "dev-only-secret-change-me-before-deploying-0123456789"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    max_upload_mb: int = 15
    debug: bool = True

    @property
    def storage_path(self) -> Path:
        """Absolute path of the storage/ folder (relative paths count from the project folder)."""
        p = Path(self.storage_dir)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()

    @property
    def resolved_database_url(self) -> str:
        """Same as database_url, but a relative SQLite file is placed in the project folder."""
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            raw = self.database_url[len(prefix):]
            if raw and raw != ":memory:" and not Path(raw).is_absolute():
                return prefix + (PROJECT_ROOT / raw).resolve().as_posix()
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
