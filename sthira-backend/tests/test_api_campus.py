"""Tests: GET /campus/map (GeoJSON)."""


def test_empty_campus_map(client, auth_headers):
    resp = client.get("/campus/map", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"type": "FeatureCollection", "features": []}


def test_building_without_inspections_has_no_health_index(client, auth_headers, building):
    feature = client.get("/campus/map", headers=auth_headers).json()["features"][0]
    assert feature["type"] == "Feature" and feature["geometry"]["type"] == "Point"
    assert feature["geometry"]["coordinates"] == [building["longitude"], building["latitude"]]  # longitude first
    props = feature["properties"]
    assert props["building_id"] == building["id"] and props["name"] == "Main Block"
    assert props["health_index"] is None and props["inspection_count"] == 0


def test_health_index_is_average_of_inspection_scores(client, auth_headers, building, upload, photo_bytes):
    scores = [upload(building["id"]).json()["health_score"],
              upload(building["id"], photo=photo_bytes + b"\x00").json()["health_score"]]
    props = client.get("/campus/map", headers=auth_headers).json()["features"][0]["properties"]
    assert props["inspection_count"] == 2
    assert props["health_index"] == round(sum(scores) / 2, 1)
