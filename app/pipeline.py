"""Real STHIRA photo-and-tap inspection pipeline."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Union

import cv2

from app.audio.analyze import AudioAnalysisError, analyze_tap
from app.core.clock import utcnow
from app.core.config import get_rule, load_rules, load_thresholds
from app.core.schemas import (AudioResult, CostEstimate, CrackResult, InspectionResult,
                              ScaleResult, Verdict)
from app.core.storage import to_relative
from app.costing.estimate import estimate_cost
from app.costing.report import make_pdf
from app.crack.measure import (IGNORE_MARGIN_PX, NoCrackFoundError, measure_crack)
from app.rules.engine import decide_verdict
from app.vision.scale import (MarkerNotFoundError, ScaleError, _detect, _detect_id_card,
                              find_scale, load_photo)

PathLike = Union[str, Path]


def _warped_reference_box(warped_path: Path, reference_type: str | None) -> tuple[int, int, int, int]:
    """Detect the calibration reference in the warped image and return its ignore box."""
    bgr = load_photo(warped_path)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    if reference_type == "id_card":
        corners = _detect_id_card(gray)
    else:
        corners, _other_markers = _detect(gray)
    if corners is None:
        raise ScaleError("The scale reference area could not be isolated. Retake the photo with the full marker/card visible.")
    height, width = gray.shape[:2]
    x0 = max(0, int(corners[:, 0].min()) - IGNORE_MARGIN_PX)
    y0 = max(0, int(corners[:, 1].min()) - IGNORE_MARGIN_PX)
    x1 = min(width, int(corners[:, 0].max()) + IGNORE_MARGIN_PX + 1)
    y1 = min(height, int(corners[:, 1].max()) + IGNORE_MARGIN_PX + 1)
    return x0, y0, x1 - x0, y1 - y0


def _warped_marker_box(warped_path: Path) -> tuple[int, int, int, int]:
    """Backward-compatible marker-only wrapper used by the tuning scripts."""
    return _warped_reference_box(warped_path, "aruco")


def _failed(photo_path: Path, wav_path: Path | None, exposure_class: str, message: str) -> InspectionResult:
    now = utcnow()
    return InspectionResult(
        inspection_id=0, building_id=0, building_name="", floor="", location="",
        exposure_class=exposure_class, created_at=now, completed_at=now,
        status="failed", error_message=message,
        photo_path=to_relative(photo_path), audio_path=to_relative(wav_path) if wav_path else None,
        scale=ScaleResult(marker_found=False),
    )


def run_pipeline(photo_path: PathLike, wav_path: PathLike | None,
                 exposure_class: str) -> InspectionResult:
    """Process saved upload files and build their inspection result and PDF."""
    photo_path = Path(photo_path)
    wav_path = Path(wav_path) if wav_path else None
    out_dir = photo_path.parent
    warped_path = out_dir / "warped.png"

    try:
        scale = find_scale(photo_path, warped_path=warped_path)
    except MarkerNotFoundError:
        return _failed(photo_path, wav_path, exposure_class,
                       "Marker not visible, please retake the photo.")

    if scale.mm_per_px is None or not scale.warped_image_path:
        return _failed(photo_path, wav_path, exposure_class,
                       "No usable scale reference was found. Include the full 6x9 cm card or STHIRA marker.")

    warped_path = Path(scale.warped_image_path)
    marker_box = _warped_reference_box(warped_path, scale.reference_type)
    no_crack = False
    try:
        crack = measure_crack(
            str(warped_path), scale.mm_per_px, ignore_region=marker_box,
            mask_path=str(out_dir / "mask.png"), heatmap_path=str(out_dir / "heatmap.png"),
        )
    except NoCrackFoundError:
        no_crack = True
        crack = CrackResult(max_width_mm=0, mean_width_mm=0, length_mm=0, angle_deg=0)

    audio_problem: str | None = None
    if wav_path is None or not wav_path.is_file():
        audio_problem = "The tap recording was not provided."
        audio = AudioResult(dominant_hz=None, classification="uncertain")
    else:
        try:
            audio = analyze_tap(wav_path, spectrum_path=out_dir / "spectrum.png")
        except AudioAnalysisError as exc:
            audio_problem = exc.message
            audio = AudioResult(dominant_hz=None, classification="uncertain")

    thresholds = load_thresholds()
    limit = float(thresholds["is456_crack_limit_mm"][exposure_class])
    if no_crack:
        hairline_rule = get_rule("hairline")
        verdict = Verdict(
            label="No crack detected",
            severity=hairline_rule["severity"],
            reason=(f"No crack was detected in the photo. The {exposure_class} exposure "
                    f"IS 456 crack-width limit is {limit:g} mm; no crack width was measurable."),
        )
    elif audio_problem:
        fallback = load_rules()["fallback"]
        verdict = Verdict(
            label="Photo-only screening complete",
            severity=fallback["severity"],
            reason=(f"The photo-only screening completed; the optional tap result was not used: {audio_problem} "
                    f"The image-derived maximum width is {crack.max_width_mm:g} mm and "
                    f"{'exceeds' if crack.max_width_mm > limit else 'does not exceed'} the configured "
                    f"{exposure_class} exposure comparison of {limit:g} mm. Subsurface condition and crack "
                    "depth were not measured. This screening is not a structural diagnosis."),
        )
    else:
        verdict = decide_verdict(crack, audio, exposure_class)

    health_scores = thresholds["health_score"]["severity_to_score"]
    health_score = float(health_scores.get(verdict.severity, health_scores.get(str(verdict.severity))))
    result = InspectionResult(
        inspection_id=0, building_id=0, building_name="", floor="", location="",
        exposure_class=exposure_class, created_at=utcnow(), completed_at=utcnow(),
        status="completed", error_message="No crack detected." if no_crack else None,
        photo_path=to_relative(photo_path), audio_path=to_relative(wav_path) if wav_path else None,
        scale=scale.model_copy(update={"warped_image_path": to_relative(warped_path)}),
        crack=crack.model_copy(update={
            "mask_path": to_relative(crack.mask_path) if crack.mask_path else None,
            "heatmap_path": to_relative(crack.heatmap_path) if crack.heatmap_path else None,
        }),
        audio=audio.model_copy(update={
            "spectrum_image_path": to_relative(audio.spectrum_image_path) if audio.spectrum_image_path else None,
        }),
        verdict=verdict, exceeds_is456_limit=crack.max_width_mm > limit,
        health_score=health_score,
    )

    estimate = estimate_cost(verdict, crack)
    report_path = out_dir / "report.pdf"
    result.cost = estimate.model_copy(update={"pdf_path": to_relative(report_path)})
    make_pdf(result, str(report_path))
    return result
