"""Tests: POST /buildings, GET /buildings."""


def test_create_building(client, auth_headers):
    resp = client.post("/buildings", json={"name": "Library", "latitude": 18.61, "longitude": 73.91},
                       headers=auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Library" and body["latitude"] == 18.61 and body["longitude"] == 73.91
    assert body["id"] >= 1 and body["created_at"]


def test_list_buildings(client, auth_headers):
    assert client.get("/buildings", headers=auth_headers).json() == []
    for name in ("Library", "Workshop"):
        client.post("/buildings", json={"name": name, "latitude": 18.6, "longitude": 73.9}, headers=auth_headers)
    names = [b["name"] for b in client.get("/buildings", headers=auth_headers).json()]
    assert names == ["Library", "Workshop"]


def test_duplicate_building_name_is_refused(client, auth_headers, building):
    resp = client.post("/buildings", json={"name": "Main Block", "latitude": 1, "longitude": 1},
                       headers=auth_headers)
    assert resp.status_code == 409


def test_building_position_must_be_on_earth(client, auth_headers):
    assert client.post("/buildings", json={"name": "A", "latitude": 95, "longitude": 10},
                       headers=auth_headers).status_code == 422
    assert client.post("/buildings", json={"name": "B", "latitude": 10, "longitude": 200},
                       headers=auth_headers).status_code == 422


def test_building_needs_a_name(client, auth_headers):
    assert client.post("/buildings", json={"name": "  ", "latitude": 10, "longitude": 10},
                       headers=auth_headers).status_code == 422
