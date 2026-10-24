"""Inspect labelled tap recordings and suggest, but never apply, audio limits."""
from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

from matplotlib.figure import Figure

from app.audio.analyze import AudioAnalysisError, analyze_tap
from app.core.config import load_thresholds
from app.core.settings import PROJECT_ROOT


def _expected_class(value: str) -> str:
    text = value.strip().lower()
    if text in {"hollow", "void"}:
        return "hollow"
    if text == "solid":
        return "solid"
    return text


def _suggest(hollow: list[float], solid: list[float]) -> tuple[float | None, float | None, str]:
    if not hollow or not solid:
        return None, None, "Need at least one successful hollow/void and one solid recording to suggest limits."
    high_hollow, low_solid = max(hollow), min(solid)
    if high_hollow < low_solid:
        gap = low_solid - high_hollow
        return high_hollow + gap * 0.25, low_solid - gap * 0.25, "The labelled examples have a non-overlapping frequency gap."
    return statistics.median(hollow), statistics.median(solid), (
        "The labelled classes overlap. These medians are only exploratory; keep a wide uncertain band "
        "and collect more recordings before changing any limit."
    )


def run_audio_tuning(truth_csv: Path, output_dir: Path) -> dict:
    truth_csv, output_dir = Path(truth_csv).resolve(), Path(output_dir).resolve()
    spectra = output_dir / "audio_spectra"
    spectra.mkdir(parents=True, exist_ok=True)
    with truth_csv.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"photo", "wav", "true_width_mm", "tap_type", "notes"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError("truth.csv is missing required columns: " + ", ".join(sorted(missing)))
        rows = list(reader)

    counts = {"hollow": 0, "solid": 0}
    readings = {"hollow": [], "solid": []}
    for index, row in enumerate(rows, start=1):
        expected = _expected_class(row.get("tap_type", ""))
        if expected in counts:
            counts[expected] += 1
        wav_name = (row.get("wav") or "").strip()
        if not wav_name:
            print(f"{index}. {row.get('photo', '')}: no WAV path; skipped")
            continue
        wav_path = Path(wav_name).expanduser()
        if not wav_path.is_absolute():
            wav_path = truth_csv.parent / wav_path
        try:
            output_spectrum = spectra / f"recording_{index:04d}_spectrum.png"
            result = analyze_tap(wav_path, spectrum_path=output_spectrum)
            print(f"{index}. {wav_path.name}: {result.dominant_hz:.1f} Hz; "
                  f"measured {result.classification}; expected {row.get('tap_type', '')}")
            if expected in readings:
                readings[expected].append(result.dominant_hz)
        except (AudioAnalysisError, OSError) as exc:
            print(f"{index}. {wav_path.name}: could not analyse ({exc})")

    for label, count in counts.items():
        if count < 5:
            print(f"Warning: only {count} {label} recording(s); collect at least 5 for a useful first comparison.")

    figure = Figure(figsize=(7.2, 4.2), dpi=120)
    axis = figure.add_subplot(111)
    series = [readings["hollow"], readings["solid"]]
    if any(series):
        axis.boxplot(series, tick_labels=["Hollow / void", "Solid"], showmeans=True)
        for xpos, values in enumerate(series, start=1):
            if values:
                axis.scatter([xpos] * len(values), values, s=24, alpha=0.7)
    else:
        axis.text(0.5, 0.5, "No labelled audio readings to plot", ha="center", va="center")
        axis.set_xticks([])
    axis.set_ylabel("Dominant tap frequency (Hz)")
    axis.set_title("Labelled hollow versus solid tap recordings")
    figure.tight_layout()
    plot_path = output_dir / "audio_tuning.png"
    figure.savefig(str(plot_path), format="png")

    suggested_void, suggested_solid, message = _suggest(readings["hollow"], readings["solid"])
    current = load_thresholds()["audio"]
    print(f"Current config (unchanged): void below {current['void_below_hz']:g} Hz; "
          f"solid above {current['solid_above_hz']:g} Hz.")
    if suggested_void is not None:
        print(f"Suggested only: void below about {suggested_void:.1f} Hz; "
              f"solid above about {suggested_solid:.1f} Hz.")
    print(message)
    print(f"Plot saved to: {plot_path}")
    print("No threshold settings were changed.")
    return {"counts": counts, "readings": readings, "suggested_void_below_hz": suggested_void,
            "suggested_solid_above_hz": suggested_solid, "plot_path": plot_path}


def main() -> None:
    parser = argparse.ArgumentParser(description="Print and plot labelled tap frequencies; never changes config.")
    parser.add_argument("truth_csv", nargs="?", type=Path, default=PROJECT_ROOT / "tests" / "real_data" / "truth.csv")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "tools" / "output")
    args = parser.parse_args()
    run_audio_tuning(args.truth_csv, args.output_dir)


if __name__ == "__main__":
    main()
