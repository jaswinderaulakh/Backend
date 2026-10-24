"""Tests: POST /inspections, GET /inspections/{id}, report.pdf, GET /buildings/{id}/inspections."""
from pathlib import Path

from app.core.schemas import InspectionResult


def test_create_inspection_returns_a_full_valid_result(client, building, upload):
    resp = upload(building["id"])
    assert resp.status_code == 202
    result = InspectionResult.model_validate(resp.json())  # exactly the shape in schemas.py
    assert result.status == "completed" and result.error_message is None
    assert result.inspection_id >= 1
    assert result.building_id == building["id"] and result.building_name == "Main Block"
    assert result.floor == "2" and result.location == "Near staircase B"
    assert result.exposure_class == "moderate"
    assert result.created_by is not None and result.created_at and result.completed_at
    assert result.scale.marker_found and result.scale.mm_per_px > 0
    assert result.crack.max_width_mm >= result.crack.mean_width_mm
    assert result.audio.classification in ("solid", "void", "uncertain")
    assert 1 <= result.verdict.severity <= 5 and result.verdict.reason
    assert 0 <= result.health_score <= 100
    assert result.cost.total_rs == round(sum(i.amount_rs for i in result.cost.items), 2)
    assert result.cost.rates_are_placeholder is True


def test_uploaded_files_are_saved_in_storage(client, storage_env, building, upload):
    result = upload(building["id"]).json()
    storage = Path(storage_env) / "storage"
    assert (storage / result["photo_path"]).is_file()
    assert (storage / result["audio_path"]).is_file()
    assert (storage / result["cost"]["pdf_path"]).is_file()


def test_get_inspection_matches_what_was_created(client, auth_headers, building, upload):
    created = upload(building["id"]).json()
    resp = client.get(f"/inspections/{created['inspection_id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == created


def test_get_unknown_inspection_is_404(client, auth_headers):
    assert client.get("/inspections/999", headers=auth_headers).status_code == 404


def test_download_pdf_report(client, auth_headers, building, upload):
    inspection_id = upload(building["id"]).json()["inspection_id"]
    resp = client.get(f"/inspections/{inspection_id}/report.pdf", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


def test_pdf_of_unknown_inspection_is_404(client, auth_headers):
    assert client.get("/inspections/999/report.pdf", headers=auth_headers).status_code == 404


def test_history_lists_newest_first(client, auth_headers, building, upload, photo_bytes):
    first = upload(building["id"], floor="1").json()
    second = upload(building["id"], floor="2", photo=photo_bytes + b"\x00" * 7).json()
    resp = client.get(f"/buildings/{building['id']}/inspections", headers=auth_headers)
    assert resp.status_code == 200
    assert [r["inspection_id"] for r in resp.json()] == [second["inspection_id"], first["inspection_id"]]
    for item in resp.json():
        InspectionResult.model_validate(item)


def test_history_only_shows_that_building(client, auth_headers, building, upload):
    other = client.post("/buildings", json={"name": "Library", "latitude": 18.7, "longitude": 73.8},
                        headers=auth_headers).json()
    upload(building["id"])
    assert client.get(f"/buildings/{other['id']}/inspections", headers=auth_headers).json() == []


def test_history_of_unknown_building_is_404(client, auth_headers):
    assert client.get("/buildings/999/inspections", headers=auth_headers).status_code == 404


def test_inspection_for_unknown_building_is_404(upload):
    assert upload(999).status_code == 404


def test_bad_exposure_class_is_422(building, upload):
    assert upload(building["id"], exposure_class="extreme").status_code == 422


def test_all_three_exposure_classes_work(building, upload):
    for exposure in ("mild", "moderate", "severe"):
        resp = upload(building["id"], exposure_class=exposure)
        assert resp.status_code == 202 and resp.json()["exposure_class"] == exposure


def test_missing_photo_or_required_fields_is_422(client, auth_headers, building):
    resp = client.post("/inspections", data={"building_id": building["id"], "floor": "1", "location": "x",
                                             "exposure_class": "mild"}, headers=auth_headers)
    assert resp.status_code == 422
    resp = client.post("/inspections", data={"building_id": building["id"]}, headers=auth_headers)
    assert resp.status_code == 422


def test_photo_must_be_a_jpeg_or_png(building, upload):
    resp = upload(building["id"], photo=b"this is not an image")
    assert resp.status_code == 400 and "JPEG or PNG" in resp.json()["detail"]


def test_recording_must_be_a_wav(building, upload):
    resp = upload(building["id"], wav=b"this is not a wav file")
    assert resp.status_code == 400 and "WAV" in resp.json()["detail"]


def test_empty_files_are_refused(building, upload):
    assert upload(building["id"], photo=b"").status_code == 400
    assert upload(building["id"], wav=b"").status_code == 400


def test_too_big_upload_is_refused(building, upload, monkeypatch, photo_bytes):
    import app.core.inspection_service as service
    monkeypatch.setattr(service, "load_upload_limits", lambda: {"photo_max_mb": 0, "wav_max_mb": 0})
    assert upload(building["id"]).status_code == 413


def test_same_image_and_audio_give_the_same_real_verdict(building, upload):
    a = upload(building["id"]).json()
    b = upload(building["id"]).json()
    assert a["verdict"]["label"] == b["verdict"]["label"]


def test_failed_analysis_is_saved_as_failed(client, auth_headers, building, upload, monkeypatch):
    import app.core.inspection_service as service

    def boom(*args, **kwargs):
        raise RuntimeError("test failure")
    monkeypatch.setattr(service, "run_pipeline", boom)
    resp = upload(building["id"])
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "failed" and "couldn't finish" in body["error_message"]
    assert "test failure" not in body["error_message"]
    assert body["verdict"] is None and body["cost"] is None
    assert client.get(f"/inspections/{body['inspection_id']}", headers=auth_headers).json()["status"] == "failed"
