"""Tests: GET /campus/map (GeoJSON)."""


def test_empty_campus_map(client, auth_headers):
    resp = client.get("/campus/map", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"type": "FeatureCollection", "features": [], "missing_location": []}


def test_building_without_inspections_has_no_health_index(client, auth_headers, building):
    feature = client.get("/campus/map", headers=auth_headers).json()["features"][0]
    assert feature["type"] == "Feature" and feature["geometry"]["type"] == "Point"
    assert feature["geometry"]["coordinates"] == [building["longitude"], building["latitude"]]  # longitude first
    props = feature["properties"]
    assert props["building_id"] == building["id"] and props["name"] == "Main Block"
    from app.campus.health import health_colour
    from app.core.config import load_campus_config
    assert props["health_index"] == load_campus_config()["health_index"]["starting_score"]
    assert props["colour"] == health_colour(props["health_index"])
    assert props["inspection_count"] == 0 and props["worst_verdict"] is None
    assert props["last_inspection_date"] is None


def test_health_index_uses_only_latest_inspection_for_location(client, auth_headers, building, upload, photo_bytes):
    upload(building["id"])
    latest = upload(building["id"], photo=photo_bytes + b"\x00").json()
    props = client.get("/campus/map", headers=auth_headers).json()["features"][0]["properties"]
    assert props["inspection_count"] == 2
    from app.core.config import load_campus_config
    config = load_campus_config()["health_index"]
    penalty = config["severity_penalties"][latest["verdict"]["severity"]]
    assert props["health_index"] == max(config["minimum_score"], config["starting_score"] - penalty)
    assert props["worst_verdict"] == latest["verdict"]["label"]
