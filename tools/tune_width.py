"""Compare measured widths to labelled truth and suggest only; do not tune config."""
from __future__ import annotations

import argparse
import csv
import shutil
import tempfile
from pathlib import Path

from app.core.settings import PROJECT_ROOT
from app.crack.measure import CrackError, NoCrackFoundError, measure_crack_detailed
from app.pipeline import _warped_marker_box
from app.vision.scale import ScaleError, find_scale

FIELDS = ["photo", "true_width_mm", "measured_width_mm", "signed_error_mm", "absolute_error_percent",
          "angle_deg", "smallest_trusted_width_mm", "error"]


def run_width_tuning(truth_csv: Path, output_dir: Path) -> dict:
    truth_csv, output_dir = Path(truth_csv).resolve(), Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rows_out = []
    with truth_csv.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"photo", "wav", "true_width_mm", "tap_type", "notes"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError("truth.csv is missing required columns: " + ", ".join(sorted(missing)))
        for index, row in enumerate(reader, start=1):
            output = {field: "" for field in FIELDS}
            output["photo"] = row.get("photo", "")
            try:
                true_width = float(row["true_width_mm"])
                if true_width < 0:
                    raise ValueError("true_width_mm cannot be negative")
                photo = Path(row["photo"]).expanduser()
                if not photo.is_absolute():
                    photo = truth_csv.parent / photo
                if not photo.is_file():
                    raise FileNotFoundError(f"Photo not found: {photo}")
                with tempfile.TemporaryDirectory(prefix=f"sthira_width_{index}_", dir=output_dir) as temp:
                    work = Path(temp)
                    suffix = ".png" if photo.suffix.lower() == ".png" else ".jpg"
                    copied = work / f"photo{suffix}"
                    shutil.copyfile(photo, copied)
                    warped = work / "warped.png"
                    scale = find_scale(copied, warped_path=warped)
                    ignore = _warped_marker_box(warped)
                    try:
                        report = measure_crack_detailed(str(warped), scale.mm_per_px, ignore_region=ignore,
                                                        mask_path=str(work / "mask.png"),
                                                        heatmap_path=str(work / "heatmap.png"))
                        measured = report.result.max_width_mm
                        angle = report.result.angle_deg
                        trusted = report.min_trusted_width_mm
                    except NoCrackFoundError:
                        measured, angle = 0.0, ""
                        trusted = None
                signed_error = measured - true_width
                output.update({
                    "true_width_mm": f"{true_width:.3f}",
                    "measured_width_mm": f"{measured:.3f}",
                    "signed_error_mm": f"{signed_error:.3f}",
                    "absolute_error_percent": "" if true_width == 0 else f"{abs(signed_error) / true_width * 100:.2f}",
                    "angle_deg": "" if angle == "" else f"{angle:.2f}",
                    "smallest_trusted_width_mm": "" if trusted is None else f"{trusted:.3f}",
                })
            except (ScaleError, CrackError, OSError, ValueError) as exc:
                output["error"] = f"{type(exc).__name__}: {exc}"
            rows_out.append(output)

    csv_path = output_dir / "width_tuning.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows_out)

    measured_rows = [row for row in rows_out if row["signed_error_mm"]]
    biases = [float(row["signed_error_mm"]) for row in measured_rows]
    trusted_limits = [float(row["smallest_trusted_width_mm"]) for row in measured_rows
                      if row["smallest_trusted_width_mm"]]
    average_bias = sum(biases) / len(biases) if biases else None
    smallest_trusted = min(trusted_limits) if trusted_limits else None
    if average_bias is None:
        print("No usable labelled width measurements were available; no width accuracy summary was calculated.")
    else:
        print(f"Average signed width bias (measured minus true): {average_bias:+.3f} mm across {len(biases)} usable pair(s).")
        if smallest_trusted is not None:
            print(f"Smallest scale-based trusted width in these photos: {smallest_trusted:.3f} mm.")
            print("This is a resolution warning, not proof that smaller cracks are absent.")
        print("Suggestion only: review camera distance and width thresholds after collecting more labelled photos.")
    print(f"Results saved to: {csv_path}")
    print("No threshold settings were changed.")
    return {"rows": rows_out, "average_bias_mm": average_bias,
            "smallest_trusted_width_mm": smallest_trusted, "csv_path": csv_path}


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare crack widths with truth-labelled photos; does not change config.")
    parser.add_argument("truth_csv", nargs="?", type=Path, default=PROJECT_ROOT / "tests" / "real_data" / "truth.csv")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "tools" / "output")
    args = parser.parse_args()
    run_width_tuning(args.truth_csv, args.output_dir)


if __name__ == "__main__":
    main()
