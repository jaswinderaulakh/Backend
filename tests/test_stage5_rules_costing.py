"""Stage 5 tests for verdict rules, cost estimates, and PDF reports."""
from datetime import datetime, timezone

import pytest

from app.core.config import load_cpwd_rates, load_rules, load_thresholds
from app.core.schemas import AudioResult, CrackResult, InspectionResult
from app.costing.estimate import compare_repair_options, estimate_cost
from app.costing.report import make_pdf
from app.rules.engine import decide_verdict


def sample_crack(width=0.2, angle=90, length=1000):
    return CrackResult(max_width_mm=width, mean_width_mm=width / 2, length_mm=length, angle_deg=angle)


def sample_audio(hz=1800):
    t = load_thresholds()["audio"]
    classification = "void" if hz < t["void_below_hz"] else "solid" if hz > t["solid_above_hz"] else "uncertain"
    return AudioResult(dominant_hz=hz, classification=classification)


def test_each_configured_verdict_row_matches_in_config_order():
    t = load_thresholds()
    c = t["crack"]
    audio = t["audio"]
    cases = [
        ("shear_risk", sample_crack(c["significant_above_mm"] + 0.1,
                                     (c["shear_angle_min_deg"] + c["shear_angle_max_deg"]) / 2),
         sample_audio(audio["solid_above_hz"] + 100)),
        ("void_risk", sample_crack(c["significant_above_mm"] + 0.1, 0),
         sample_audio(max(1, audio["void_below_hz"] - 100))),
        ("plaster_spalling", sample_crack(c["significant_above_mm"] + 0.1, 90),
         sample_audio(audio["solid_above_hz"] + 100)),
        ("minor", sample_crack((c["hairline_below_mm"] + c["significant_above_mm"]) / 2, 90),
         sample_audio(audio["solid_above_hz"] + 100)),
        ("hairline", sample_crack(c["hairline_below_mm"] / 2, 90),
         sample_audio(audio["solid_above_hz"] + 100)),
    ]
    for rule_id, crack, audio_result in cases:
        rule = next(row for row in load_rules()["rules"] if row["id"] == rule_id)
        verdict = decide_verdict(crack, audio_result, "moderate")
        assert verdict.label == rule["label"]
        assert verdict.severity == rule["severity"]


def test_inconclusive_fallback_mentions_missing_rule_match():
    config = load_rules()["fallback"]
    thresholds = load_thresholds()["audio"]
    verdict = decide_verdict(sample_crack(0.2, 90), sample_audio((thresholds["void_below_hz"] + thresholds["solid_above_hz"]) / 2), "mild")
    assert verdict.label == config["label"]
    assert verdict.severity == config["severity"]
    assert "no configured rule matched" in verdict.reason


@pytest.mark.parametrize("exposure", ["mild", "moderate", "severe"])
def test_reason_names_exposure_limit_and_measured_width(exposure):
    limit = load_thresholds()["is456_crack_limit_mm"][exposure]
    crack = sample_crack(limit, 90)
    verdict = decide_verdict(crack, sample_audio(), exposure)
    assert exposure in verdict.reason
    assert f"{limit:g} mm" in verdict.reason
    assert f"{limit:g} mm" in verdict.reason
    assert "does not exceed" in verdict.reason


def test_width_equal_to_significant_threshold_is_not_strictly_wide():
    c = load_thresholds()["crack"]
    a = load_thresholds()["audio"]
    width = c["significant_above_mm"]  # exactly 0.3 mm: gt is false, inclusive minor band applies
    verdict = decide_verdict(sample_crack(width, 90), sample_audio(a["solid_above_hz"] + 10), "moderate")
    assert verdict.label == next(r["label"] for r in load_rules()["rules"] if r["id"] == "minor")


def test_frequency_equal_to_void_threshold_is_not_below():
    a = load_thresholds()["audio"]
    verdict = decide_verdict(sample_crack(load_thresholds()["crack"]["significant_above_mm"] + 0.1, 90),
                             sample_audio(a["void_below_hz"]), "moderate")
    assert verdict.label == load_rules()["fallback"]["label"]  # 900 Hz does not satisfy strict lt


def test_frequency_equal_to_solid_threshold_is_not_above():
    a = load_thresholds()["audio"]
    verdict = decide_verdict(sample_crack(0.2, 90), sample_audio(a["solid_above_hz"]), "moderate")
    assert verdict.label == load_rules()["fallback"]["label"]  # 1400 Hz does not satisfy strict gt


@pytest.mark.parametrize("angle", [30, 60])
def test_shear_angle_boundaries_are_inclusive(angle):
    c = load_thresholds()["crack"]
    # Both endpoints of the configured 30-to-60 degree interval fall inside it.
    verdict = decide_verdict(sample_crack(c["significant_above_mm"] + 0.1, angle), sample_audio(), "moderate")
    assert verdict.label == next(r["label"] for r in load_rules()["rules"] if r["id"] == "shear_risk")


def test_unknown_exposure_class_is_plain_english_error():
    with pytest.raises(ValueError, match="Exposure class must be one of"):
        decide_verdict(sample_crack(), sample_audio(), "extreme")


def test_cost_quantities_totals_and_option_comparison():
    verdict = decide_verdict(sample_crack(0.5, 90, 1250), sample_audio(700), "moderate")
    estimate = estimate_cost(verdict, sample_crack(0.5, 90, 1250))
    rates = {item["id"]: item for item in load_cpwd_rates()["items"]}
    assert estimate.rates_are_placeholder is bool(load_cpwd_rates().get("is_placeholder", True))
    assert estimate.total_rs == round(sum(item.amount_rs for item in estimate.items), 2)
    for item in estimate.items:
        assert item.amount_rs == round(item.quantity * item.rate_rs, 2)
        source = next(row for row in rates.values() if row["description"] == item.description)
        expected_qty = round(1.25 if source["unit"] == "rmt" else 1.25 * 0.5, 2)
        assert item.quantity == expected_qty
    options = compare_repair_options(verdict, sample_crack(0.5, 90, 1250))
    assert options["cheaper"].total_rs <= options["recommended"].total_rs


def _report_result(photo=None, heatmap=None, spectrum=None):
    crack = sample_crack(0.25, 90, 1250).model_copy(update={"heatmap_path": heatmap})
    audio = sample_audio(1800).model_copy(update={"spectrum_image_path": spectrum})
    verdict = decide_verdict(crack, audio, "moderate")
    rate_estimate = estimate_cost(verdict, crack)
    return InspectionResult(inspection_id=123, building_id=7, building_name="Test Hall", floor="2",
                           location="North wall", exposure_class="moderate", created_at=datetime.now(timezone.utc),
                           completed_at=datetime.now(timezone.utc), status="completed", photo_path=photo,
                           crack=crack, audio=audio, verdict=verdict, exceeds_is456_limit=True,
                           health_score=60, cost=rate_estimate)


def test_report_pdf_is_created_and_non_empty(tmp_path):
    output = tmp_path / "inspection.pdf"
    assert make_pdf(_report_result(), str(output)) == str(output)
    assert output.is_file() and output.stat().st_size > 100
    assert output.read_bytes().startswith(b"%PDF")


def test_report_does_not_crash_when_images_are_missing(tmp_path):
    result = _report_result("does-not-exist-photo.jpg", "missing-heatmap.png", "missing-spectrum.png")
    output = tmp_path / "missing-images.pdf"
    make_pdf(result, str(output))
    assert output.is_file() and output.read_bytes().startswith(b"%PDF")
