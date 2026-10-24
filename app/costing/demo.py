"""Generate one illustrative report for every configured verdict type."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.core.config import load_rules, load_thresholds
from app.core.schemas import AudioResult, CrackResult, InspectionResult
from app.core.settings import PROJECT_ROOT
from app.costing.estimate import estimate_cost
from app.costing.report import make_pdf
from app.rules.engine import decide_verdict


def _scenario(rule_id: str, thresholds: dict) -> tuple[CrackResult, AudioResult]:
    crack_cfg, audio_cfg = thresholds["crack"], thresholds["audio"]
    low, high = audio_cfg["void_below_hz"], audio_cfg["solid_above_hz"]
    middle = (low + high) / 2
    if rule_id == "shear_risk":
        crack = CrackResult(max_width_mm=float(crack_cfg["significant_above_mm"] + 0.1), mean_width_mm=0.2,
                            length_mm=1200, angle_deg=(crack_cfg["shear_angle_min_deg"] + crack_cfg["shear_angle_max_deg"]) / 2)
        hz = high + 200
    elif rule_id == "void_risk":
        crack = CrackResult(max_width_mm=float(crack_cfg["significant_above_mm"] + 0.1), mean_width_mm=0.2,
                            length_mm=900, angle_deg=0)
        hz = max(1, low - 100)
    elif rule_id == "plaster_spalling":
        crack = CrackResult(max_width_mm=float(crack_cfg["significant_above_mm"] + 0.1), mean_width_mm=0.2,
                            length_mm=700, angle_deg=90)
        hz = high + 200
    elif rule_id == "minor":
        crack = CrackResult(max_width_mm=(crack_cfg["hairline_below_mm"] + crack_cfg["significant_above_mm"]) / 2,
                            mean_width_mm=0.1, length_mm=600, angle_deg=90)
        hz = high + 200
    elif rule_id == "hairline":
        crack = CrackResult(max_width_mm=max(0, crack_cfg["hairline_below_mm"] / 2), mean_width_mm=0.02,
                            length_mm=350, angle_deg=90)
        hz = high + 200
    else:  # The configured fallback, for example uncertain tap frequency.
        crack = CrackResult(max_width_mm=float(crack_cfg["significant_above_mm"] + 0.1), mean_width_mm=0.2,
                            length_mm=800, angle_deg=0)
        hz = middle
    classification = "void" if hz < low else "solid" if hz > high else "uncertain"
    return crack, AudioResult(dominant_hz=float(hz), classification=classification)


def main() -> None:
    out_dir = PROJECT_ROOT / "demo_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    rules = load_rules()
    thresholds = load_thresholds()
    examples = [(rule["id"], rule["label"]) for rule in rules["rules"]]
    examples.append((rules["fallback"]["id"], rules["fallback"]["label"]))
    for rule_id, _ in examples:
        crack, audio = _scenario(rule_id, thresholds)
        verdict = decide_verdict(crack, audio, "moderate")
        stamp = datetime.now(timezone.utc)
        result = InspectionResult(inspection_id=0, building_id=0, building_name="Sample Campus Building",
                                  floor="Ground", location="North wall", exposure_class="moderate",
                                  created_at=stamp, completed_at=stamp, status="completed", crack=crack,
                                  audio=audio, verdict=verdict,
                                  exceeds_is456_limit=crack.max_width_mm > thresholds["is456_crack_limit_mm"]["moderate"])
        result.cost = estimate_cost(verdict, crack)
        safe_name = rule_id.replace("/", "_")
        path = out_dir / f"{safe_name}.pdf"
        make_pdf(result, str(path))
        print(f"Wrote {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
