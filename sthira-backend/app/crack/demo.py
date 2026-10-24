r"""
Try the crack measurement on one photo.

Usage (from the project folder):
    python -m app.crack.demo path\to\image.jpg 0.12
    python -m app.crack.demo path\to\image.jpg 0.12 --ignore 40 30 300 300

The second value is mm_per_px (millimetres covered by one pixel).
The photo should be the straightened ("warped") one from the scale step.
--ignore x y w h  skips a box (in pixels), for example the printed marker.
"""

import argparse
import sys

from app.crack.measure import CrackError, measure_crack_detailed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Measure a crack in a straightened photo.")
    parser.add_argument("image", help="path to the straightened photo")
    parser.add_argument("mm_per_px", help="millimetres per pixel, e.g. 0.12")
    parser.add_argument("--ignore", nargs=4, type=int, metavar=("X", "Y", "W", "H"),
                        help="box to skip, e.g. the marker")
    args = parser.parse_args(argv)

    try:
        scale = float(args.mm_per_px)
    except ValueError:
        print("Problem: mm_per_px must be a number, for example 0.12")
        return 1

    try:
        report = measure_crack_detailed(
            args.image, scale, ignore_region=tuple(args.ignore) if args.ignore else None
        )
    except CrackError as error:
        print("Problem:", error.message)
        return 1

    r = report.result
    print(f"Max width : {r.max_width_mm:.3f} mm")
    print(f"Mean width: {r.mean_width_mm:.3f} mm")
    print(f"Length    : {r.length_mm:.1f} mm")
    print(f"Angle     : {r.angle_deg:.1f} degrees (0 = horizontal, 90 = vertical)")
    print(f"Width reliable: {'yes' if report.width_is_reliable else 'NO'}")
    print(f"Note      : {report.message}")
    print(f"Heatmap   : {r.heatmap_path}")
    print(f"Mask      : {r.mask_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
