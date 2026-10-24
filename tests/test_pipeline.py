"""Unit tests for the real Stage 7 analysis pipeline."""
from app.core.config import get_rule
from app.core.storage import storage_root
from app.pipeline import run_pipeline
from tests.helpers import make_marked_photo_bytes, make_tap_wav_bytes


def _write_scene(storage_env, *, with_marker=True, with_crack=True, with_audio=True):
    folder = storage_env / "storage" / "inspections" / "pipeline-test"
    folder.mkdir(parents=True, exist_ok=True)
    photo = folder / "photo.jpg"
    photo.write_bytes(make_marked_photo_bytes(with_marker=with_marker, with_crack=with_crack))
    wav = folder / "tap.wav" if with_audio else None
    if wav:
        wav.write_bytes(make_tap_wav_bytes())
    return photo, wav


def test_pipeline_runs_real_modules_and_writes_report_and_images(storage_env):
    photo, wav = _write_scene(storage_env)
    result = run_pipeline(photo, wav, "moderate")
    assert result.status == "completed"
    assert result.scale.marker_found and result.scale.mm_per_px > 0
    assert result.crack.max_width_mm > 0 and result.crack.length_mm > 0
    assert result.audio.classification == "solid"
    assert result.verdict and result.cost
    for relative in (result.scale.warped_image_path, result.crack.mask_path,
                     result.crack.heatmap_path, result.audio.spectrum_image_path,
                     result.cost.pdf_path):
        assert relative and (storage_root() / relative).is_file()


def test_missing_marker_returns_required_failed_inspection(storage_env):
    photo, wav = _write_scene(storage_env, with_marker=False)
    result = run_pipeline(photo, wav, "moderate")
    assert result.status == "failed"
    assert result.error_message == "Marker not visible, please retake the photo."


def test_no_crack_is_completed_with_no_repair(storage_env):
    photo, wav = _write_scene(storage_env, with_crack=False)
    result = run_pipeline(photo, wav, "moderate")
    assert result.status == "completed" and result.error_message == "No crack detected."
    assert result.verdict.label == "No crack detected"
    assert result.crack.max_width_mm == 0 and result.cost.total_rs == 0


def test_missing_audio_completes_photo_work_with_inconclusive_verdict(storage_env):
    photo, wav = _write_scene(storage_env, with_audio=False)
    result = run_pipeline(photo, wav, "moderate")
    assert result.status == "completed"
    assert result.audio.classification == "uncertain" and result.audio.dominant_hz is None
    assert result.verdict.label == "Inconclusive, tap test needed"
    assert result.verdict.severity == get_rule("inconclusive")["severity"]
