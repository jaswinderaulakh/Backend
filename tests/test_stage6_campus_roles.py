"""Stage 6 campus-health, map, login, and role tests."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from sqlalchemy import create_engine, inspect, text

from app.campus.health import calculate_health_index, health_colour, health_index_trend
from app.core.config import load_campus_config, load_security_config
from app.core.settings import get_settings
from app.core import security
from app.db.session import get_sessionmaker


def _record(severity, floor, location, when, inspection_id=1):
    return SimpleNamespace(
        id=inspection_id, status="completed", floor=floor, location=location,
        created_at=when, verdict=SimpleNamespace(severity=severity),
    )


def _inspector_headers(client, username="ordinary-inspector"):
    registered = client.post("/auth/register", json={"username": username, "password": "inspector-pass"})
    assert registered.status_code == 201
    assert registered.json()["role"] == "inspector"
    token = client.post("/auth/login", data={"username": username, "password": "inspector-pass"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health_formula_subtracts_configured_penalty_and_floors_at_minimum():
    config = load_campus_config()["health_index"]
    now = datetime.now(timezone.utc)
    rows = [_record(5, "1", "North", now), _record(4, "2", "South", now, 2)]
    expected = max(config["minimum_score"], config["starting_score"] -
                   config["severity_penalties"][5] - config["severity_penalties"][4])
    assert calculate_health_index(rows) == expected
    many = [_record(5, str(i), f"location-{i}", now, i) for i in range(20)]
    assert calculate_health_index(many) == config["minimum_score"]


def test_only_latest_completed_inspection_per_floor_and_location_counts():
    config = load_campus_config()["health_index"]
    now = datetime.now(timezone.utc)
    rows = [
        _record(5, "1", "North", now - timedelta(days=2), 1),
        _record(1, "1", " north ", now - timedelta(days=1), 2),
        _record(4, "2", "North", now, 3),
        SimpleNamespace(id=4, status="failed", floor="1", location="North", created_at=now,
                        verdict=SimpleNamespace(severity=5)),
    ]
    expected = max(config["minimum_score"], config["starting_score"] -
                   config["severity_penalties"][1] - config["severity_penalties"][4])
    assert calculate_health_index(rows) == expected


def test_colour_boundaries_are_loaded_from_config():
    bands = load_campus_config()["colour_bands"]
    assert health_colour(bands["green_minimum"]) == "green"
    assert health_colour(bands["yellow_minimum"]) == "yellow"
    assert health_colour(bands["yellow_minimum"] - 1) == "red"


def test_empty_building_detail_starts_healthy_with_empty_trend(client, auth_headers, building):
    detail = client.get(f"/buildings/{building['id']}", headers=auth_headers)
    assert detail.status_code == 200
    config = load_campus_config()["health_index"]
    assert detail.json()["health_index"] == config["starting_score"]
    assert detail.json()["inspection_history"] == []
    assert detail.json()["health_index_trend"] == []


def test_building_without_coordinates_is_listed_and_not_mapped(client, auth_headers):
    created = client.post("/buildings", json={"name": "No Location Hall"}, headers=auth_headers)
    assert created.status_code == 201
    campus = client.get("/campus/map", headers=auth_headers).json()
    assert all(feature["properties"]["name"] != "No Location Hall" for feature in campus["features"])
    assert {item["name"] for item in campus["missing_location"]} == {"No Location Hall"}


def test_building_detail_has_sorted_history_and_health_trend(client, auth_headers, building, upload):
    first = upload(building["id"], floor="1", location="Wall A").json()
    second = upload(building["id"], floor="2", location="Wall B", photo_name="other.jpg").json()
    detail = client.get(f"/buildings/{building['id']}", headers=auth_headers).json()
    ids = [item["inspection_id"] for item in detail["inspection_history"]]
    assert ids == [second["inspection_id"], first["inspection_id"]]
    assert len(detail["health_index_trend"]) == 2
    assert detail["health_index"] == detail["health_index_trend"][-1]["health_index"]


def test_registration_cannot_choose_admin_and_inspector_cannot_create_building(client):
    headers = _inspector_headers(client, "role-check-inspector")
    response = client.post("/buildings", json={"name": "Forbidden Hall", "latitude": 1, "longitude": 2},
                           headers=headers)
    assert response.status_code == 403
    assert "Administrator" in response.json()["detail"]


def test_inspector_can_create_inspection_and_admin_can_read_it(client, auth_headers, building, photo_bytes, wav_bytes):
    inspector_headers = _inspector_headers(client, "inspection-writer")
    created = client.post("/inspections", data={"building_id": building["id"], "floor": "1",
                                                 "location": "Inspector wall", "exposure_class": "moderate"},
                          files={"photo": ("wall.jpg", photo_bytes, "image/jpeg"),
                                 "wav": ("tap.wav", wav_bytes, "audio/wav")}, headers=inspector_headers)
    assert created.status_code == 202
    inspection_id = created.json()["inspection_id"]
    assert client.get(f"/inspections/{inspection_id}", headers=inspector_headers).status_code == 200
    assert client.get(f"/inspections/{inspection_id}", headers=auth_headers).status_code == 200


def test_inspector_cannot_read_another_users_inspection(client, auth_headers, building, upload):
    created = upload(building["id"]).json()  # created by the administrator fixture user
    inspector_headers = _inspector_headers(client, "read-only-inspector")
    assert client.get(f"/inspections/{created['inspection_id']}", headers=inspector_headers).status_code == 404
    assert client.get(f"/inspections/{created['inspection_id']}/report.pdf", headers=inspector_headers).status_code == 404
    assert client.get(f"/buildings/{building['id']}/inspections", headers=inspector_headers).json() == []


def test_wrong_password_is_clear_and_failed_login_is_rate_limited(client):
    username = "limited-login-test"
    client.post("/auth/register", json={"username": username, "password": "right-pass"})
    config = load_security_config()["login_rate_limit"]
    for _ in range(config["attempts"]):
        response = client.post("/auth/login", data={"username": username, "password": "wrong-pass"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Wrong username or password."
    blocked = client.post("/auth/login", data={"username": username, "password": "right-pass"})
    assert blocked.status_code == 429
    assert "wait" in blocked.json()["detail"].lower()


def test_expired_token_is_rejected(storage_env, monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "-1")
    get_settings.cache_clear()
    token = security.create_access_token(123)
    assert security.decode_access_token(token) is None


def test_demo_seed_creates_six_fictional_pune_buildings_once(storage_env):
    from app.campus.seed_demo import main
    from app.db.models import Building, Inspection
    main()
    main()
    with get_sessionmaker()() as db:
        assert db.query(Building).filter(Building.name.like("Demo — %")).count() == 6
        assert db.query(Inspection).join(Building).filter(Building.name.like("Demo — %")).count() == 12


def test_sqlite_stage6_migration_adds_role_and_allows_unknown_coordinates(tmp_path):
    path = tmp_path / "old-schema.sqlite"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(50) NOT NULL, password_hash VARCHAR(100) NOT NULL, created_at DATETIME NOT NULL)")
        connection.exec_driver_sql("CREATE TABLE buildings (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE, latitude FLOAT NOT NULL, longitude FLOAT NOT NULL, created_at DATETIME NOT NULL)")
        connection.exec_driver_sql("CREATE TABLE inspections (id INTEGER PRIMARY KEY, building_id INTEGER NOT NULL REFERENCES buildings(id))")
        connection.exec_driver_sql("INSERT INTO users VALUES (1, 'old-user', 'hash', '2026-01-01')")
        connection.exec_driver_sql("INSERT INTO buildings VALUES (1, 'Old Hall', 1, 2, '2026-01-01')")
    from app.db.session import _upgrade_stage6_sqlite_schema
    _upgrade_stage6_sqlite_schema(engine)
    with engine.begin() as connection:
        assert "role" in {column["name"] for column in inspect(connection).get_columns("users")}
        building_columns = {column["name"]: column for column in inspect(connection).get_columns("buildings")}
        assert building_columns["latitude"]["nullable"] is True
        row = connection.execute(text("SELECT role FROM users WHERE id=1")).one()
        assert row.role == "inspector"
        connection.execute(text("INSERT INTO buildings (name, created_at) VALUES ('No Coords', '2026-01-01')"))
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    engine.dispose()
