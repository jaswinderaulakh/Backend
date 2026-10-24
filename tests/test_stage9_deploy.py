"""Stage 9 deployment configuration checks; no remote service is contacted."""
from __future__ import annotations

import pytest

from app.core.settings import get_settings
from app.main import validate_startup_settings


def test_health_endpoint_returns_database_ready_status(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ok"


def test_production_startup_names_a_missing_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("SECRET_KEY", "")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://sthira-campus.test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            validate_startup_settings()
    finally:
        get_settings.cache_clear()
    assert (tmp_path / "storage").is_dir()


def test_startup_never_accepts_wildcard_cors(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="exact origins"):
            validate_startup_settings()
    finally:
        get_settings.cache_clear()


def test_production_rejects_default_localhost_origin(monkeypatch):
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("SECRET_KEY", "a-private-random-secret-with-at-least-32-characters")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./sthira.db")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="CORS_ALLOWED_ORIGINS"):
            validate_startup_settings()
    finally:
        get_settings.cache_clear()
