"""Run the real analysis pipeline on one local photo and optional WAV file."""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.core.storage import storage_root
from app.pipeline import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyse one STHIRA wall photo and optional tap recording.")
    parser.add_argument("photo", help="Path to a JPEG or PNG photo with the STHIRA ArUco marker")
    parser.add_argument("wav", nargs="?", help="Optional coin-tap WAV file")
    parser.add_argument("--exposure", required=True, choices=("mild", "moderate", "severe"),
                        help="Concrete exposure class")
    args = parser.parse_args()

    photo = Path(args.photo).expanduser().resolve()
    wav = Path(args.wav).expanduser().resolve() if args.wav else None
    if not photo.is_file():
        parser.error(f"Photo file not found: {photo}")
    if wav is not None and not wav.is_file():
        parser.error(f"WAV file not found: {wav}")

    safe_folder = storage_root() / "one_off" / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    safe_folder.mkdir(parents=True, exist_ok=True)
    suffix = ".png" if photo.suffix.lower() == ".png" else ".jpg"
    saved_photo = safe_folder / f"photo{suffix}"
    shutil.copyfile(photo, saved_photo)
    saved_wav = safe_folder / "tap.wav" if wav else None
    if wav and saved_wav:
        shutil.copyfile(wav, saved_wav)

    result = run_pipeline(saved_photo, saved_wav, args.exposure)
    if result.status == "failed":
        print(f"Status: failed\nReason: {result.error_message}")
        return 1

    print(f"Status: {result.status}")
    if result.crack:
        print(f"Crack: widest {result.crack.max_width_mm:.2f} mm; "
              f"average {result.crack.mean_width_mm:.2f} mm; "
              f"length {result.crack.length_mm:.1f} mm; angle {result.crack.angle_deg:.1f} degrees")
    if result.audio:
        frequency = "unavailable" if result.audio.dominant_hz is None else f"{result.audio.dominant_hz:.1f} Hz"
        print(f"Tap: {frequency} ({result.audio.classification})")
    if result.verdict:
        print(f"Verdict: {result.verdict.label} (severity {result.verdict.severity}/5)")
        print(f"Reason: {result.verdict.reason}")
    if result.cost:
        print(f"Estimated cost: Rs. {result.cost.total_rs:,.2f}"
              f"{' (placeholder rates)' if result.cost.rates_are_placeholder else ''}")
        if result.cost.pdf_path:
            print(f"PDF report: {storage_root() / result.cost.pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
