"""Shared test helpers. Every test gets its own empty database and storage folder."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.db.session import reset_engine
from app.db.session import get_sessionmaker
from app.db.models import User
from tests.helpers import make_marked_photo_bytes, make_tap_wav_bytes

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def storage_env(tmp_path, monkeypatch):
    """Point the database and storage folder at a throw-away temp folder."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", (tmp_path / "storage").as_posix())
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough-1234567890")
    reset_engine()
    yield tmp_path
    reset_engine()


@pytest.fixture
def client(storage_env):
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(client):
    registered = client.post("/auth/register", json={"username": "student1", "password": "secret123"})
    # The shared legacy endpoint tests need an admin token for building creation.
    # In production, only app.core.create_admin can grant this role.
    with get_sessionmaker()() as db:
        db.get(User, registered.json()["id"]).role = "admin"
        db.commit()
    token = client.post("/auth/login", data={"username": "student1", "password": "secret123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def building(client, auth_headers):
    resp = client.post("/buildings", json={"name": "Main Block", "latitude": 18.6, "longitude": 73.9},
                       headers=auth_headers)
    return resp.json()


@pytest.fixture
def photo_bytes():
    return make_marked_photo_bytes()


@pytest.fixture
def wav_bytes():
    return make_tap_wav_bytes()


@pytest.fixture
def upload(client, auth_headers, photo_bytes, wav_bytes):
    """Function that creates an inspection through the API."""
    def _upload(building_id, floor="2", location="Near staircase B", exposure_class="moderate",
                photo=None, wav=None, photo_name="crack.jpg", wav_name="tap.wav"):
        response = client.post(
            "/inspections",
            data={"building_id": building_id, "floor": floor, "location": location,
                  "exposure_class": exposure_class},
            files={"photo": (photo_name, photo if photo is not None else photo_bytes, "image/jpeg"),
                   "wav": (wav_name, wav if wav is not None else wav_bytes, "audio/wav")},
            headers=auth_headers)
        if response.status_code == 202 and response.json().get("inspection_id"):
            final = client.get(f"/inspections/{response.json()['inspection_id']}", headers=auth_headers)
            return SimpleNamespace(status_code=response.status_code, json=lambda: final.json())
        return response
    return _upload
