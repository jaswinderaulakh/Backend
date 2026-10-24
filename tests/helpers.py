"""Generated test assets for real-pipeline end-to-end checks."""
from __future__ import annotations

import io
import wave

import cv2
import numpy as np


def make_marked_photo_bytes(*, with_marker: bool = True, with_crack: bool = True,
                            crack_width_px: int = 12, image_format: str = ".jpg") -> bytes:
    """Build a synthetic wall photo containing an optional 50 mm ArUco marker and crack."""
    width, height = 1600, 1200
    rng = np.random.default_rng(42)
    wall = np.empty((height, width, 3), np.float32)
    wall[:] = (195, 207, 213)
    wall += np.linspace(-4, 4, width, dtype=np.float32)[None, :, None]
    wall += rng.normal(0, 1.2, wall.shape).astype(np.float32)
    image = np.clip(wall, 0, 255).astype(np.uint8)

    if with_marker:
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        marker = cv2.aruco.generateImageMarker(dictionary, 0, 300)
        x, y, pad = 200, 400, 50
        image[y - pad:y + 300 + pad, x - pad:x + 300 + pad] = 255
        image[y:y + 300, x:x + 300] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    if with_crack:
        cv2.line(image, (720, 750), (1380, 750), (48, 48, 48), crack_width_px, cv2.LINE_8)
    ok, encoded = cv2.imencode(image_format, image, [cv2.IMWRITE_JPEG_QUALITY, 95] if image_format == ".jpg" else [])
    if not ok:
        raise RuntimeError("Could not encode generated test photo")
    return encoded.tobytes()


def make_tap_wav_bytes(frequency_hz: float = 1800, *, silent: bool = False) -> bytes:
    """Build a three-second 48 kHz mono PCM WAV with a fading sine-wave tap."""
    sample_rate = 48000
    count = sample_rate * 3
    samples = np.zeros(count, dtype=np.float64)
    if not silent:
        rng = np.random.default_rng(123)
        samples += rng.normal(0.0, 0.0005, count)
        duration = int(sample_rate * 0.15)
        t = np.arange(duration) / sample_rate
        burst = 0.6 * np.exp(-t / 0.01) * np.sin(2 * np.pi * frequency_hz * t)
        start = sample_rate
        samples[start:start + duration] += burst
    pcm = np.round(np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    return output.getvalue()
