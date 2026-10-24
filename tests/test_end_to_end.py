"""End-to-end tests for real analysis through the asynchronous upload API."""
from __future__ import annotations

import time

from app.core.config import load_campus_config, load_thresholds, load_upload_limits
from tests.helpers import make_marked_photo_bytes, make_tap_wav_bytes


def _submit(client, headers, building_id, photo, wav=None, photo_name="scene.jpg"):
    files = {"photo": (photo_name, photo, "image/jpeg")}
    if wav is not None:
        files["wav"] = ("tap.wav", wav, "audio/wav")
    return client.post(
        "/inspections",
        data={"building_id": building_id, "floor": "Ground", "location": "North test wall",
              "exposure_class": "moderate"},
        files=files, headers=headers,
    )


def _wait_for_final(client, headers, inspection_id):
    result = None
    for _ in range(200):
        response = client.get(f"/inspections/{inspection_id}", headers=headers)
        assert response.status_code == 200
        result = response.json()
        if result["status"] != "processing":
            return result
        time.sleep(0.05)
    raise AssertionError(f"Inspection {inspection_id} remained processing too long")


def test_generated_known_width_scene_completes_pdf_and_updates_health(client, auth_headers, building):
    thresholds = load_thresholds()
    true_width_px = 12
    expected_width_mm = true_width_px * thresholds["marker"]["aruco_size_mm"] / 300
    response = _submit(client, auth_headers, building["id"],
                       make_marked_photo_bytes(crack_width_px=true_width_px), make_tap_wav_bytes(1800),
                       photo_name="../../unsafe-name.jpg")
    assert response.status_code == 202
    accepted = response.json()
    assert accepted["status"] == "processing" and accepted["inspection_id"] > 0
    result = _wait_for_final(client, auth_headers, accepted["inspection_id"])
    assert result["status"] == "completed"
    assert result["scale"]["marker_found"] is True
    assert result["crack"]["max_width_mm"] > 0
    width_error_mm = abs(result["crack"]["max_width_mm"] - expected_width_mm)
    print(f"Synthetic truth width: {expected_width_mm:.3f} mm; measured: "
          f"{result['crack']['max_width_mm']:.3f} mm; absolute error: {width_error_mm:.3f} mm")
    assert width_error_mm <= 1.0, f"synthetic crack width error was {width_error_mm:.3f} mm"
    assert result["audio"]["classification"] == "solid"
    assert result["verdict"]["label"]
    assert result["cost"]["total_rs"] >= 0
    assert result["photo_path"].endswith("/photo.jpg")  # caller filename was ignored

    storage = client.get(f"/inspections/{accepted['inspection_id']}", headers=auth_headers).json()
    from app.core.storage import resolve
    pdf_path = resolve(storage["cost"]["pdf_path"])
    pdf_bytes = pdf_path.read_bytes()
    assert pdf_bytes.startswith(b"%PDF-") and pdf_bytes.rstrip().endswith(b"%%EOF")
    assert pdf_path.stat().st_size > 1000

    feature = client.get("/campus/map", headers=auth_headers).json()["features"][0]["properties"]
    config = load_campus_config()["health_index"]
    penalty = config["severity_penalties"][result["verdict"]["severity"]]
    assert feature["inspection_count"] == 1
    assert feature["health_index"] == max(config["minimum_score"], config["starting_score"] - penalty)
    assert feature["worst_verdict"] == result["verdict"]["label"]


def test_missing_marker_fails_with_exact_plain_english_message(client, auth_headers, building):
    response = _submit(client, auth_headers, building["id"],
                       make_marked_photo_bytes(with_marker=False), make_tap_wav_bytes())
    assert response.status_code == 202
    result = _wait_for_final(client, auth_headers, response.json()["inspection_id"])
    assert result["status"] == "failed"
    assert result["error_message"] == "Marker not visible, please retake the photo."


def test_no_crack_is_a_completed_no_repair_result(client, auth_headers, building):
    response = _submit(client, auth_headers, building["id"],
                       make_marked_photo_bytes(with_crack=False), make_tap_wav_bytes())
    result = _wait_for_final(client, auth_headers, response.json()["inspection_id"])
    assert result["status"] == "completed"
    assert result["error_message"] == "No crack detected."
    assert result["verdict"]["label"] == "No crack detected"
    assert result["cost"]["total_rs"] == 0


def test_missing_audio_still_completes_photo_analysis(client, auth_headers, building):
    response = _submit(client, auth_headers, building["id"], make_marked_photo_bytes(), wav=None)
    assert response.status_code == 202
    result = _wait_for_final(client, auth_headers, response.json()["inspection_id"])
    assert result["status"] == "completed"
    assert result["audio"]["classification"] == "uncertain"
    assert result["verdict"]["label"] == "Inconclusive, tap test needed"


def test_silent_audio_still_completes_photo_analysis(client, auth_headers, building):
    response = _submit(client, auth_headers, building["id"], make_marked_photo_bytes(),
                       make_tap_wav_bytes(silent=True))
    result = _wait_for_final(client, auth_headers, response.json()["inspection_id"])
    assert result["status"] == "completed"
    assert result["audio"]["classification"] == "uncertain"
    assert result["audio"]["dominant_hz"] is None
    assert result["verdict"]["label"] == "Inconclusive, tap test needed"


def test_unexpected_error_is_generic_to_user_and_detailed_in_logs(client, auth_headers, building, monkeypatch):
    import app.core.inspection_service as service
    from pathlib import Path
    from app.core.settings import PROJECT_ROOT

    def fail_unexpectedly(*args, **kwargs):
        raise RuntimeError("private technical detail for the log")
    monkeypatch.setattr(service, "run_pipeline", fail_unexpectedly)
    response = _submit(client, auth_headers, building["id"], make_marked_photo_bytes(), make_tap_wav_bytes())
    result = _wait_for_final(client, auth_headers, response.json()["inspection_id"])
    assert result["status"] == "failed"
    assert "couldn't finish" in result["error_message"]
    assert "private technical detail" not in result["error_message"]
    log_file = PROJECT_ROOT / "logs" / "sthira.log"
    assert log_file.is_file() and "private technical detail for the log" in log_file.read_text(encoding="utf-8")


def test_upload_limits_are_configured_separately_for_photo_and_wav():
    limits = load_upload_limits()
    assert limits["photo_max_mb"] == 15
    assert limits["wav_max_mb"] == 10
