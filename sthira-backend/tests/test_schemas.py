"""Tests for app/core/schemas.py (shared data shapes)."""
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.core.schemas import (
    AudioResult, CostEstimate, CostItem, CrackResult,
    InspectionResult, ScaleResult, Verdict,
)


def test_scale_result_without_marker():
    r = ScaleResult(marker_found=False)
    assert r.mm_per_px is None and r.confidence == 0


def test_severity_must_be_1_to_5():
    Verdict(label="x", severity=5, reason="y")
    with pytest.raises(ValidationError):
        Verdict(label="x", severity=6, reason="y")
    with pytest.raises(ValidationError):
        Verdict(label="x", severity=0, reason="y")


def test_audio_classification_only_allowed_values():
    AudioResult(dominant_hz=1500.0, classification="solid")
    with pytest.raises(ValidationError):
        AudioResult(dominant_hz=1500.0, classification="hollow")


def test_cost_estimate_holds_items():
    item = CostItem(description="d", unit="rmt", quantity=2, rate_rs=100, amount_rs=200)
    est = CostEstimate(items=[item], total_rs=200)
    assert est.total_rs == 200 and est.rates_are_placeholder is True


def test_full_inspection_result_round_trip():
    res = InspectionResult(
        inspection_id=1, building_id=1, building_name="Main Block", floor="2",
        location="Near staircase B", exposure_class="moderate",
        created_at=datetime(2026, 10, 24), status="completed",
        crack=CrackResult(max_width_mm=0.4, mean_width_mm=0.2, length_mm=300, angle_deg=45),
        health_score=60,
    )
    again = InspectionResult.model_validate_json(res.model_dump_json())
    assert again == res


def test_bad_exposure_class_rejected():
    with pytest.raises(ValidationError):
        InspectionResult(
            inspection_id=1, building_id=1, building_name="b", floor="1",
            location="l", exposure_class="extreme",
            created_at=datetime(2026, 10, 24), status="pending",
        )
