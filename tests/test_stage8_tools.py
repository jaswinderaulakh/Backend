"""Small generated-data tests for the local Stage 8 checking tools."""
from __future__ import annotations

import csv
from pathlib import Path

from tests.helpers import make_marked_photo_bytes, make_tap_wav_bytes
from tools.batch_check import run_batch
from tools.tune_audio import run_audio_tuning
from tools.tune_width import run_width_tuning


def _write_truth(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["photo", "wav", "true_width_mm", "tap_type", "notes"])
        writer.writeheader()
        writer.writerows(rows)


def test_batch_tool_writes_results_and_continues_after_a_missing_file(tmp_path):
    data = tmp_path / "real_data"
    data.mkdir()
    (data / "known.jpg").write_bytes(make_marked_photo_bytes())
    (data / "known.wav").write_bytes(make_tap_wav_bytes(1800))
    truth = data / "truth.csv"
    _write_truth(truth, [
        {"photo": "known.jpg", "wav": "known.wav", "true_width_mm": "2.0", "tap_type": "solid", "notes": "generated test"},
        {"photo": "missing.jpg", "wav": "missing.wav", "true_width_mm": "1.0", "tap_type": "hollow", "notes": "generated failure"},
    ])
    out = tmp_path / "output"
    results = run_batch(truth, out)
    assert len(results) == 2
    assert results[0]["measured_width_mm"]
    assert abs(float(results[0]["width_error_mm"])) <= 1.0
    assert "not found" in results[1]["error"].lower()
    assert (out / "results.csv").is_file()
    assert "generated failure" not in (out / "results.html").read_text(encoding="utf-8")
    assert "STHIRA batch check" in (out / "results.html").read_text(encoding="utf-8")


def test_audio_tuner_plots_and_suggests_without_changing_thresholds(tmp_path):
    data = tmp_path / "real_data"
    data.mkdir()
    (data / "hollow.wav").write_bytes(make_tap_wav_bytes(450))
    (data / "solid.wav").write_bytes(make_tap_wav_bytes(1800))
    truth = data / "truth.csv"
    _write_truth(truth, [
        {"photo": "not-used.jpg", "wav": "hollow.wav", "true_width_mm": "1", "tap_type": "hollow", "notes": "generated"},
        {"photo": "not-used.jpg", "wav": "solid.wav", "true_width_mm": "1", "tap_type": "solid", "notes": "generated"},
    ])
    from app.core.settings import PROJECT_ROOT
    settings = PROJECT_ROOT / "config" / "thresholds.yaml"
    before = settings.read_bytes()
    result = run_audio_tuning(truth, tmp_path / "output")
    assert result["counts"] == {"hollow": 1, "solid": 1}
    assert result["suggested_void_below_hz"] < result["suggested_solid_above_hz"]
    assert result["plot_path"].is_file()
    assert settings.read_bytes() == before


def test_width_tuner_reports_bias_and_trusted_limit_without_editing_config(tmp_path):
    data = tmp_path / "real_data"
    data.mkdir()
    (data / "known.jpg").write_bytes(make_marked_photo_bytes())
    truth = data / "truth.csv"
    _write_truth(truth, [{"photo": "known.jpg", "wav": "", "true_width_mm": "2.0",
                          "tap_type": "solid", "notes": "generated test"}])
    from app.core.settings import PROJECT_ROOT
    settings = PROJECT_ROOT / "config" / "thresholds.yaml"
    before = settings.read_bytes()
    result = run_width_tuning(truth, tmp_path / "output")
    assert result["rows"][0]["measured_width_mm"]
    assert result["average_bias_mm"] is not None
    assert result["smallest_trusted_width_mm"] > 0
    assert result["csv_path"].is_file()
    assert settings.read_bytes() == before
