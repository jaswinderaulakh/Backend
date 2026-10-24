"""Compare truth-labelled local photo/WAV pairs with the real STHIRA pipeline."""
from __future__ import annotations

import argparse
import csv
import html
import shutil
import tempfile
import time
from pathlib import Path

from app.core.settings import PROJECT_ROOT
from app.pipeline import run_pipeline

FIELDS = ["photo", "wav", "true_width_mm", "measured_width_mm", "width_error_mm",
          "width_error_percent", "angle_deg", "tap_frequency_hz", "tap_class",
          "tap_class_expected", "verdict", "severity", "cost_rs", "time_seconds", "error"]


def _input_path(value: str, base: Path) -> Path:
    candidate = Path(value).expanduser()
    return candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()


def _expected_tap(value: str) -> str:
    text = value.strip().lower()
    if text in {"hollow", "void"}:
        return "void"
    if text == "solid":
        return "solid"
    if text == "uncertain":
        return "uncertain"
    return text


def _blank(row: dict) -> dict:
    return {key: "" for key in FIELDS} | {"photo": row.get("photo", ""), "wav": row.get("wav", ""),
                                           "tap_class_expected": row.get("tap_type", "")}


def run_batch(truth_csv: Path, output_dir: Path) -> list[dict]:
    truth_csv, output_dir = Path(truth_csv).resolve(), Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    with truth_csv.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = {"photo", "wav", "true_width_mm", "tap_type", "notes"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError("truth.csv is missing required columns: " + ", ".join(sorted(missing)))
        for index, row in enumerate(reader, start=1):
            result = _blank(row)
            start = time.perf_counter()
            try:
                photo = _input_path(row["photo"], truth_csv.parent)
                wav_text = (row.get("wav") or "").strip()
                wav = _input_path(wav_text, truth_csv.parent) if wav_text else None
                true_width = float(row["true_width_mm"])
                if true_width < 0:
                    raise ValueError("true_width_mm cannot be negative")
                if not photo.is_file():
                    raise FileNotFoundError(f"Photo not found: {photo}")
                if wav is not None and not wav.is_file():
                    raise FileNotFoundError(f"WAV file not found: {wav}")

                with tempfile.TemporaryDirectory(prefix=f"sthira_batch_{index}_", dir=output_dir) as temp:
                    work = Path(temp)
                    suffix = ".png" if photo.suffix.lower() == ".png" else ".jpg"
                    photo_copy = work / f"photo{suffix}"
                    shutil.copyfile(photo, photo_copy)
                    wav_copy = work / "tap.wav" if wav else None
                    if wav and wav_copy:
                        shutil.copyfile(wav, wav_copy)
                    inspection = run_pipeline(photo_copy, wav_copy, "moderate")

                result["true_width_mm"] = f"{true_width:.3f}"
                if inspection.crack:
                    measured = inspection.crack.max_width_mm
                    error = measured - true_width
                    result.update({
                        "measured_width_mm": f"{measured:.3f}",
                        "width_error_mm": f"{error:.3f}",
                        "width_error_percent": "" if true_width == 0 else f"{abs(error) / true_width * 100:.2f}",
                        "angle_deg": f"{inspection.crack.angle_deg:.2f}",
                    })
                if inspection.audio:
                    result["tap_frequency_hz"] = ("" if inspection.audio.dominant_hz is None
                                                   else f"{inspection.audio.dominant_hz:.1f}")
                    result["tap_class"] = inspection.audio.classification
                result["verdict"] = inspection.verdict.label if inspection.verdict else ""
                result["severity"] = inspection.verdict.severity if inspection.verdict else ""
                result["cost_rs"] = f"{inspection.cost.total_rs:.2f}" if inspection.cost else ""
                expected = _expected_tap(row.get("tap_type", ""))
                actual = result["tap_class"]
                if expected and actual and expected != actual:
                    result["error"] = f"Tap class mismatch: expected {expected}, measured {actual}"
                if inspection.status == "failed":
                    result["error"] = inspection.error_message or "Pipeline returned failed status"
            except Exception as exc:
                result["error"] = f"{type(exc).__name__}: {exc}"
            result["time_seconds"] = f"{time.perf_counter() - start:.3f}"
            results.append(result)

    csv_path = output_dir / "results.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(results)
    _write_html(output_dir / "results.html", results, truth_csv)
    return results


def _write_html(path: Path, rows: list[dict], truth_csv: Path) -> None:
    if rows:
        headings = "".join(f"<th>{html.escape(field.replace('_', ' ').title())}</th>" for field in FIELDS)
        body = "".join("<tr>" + "".join(f"<td>{html.escape(str(row.get(field, '')))}</td>" for field in FIELDS) + "</tr>"
                       for row in rows)
        table = f"<table><thead><tr>{headings}</tr></thead><tbody>{body}</tbody></table>"
        note = "Measurements below are only as representative as the truth-labelled files supplied."
    else:
        table = "<p>No labelled rows were found. No real-data measurements have been calculated.</p>"
        note = f"Add truth-labelled photo/WAV pairs to <code>{html.escape(str(truth_csv))}</code> and run this tool again."
    path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>STHIRA batch check</title>"
        "<style>body{font:14px Arial,sans-serif;margin:24px;color:#20343d}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #c8d5d9;padding:6px;text-align:left}th{background:#e8f0f3}"
        "td{max-width:360px;overflow-wrap:anywhere}</style></head><body>"
        "<h1>STHIRA batch check</h1><p>" + note + "</p>" + table + "</body></html>",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure photo/WAV pairs in tests/real_data/truth.csv.")
    parser.add_argument("truth_csv", nargs="?", type=Path, default=PROJECT_ROOT / "tests" / "real_data" / "truth.csv")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "tools" / "output")
    args = parser.parse_args()
    rows = run_batch(args.truth_csv, args.output_dir)
    print(f"Processed {len(rows)} labelled row(s).")
    print(f"CSV: {args.output_dir / 'results.csv'}")
    print(f"HTML: {args.output_dir / 'results.html'}")


if __name__ == "__main__":
    main()
