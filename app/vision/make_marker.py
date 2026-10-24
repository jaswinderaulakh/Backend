"""
Make a printable STHIRA marker.

Run from the project folder:
    python -m app.vision.make_marker
Optional: choose the file name:
    python -m app.vision.make_marker --out my_marker.png

The marker's black square is the size set in config/thresholds.yaml
(marker.aruco_size_mm, 50 mm = 5 cm), with a white border around it.
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.vision.scale import (
    ARUCO_DICTIONARY_NAME,
    ARUCO_MARKER_ID,
    ScaleError,
    _default_thresholds_path,
    _load_marker_config,
)

PRINT_DPI = 300      # picture resolution for printing
BORDER_MM = 10.0     # white border around the black square (printing setting, not a threshold)
MM_PER_INCH = 25.4


def build_marker_image(marker_mm: float):
    """
    Returns (image, marker_px, pixels_per_metre).

    5 cm at 300 dpi is 590.55 pixels, which is not a whole number. So the black
    square gets the nearest whole number of pixels (591) and the PNG's "print
    size" is set so that those 591 pixels are exactly marker_mm wide on paper
    (about 300.2 dpi instead of 300). This keeps the printed size right, which is
    what the measurements depend on.
    """
    marker_px = int(round(marker_mm / MM_PER_INCH * PRINT_DPI))
    pixels_per_metre = int(round(marker_px / (marker_mm / 1000.0)))
    border_px = int(round(BORDER_MM / marker_mm * marker_px))

    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, ARUCO_DICTIONARY_NAME))
    square = cv2.aruco.generateImageMarker(dictionary, ARUCO_MARKER_ID, marker_px)
    total = marker_px + 2 * border_px
    canvas = np.full((total, total), 255, dtype=np.uint8)
    canvas[border_px:border_px + marker_px, border_px:border_px + marker_px] = square
    return canvas, marker_px, pixels_per_metre


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Make a printable STHIRA marker (PNG).")
    parser.add_argument("--out", default=None, help="file to save (default: sthira_marker_<size>mm.png)")
    args = parser.parse_args(argv)

    try:
        marker_mm = _load_marker_config(str(_default_thresholds_path()))["marker_mm"]
    except ScaleError as err:
        print(f"Could not make the marker: {err.message}")
        return 1

    image, marker_px, ppm = build_marker_image(marker_mm)
    size_text = f"{marker_mm:g}"
    out = Path(args.out) if args.out else Path(f"sthira_marker_{size_text}mm.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image).save(str(out), dpi=(ppm * 0.0254, ppm * 0.0254))

    total_mm = image.shape[0] / ppm * 1000
    print(f"Marker saved to: {out.resolve()}")
    print(f"Black square: {marker_mm:g} mm ({marker_mm / 10:g} cm) wide. Whole picture with white border: {total_mm:.0f} mm.")
    print()
    print("HOW TO PRINT")
    print("  1. Open the PNG and print it on plain white paper (matt paper is best, not glossy).")
    print("  2. Set the scale to 100% / 'Actual size'. Do NOT choose 'Fit to page' or 'Shrink to fit'.")
    print("  3. If the print dialog asks about margins, choose 'None' or 'Default', never 'Fit'.")
    print()
    print("CHECK THE PRINTED SIZE")
    print(f"  Hold a ruler across the BLACK square (not the white border).")
    print(f"  It must measure {marker_mm:g} mm ({marker_mm / 10:g} cm), within about 0.5 mm.")
    print("  If it is smaller or larger, the print was scaled: print again at 100%.")
    print("  A wrong printed size makes every crack measurement wrong by the same amount.")
    print()
    print("HOW TO USE")
    print("  Stick the marker flat on the wall right next to the crack, right way up (not sideways),")
    print("  with no folds or glare, and keep the whole marker in the photo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
