"""Tests for app/pipeline.py (the fake analysis)."""
import pytest

from app.core.config import get_rule, load_thresholds
from app.core.schemas import InspectionResult
from app.pipeline import run_pipeline


def make_files(folder, photo_size, wav_size):
    folder.mkdir(parents=True, exist_ok=True)
    photo, wav = folder / "photo.jpg", folder / "tap.wav"
    photo.write_bytes(b"\xff\xd8\xff" + b"0" * photo_size)
    wav.write_bytes(b"RIFF0000WAVE" + b"0" * wav_size)
    return photo, wav


def all_five_results(storage_env):
    results = []
    for i in range(5):  # file sizes 0..4 apart give each of the five fake cracks once
        photo, wav = make_files(storage_env / "storage" / "inspections" / str(i), i, 0)
        results.append(run_pipeline(photo, wav, "moderate"))
    return results


def test_returns_a_valid_inspection_result(storage_env):
    photo, wav = make_files(storage_env / "storage" / "inspections" / "1", 100, 50)
    result = run_pipeline(photo, wav, "mild")
    assert isinstance(result, InspectionResult)
    assert result.status == "completed" and result.exposure_class == "mild"
    assert result.inspection_id == 0 and result.building_name == ""  # filled in by the caller


def test_same_files_same_answer(storage_env):
    photo, wav = make_files(storage_env / "storage" / "inspections" / "1", 100, 50)
    a, b = run_pipeline(photo, wav, "mild"), run_pipeline(photo, wav, "mild")
    assert a.verdict == b.verdict and a.crack == b.crack


def test_all_five_verdicts_appear_and_match_the_rules(storage_env):
    results = all_five_results(storage_env)
    labels = {r.verdict.label for r in results}
    expected = {get_rule(i)["label"] for i in ("shear_risk", "void_risk", "plaster_spalling", "minor", "hairline")}
    assert labels == expected
    for r in results:
        rule_severity = next(x for x in [get_rule(i) for i in ("shear_risk", "void_risk", "plaster_spalling", "minor", "hairline")]
                             if x["label"] == r.verdict.label)["severity"]
        assert r.verdict.severity == rule_severity


def test_fake_numbers_agree_with_the_thresholds(storage_env):
    t = load_thresholds()
    for r in all_five_results(storage_env):
        if r.audio.classification == "void":
            assert r.audio.dominant_hz < t["audio"]["void_below_hz"]
        if r.audio.classification == "solid":
            assert r.audio.dominant_hz > t["audio"]["solid_above_hz"]
        assert r.health_score == t["health_score"]["severity_to_score"][r.verdict.severity]
        limit = t["is456_crack_limit_mm"][r.exposure_class]
        assert r.exceeds_is456_limit == (r.crack.max_width_mm > limit)


def test_exposure_class_changes_the_is456_flag(storage_env):
    photo, wav = make_files(storage_env / "storage" / "inspections" / "9", 3, 0)  # a 0.20 mm crack
    mild = run_pipeline(photo, wav, "mild")
    severe = run_pipeline(photo, wav, "severe")
    assert mild.exceeds_is456_limit is False
    assert severe.exceeds_is456_limit is True


def test_cost_estimate_adds_up_and_pdf_is_written(storage_env):
    for r in all_five_results(storage_env):
        assert r.cost.total_rs == round(sum(i.amount_rs for i in r.cost.items), 2)
        for item in r.cost.items:
            assert item.amount_rs == round(item.quantity * item.rate_rs, 2)
        pdf = storage_env / "storage" / r.cost.pdf_path
        assert pdf.read_bytes().startswith(b"%PDF")


def test_hairline_crack_needs_no_repair(storage_env):
    hairline = [r for r in all_five_results(storage_env) if r.verdict.label == get_rule("hairline")["label"]][0]
    assert hairline.cost.items == [] and hairline.cost.total_rs == 0


def test_result_paths_use_forward_slashes_and_stay_relative(storage_env):
    photo, wav = make_files(storage_env / "storage" / "inspections" / "1", 100, 50)
    r = run_pipeline(photo, wav, "mild")
    assert r.photo_path == "inspections/1/photo.jpg"
    assert r.cost.pdf_path == "inspections/1/report.pdf"
