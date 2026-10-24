"""Tests: GET /health, POST /auth/register, POST /auth/login, and login protection."""


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["database"] == "ok"


def test_register_works_and_hides_password(client):
    resp = client.post("/auth/register", json={"username": "asha", "password": "secret123"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "asha" and body["id"] >= 1
    assert "password" not in body and "password_hash" not in body


def test_register_same_username_twice_is_refused(client):
    client.post("/auth/register", json={"username": "asha", "password": "secret123"})
    resp = client.post("/auth/register", json={"username": "asha", "password": "other-pass"})
    assert resp.status_code == 409


def test_register_rejects_short_password_and_short_username(client):
    assert client.post("/auth/register", json={"username": "asha", "password": "123"}).status_code == 422
    assert client.post("/auth/register", json={"username": "a", "password": "secret123"}).status_code == 422


def test_register_rejects_password_over_72_bytes(client):
    resp = client.post("/auth/register", json={"username": "asha", "password": "x" * 73})
    assert resp.status_code == 422


def test_login_gives_a_token(client):
    client.post("/auth/register", json={"username": "asha", "password": "secret123"})
    resp = client.post("/auth/login", data={"username": "asha", "password": "secret123"})
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer" and len(resp.json()["access_token"]) > 20


def test_login_wrong_password_or_unknown_user(client):
    client.post("/auth/register", json={"username": "asha", "password": "secret123"})
    assert client.post("/auth/login", data={"username": "asha", "password": "wrong-one"}).status_code == 401
    assert client.post("/auth/login", data={"username": "nobody", "password": "secret123"}).status_code == 401


def test_protected_endpoints_need_a_valid_token(client):
    for method, url in [("get", "/buildings"), ("get", "/inspections/1"), ("get", "/inspections/1/report.pdf"),
                        ("get", "/buildings/1/inspections"), ("get", "/campus/map")]:
        assert getattr(client, method)(url).status_code == 401, url
    assert client.post("/buildings", json={"name": "X", "latitude": 1, "longitude": 1}).status_code == 401
    bad = {"Authorization": "Bearer not-a-real-token"}
    assert client.get("/buildings", headers=bad).status_code == 401
