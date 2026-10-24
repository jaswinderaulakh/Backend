"""
FAKE analysis pipeline (Stage 1).

run_pipeline() pretends to analyse a photo and a coin-tap recording and returns
made-up but realistic numbers. Real modules will replace the fake parts one
stage at a time:
    Stage 2 audio, Stage 3 scale, Stage 4 crack, Stage 5 rules + cost + PDF.
Keep the function name and inputs the same, so nothing else has to change.

The result has placeholder values for who/where (inspection_id = 0, empty
building name, floor and location). The caller (inspection_service.py) fills
those in.

Fake behaviour: the file sizes pick one of five sample cracks, so the same
files always give the same answer. The picture files named in the result
(warped image, heatmap, mask, spectrum) are NOT created. Only report.pdf is.
"""
import os
import random
from pathlib import Path
from typing import Union

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.clock import utcnow
from app.core.config import get_rule, load_cpwd_rates, load_thresholds
from app.core.schemas import (AudioResult, CostEstimate, CostItem, CrackResult,
                              InspectionResult, ScaleResult, Verdict)
from app.core.storage import to_relative

# Made-up sample cracks. Each one is built to match one row of config/rules.yaml.
# (These are sample measurements, not thresholds.)
_SCENARIOS = [
    dict(rule="shear_risk", max_width_mm=0.45, length_mm=1450, angle_deg=47.0, dominant_hz=1650,
         repairs=["epoxy_injection_grouting", "polymer_mortar_plastering"],
         reason="The crack runs at about 47 degrees, which is the diagonal shear range, so it is flagged first whatever the tap sound says."),
    dict(rule="void_risk", max_width_mm=0.52, length_mm=980, angle_deg=12.0, dominant_hz=640,
         repairs=["epoxy_injection_grouting", "polymer_mortar_plastering"],
         reason="The crack is wider than 0.3 mm and the tap sound is low, which suggests a hollow area behind the surface."),
    dict(rule="plaster_spalling", max_width_mm=0.60, length_mm=620, angle_deg=85.0, dominant_hz=1700,
         repairs=["polymer_mortar_plastering"],
         reason="The crack is wide but the tap sound is high and firm, so only the plaster layer is damaged."),
    dict(rule="minor", max_width_mm=0.20, length_mm=850, angle_deg=80.0, dominant_hz=1650,
         repairs=["crack_sealing"],
         reason="A fine crack over solid concrete. Seal it and keep an eye on it."),
    dict(rule="hairline", max_width_mm=0.07, length_mm=400, angle_deg=90.0, dominant_hz=1800,
         repairs=[],
         reason="A very thin shrinkage crack over solid concrete. No action needed."),
]


def run_pipeline(photo_path: Union[str, Path], wav_path: Union[str, Path],
                 exposure_class: str) -> InspectionResult:
    photo_path, wav_path = Path(photo_path), Path(wav_path)
    seed = os.path.getsize(photo_path) + os.path.getsize(wav_path)
    rng = random.Random(seed)
    sc = _SCENARIOS[seed % len(_SCENARIOS)]
    out_dir = photo_path.parent

    def jitter() -> float:  # small +/-5% change so results do not look copy-pasted
        return rng.uniform(0.95, 1.05)

    max_width = round(sc["max_width_mm"] * jitter(), 2)
    scale = ScaleResult(
        marker_found=True,
        mm_per_px=round(rng.uniform(0.15, 0.25), 4),
        confidence=round(rng.uniform(0.85, 0.98), 2),
        warped_image_path=to_relative(out_dir / "warped.png"),
    )
    crack = CrackResult(
        max_width_mm=max_width,
        mean_width_mm=round(max_width * 0.5, 2),
        length_mm=round(sc["length_mm"] * jitter(), 1),
        angle_deg=round(sc["angle_deg"], 1),
        heatmap_path=to_relative(out_dir / "heatmap.png"),
        mask_path=to_relative(out_dir / "mask.png"),
    )
    hz = round(sc["dominant_hz"] * jitter(), 1)
    audio_limits = load_thresholds()["audio"]
    if hz < audio_limits["void_below_hz"]:
        classification = "void"
    elif hz > audio_limits["solid_above_hz"]:
        classification = "solid"
    else:
        classification = "uncertain"
    audio = AudioResult(dominant_hz=hz, classification=classification,
                        spectrum_image_path=to_relative(out_dir / "spectrum.png"))

    rule = get_rule(sc["rule"])
    verdict = Verdict(label=rule["label"], severity=rule["severity"], reason=sc["reason"])

    thresholds = load_thresholds()
    limit = thresholds["is456_crack_limit_mm"][exposure_class]
    health = float(thresholds["health_score"]["severity_to_score"][verdict.severity])

    now = utcnow()
    result = InspectionResult(
        inspection_id=0, building_id=0, building_name="", floor="", location="",
        exposure_class=exposure_class, created_at=now, completed_at=now, status="completed",
        photo_path=to_relative(photo_path), audio_path=to_relative(wav_path),
        scale=scale, crack=crack, audio=audio, verdict=verdict,
        exceeds_is456_limit=max_width > limit, health_score=health,
    )
    result.cost = _fake_cost(sc["repairs"], crack.length_mm, out_dir / "report.pdf", result)
    return result


def _fake_cost(repair_ids, length_mm, pdf_file: Path, result: InspectionResult) -> CostEstimate:
    rates = load_cpwd_rates()
    by_id = {item["id"]: item for item in rates["items"]}
    length_m = round(length_mm / 1000, 2)
    items = []
    for repair_id in repair_ids:
        rate = by_id[repair_id]
        quantity = length_m if rate["unit"] == "rmt" else round(length_m * 0.5, 2)  # fake: 0.5 m wide patch
        items.append(CostItem(description=rate["description"], unit=rate["unit"], quantity=quantity,
                              rate_rs=rate["rate_rs"], amount_rs=round(quantity * rate["rate_rs"], 2)))
    estimate = CostEstimate(items=items, total_rs=round(sum(i.amount_rs for i in items), 2),
                            pdf_path=to_relative(pdf_file),
                            rates_are_placeholder=bool(rates.get("is_placeholder", True)))
    _write_fake_pdf(pdf_file, result, estimate)
    return estimate


def _write_fake_pdf(path: Path, result: InspectionResult, estimate: CostEstimate) -> None:
    """A one-page sample PDF. Stage 5 replaces this with the real report."""
    pdf = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, y, "STHIRA Inspection Report - SAMPLE (FAKE DATA)")
    pdf.setFont("Helvetica", 11)
    lines = [
        f"Verdict: {result.verdict.label} (severity {result.verdict.severity} of 5)",
        f"Widest crack: {result.crack.max_width_mm} mm    Length: {result.crack.length_mm} mm    Angle: {result.crack.angle_deg} deg",
        f"Tap sound: {result.audio.dominant_hz} Hz ({result.audio.classification})",
        f"Health score: {result.health_score} / 100",
        "",
        "Repair estimate:",
    ]
    for item in estimate.items:
        lines.append(f"  {item.description}: {item.quantity} {item.unit} x Rs. {item.rate_rs} = Rs. {item.amount_rs}")
    if not estimate.items:
        lines.append("  No repair needed.")
    lines.append(f"Total: Rs. {estimate.total_rs}")
    if estimate.rates_are_placeholder:
        lines += ["", "WARNING: rates are PLACEHOLDERS, not real CPWD DSR values."]
    for line in lines:
        y -= 22
        pdf.drawString(50, y, line)
    pdf.save()
