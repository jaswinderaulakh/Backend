"""
Try the marker + scale step on one photo.

Run from the project folder:
    python -m app.vision.demo path\\to\\photo.jpg
Optional: choose where the straightened photo goes:
    python -m app.vision.demo path\\to\\photo.jpg --out warped.png
"""

import argparse
import sys

from app.vision.scale import ScaleError, find_scale


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Find the marker in a photo and work out the scale.")
    parser.add_argument("photo", help="path to the photo (JPEG or PNG)")
    parser.add_argument("--out", help="where to save the straightened photo (default: next to the photo)")
    args = parser.parse_args(argv)

    try:
        result = find_scale(args.photo, warped_path=args.out)
    except ScaleError as err:
        print(f"Could not measure the scale: {err.message}")
        return 1

    print(f"mm per pixel   : {result.mm_per_px:.5f}")
    print(f"Confidence     : {result.confidence:.2f}  (0 = do not trust, 1 = fully trust)")
    print(f"Warped image   : {result.warped_image_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
