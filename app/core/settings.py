"""Environment-backed settings used locally and in production."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEVELOPMENT_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(PROJECT_ROOT / ".env"), extra="ignore")

    database_url: str = "sqlite:///./sthira.db"
    storage_dir: str = "./storage"
    # Development-only fallback. Production startup refuses this placeholder.
    secret_key: str = "dev-only-secret-change-me-before-deploying-0123456789"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    max_upload_mb: int = 15  # legacy setting; current per-file limits are in config/uploads.yaml
    debug: bool = True
    cors_allowed_origins: str = DEVELOPMENT_CORS_ORIGINS

    @property
    def storage_path(self) -> Path:
        """Absolute storage directory; relative paths are rooted in the project folder."""
        p = Path(self.storage_dir)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()

    @property
    def cors_origins(self) -> list[str]:
        """Comma-separated, exact browser origins; a wildcard is never needed."""
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def resolved_database_url(self) -> str:
        """Resolve relative SQLite files; other SQLAlchemy URLs pass through unchanged."""
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            raw = self.database_url[len(prefix):]
            if raw and raw != ":memory:" and not Path(raw).is_absolute():
                return prefix + (PROJECT_ROOT / raw).resolve().as_posix()
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
