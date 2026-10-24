"""
Try the coin-tap analysis on one WAV file.

Run from the project folder:
    python -m app.audio.demo path\\to\\file.wav
Optional: choose where the spectrum picture goes:
    python -m app.audio.demo path\\to\\file.wav --out spectrum.png
"""

import argparse
import sys

from app.audio.analyze import AudioAnalysisError, analyze_tap


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Analyse a coin-tap WAV recording.")
    parser.add_argument("wav", help="path to the WAV file")
    parser.add_argument("--out", help="where to save the spectrum PNG (default: next to the WAV file)")
    args = parser.parse_args(argv)

    try:
        result = analyze_tap(args.wav, spectrum_path=args.out)
    except AudioAnalysisError as err:
        print(f"Could not analyse the recording: {err.message}")
        return 1

    print(f"Dominant frequency : {result.dominant_hz} Hz")
    print(f"Classification     : {result.classification}")
    print(f"Spectrum image     : {result.spectrum_image_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
