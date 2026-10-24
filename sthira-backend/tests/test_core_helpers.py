"""Tests for settings, config loading, security, storage and database start-up."""
import time
from pathlib import Path

import jwt
import pytest

from app.core import security
from app.core.config import get_rule, load_cpwd_rates, load_rules, load_thresholds
from app.core.settings import PROJECT_ROOT, Settings, get_settings
from app.core.storage import resolve, to_relative


def test_config_loaders_read_the_config_folder():
    assert load_thresholds()["marker"]["aruco_size_mm"] == 50
    assert len(load_rules()["rules"]) == 5
    assert len(load_cpwd_rates()["items"]) == 3
    assert get_rule("hairline")["severity"] == 1
    assert get_rule("inconclusive")["label"].startswith("Inconclusive")
    with pytest.raises(KeyError):
        get_rule("no_such_rule")


def test_password_hash_and_check():
    hashed = security.hash_password("secret123")
    assert hashed != "secret123"
    assert security.verify_password("secret123", hashed)
    assert not security.verify_password("wrong", hashed)
    assert not security.verify_password("x", "not-a-hash")


def test_token_round_trip_and_bad_tokens(storage_env):
    token = security.create_access_token(42)
    assert security.decode_access_token(token) == 42
    assert security.decode_access_token("garbage") is None
    other = jwt.encode({"sub": "42"}, "some-other-secret-key-that-is-long-enough-12345", algorithm="HS256")
    assert security.decode_access_token(other) is None


def test_expired_token_is_rejected(storage_env, monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "-1")
    get_settings.cache_clear()
    assert security.decode_access_token(security.create_access_token(1)) is None


def test_relative_database_and_storage_paths_sit_in_the_project_folder():
    s = Settings(database_url="sqlite:///./sthira.db", storage_dir="./storage")
    assert s.storage_path == (PROJECT_ROOT / "storage").resolve()
    assert s.resolved_database_url == "sqlite:///" + (PROJECT_ROOT / "sthira.db").resolve().as_posix()


def test_storage_paths_cannot_escape(storage_env):
    assert to_relative(storage_env / "storage" / "a" / "b.txt") == "a/b.txt"
    with pytest.raises(ValueError):
        resolve("../../etc/passwd")


def test_database_and_storage_folder_are_created_on_first_start(storage_env):
    from fastapi.testclient import TestClient
    from app.main import app
    assert not (storage_env / "test.db").exists()
    with TestClient(app):
        pass
    assert (storage_env / "test.db").is_file()
    assert (storage_env / "storage").is_dir()
