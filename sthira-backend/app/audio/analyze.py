"""
Coin-tap sound analysis (Stage 2).

Main function:  analyze_tap(wav_path) -> AudioResult

What it does, in order:
  1. Loads the WAV (mono or stereo; 8/16/24/32-bit or float).
  2. Converts to mono and resamples to the expected sample rate (48 kHz).
  3. Applies the high-pass filter (removes speech and rumble).
  4. Finds the loudest tap and takes a short window around it.
  5. Runs an FFT on that window and finds the dominant frequency.
  6. Classifies it as "void", "solid" or "uncertain".
  7. Saves a picture of the spectrum (PNG).

All the important numbers (48 kHz, 600 Hz, 50 ms, 900 Hz, 1400 Hz) are read
from config/thresholds.yaml. They are NOT typed in this file.
"""

from __future__ import annotations

import math
import wave
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np
import yaml
from scipy import signal
from scipy.io import wavfile

from app.core.schemas import AudioResult

PathLike = Union[str, Path]

# --------------------------------------------------------------------------
# Technical settings for the checks below.
# These are NOT in config/thresholds.yaml (and I was told not to change that
# file), so they live here as clearly named constants. They are about sound
# QUALITY (is the recording usable?), not about concrete health.
# Suggestion for later: move them into config/thresholds.yaml.
# --------------------------------------------------------------------------
SILENCE_LEVEL = 1e-4          # peak below this (full scale = 1.0) counts as silence
CLIP_LEVEL = 0.999            # a sample this close to full scale is "at the limit"
CLIP_MIN_RUN = 3              # this many limit samples in a row = clipped audio
PEAK_TO_TYPICAL_MIN = 12.0    # tap peak must be this many times the typical background level
FILTER_ORDER = 4              # steepness of the high-pass filter
EDGE_GUARD_MS = 20            # the filter makes a fake blip at the very start/end of a file, so no tap is searched there
FFT_ZERO_PAD_FACTOR = 8       # zero-padding makes the frequency reading smoother
SPECTRUM_PLOT_MAX_HZ = 6000   # right edge of the spectrum picture


class AudioAnalysisError(Exception):
    """A problem with the recording. The message is plain English and safe to show a user."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ------------------------------------------------------------------ config
def _default_thresholds_path() -> Path:
    # app/audio/analyze.py -> project root is two folders up from "app"
    return Path(__file__).resolve().parents[2] / "config" / "thresholds.yaml"


@lru_cache(maxsize=8)
def _load_audio_config(path_str: str) -> dict:
    path = Path(path_str)
    if not path.is_file():
        raise AudioAnalysisError(f"Settings file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        audio = data["audio"]
        cfg = {
            "sample_rate": int(audio["expected_sample_rate_hz"]),
            "highpass_hz": float(audio["highpass_hz"]),
            "window_ms": float(audio["window_ms"]),
            "void_below_hz": float(audio["void_below_hz"]),
            "solid_above_hz": float(audio["solid_above_hz"]),
        }
    except (KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise AudioAnalysisError(
            f"The audio settings in {path.name} are missing or not valid ({exc})."
        ) from exc
    return cfg


# ------------------------------------------------------------------ loading
def _read_24bit_wav(path: Path) -> Tuple[int, np.ndarray]:
    """Fallback reader for 24-bit PCM files. Returns (sample_rate, float array in -1..1)."""
    with wave.open(str(path), "rb") as w:
        channels = w.getnchannels()
        width = w.getsampwidth()
        rate = w.getframerate()
        raw = w.readframes(w.getnframes())
    if width != 3:
        raise AudioAnalysisError("This WAV format is not supported. Please record 16-bit or 24-bit audio.")
    n = len(raw) // 3
    b = np.frombuffer(raw[: n * 3], dtype=np.uint8).reshape(-1, 3).astype(np.int32)
    ints = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
    ints = np.where(ints >= 1 << 23, ints - (1 << 24), ints)
    data = ints.astype(np.float64) / float(1 << 23)
    if channels > 1:
        data = data[: (len(data) // channels) * channels].reshape(-1, channels)
    return rate, data


def _to_float(data: np.ndarray) -> np.ndarray:
    """Scale any WAV sample type to floats where full scale is 1.0."""
    if data.dtype == np.uint8:
        return (data.astype(np.float64) - 128.0) / 128.0
    if data.dtype == np.int16:
        return data.astype(np.float64) / 32768.0
    if data.dtype == np.int32:
        return data.astype(np.float64) / 2147483648.0
    if np.issubdtype(data.dtype, np.floating):
        return data.astype(np.float64)
    raise AudioAnalysisError("This WAV format is not supported. Please record 16-bit or 24-bit audio.")


def _load_wav(path: Path) -> Tuple[int, np.ndarray]:
    """Return (sample_rate, floats) with shape (n,) or (n, channels)."""
    if not path.is_file():
        raise AudioAnalysisError(f"Audio file not found: {path}")
    try:
        rate, data = wavfile.read(str(path))
        return rate, _to_float(data)
    except AudioAnalysisError:
        raise
    except Exception:
        pass  # try the 24-bit fallback before giving up
    try:
        return _read_24bit_wav(path)
    except AudioAnalysisError:
        raise
    except Exception as exc:
        raise AudioAnalysisError(
            "The file could not be read as a WAV recording. Please record the tap again and upload a WAV file."
        ) from exc


# ------------------------------------------------------------------ checks
def _has_clipping(samples: np.ndarray) -> bool:
    """True if the recording hits the maximum level for several samples in a row."""
    at_limit = np.abs(samples) >= CLIP_LEVEL
    if at_limit.ndim == 2:
        at_limit = at_limit.any(axis=1)
    if at_limit.sum() < CLIP_MIN_RUN:
        return False
    runs = np.convolve(at_limit.astype(np.int32), np.ones(CLIP_MIN_RUN, dtype=np.int32), mode="valid")
    return bool((runs >= CLIP_MIN_RUN).any())


def _refine_peak(spectrum: np.ndarray, k: int) -> float:
    """Fractional bin position of the spectrum peak (parabolic interpolation)."""
    if k <= 0 or k >= len(spectrum) - 1:
        return float(k)
    a, b, c = spectrum[k - 1], spectrum[k], spectrum[k + 1]
    denom = a - 2 * b + c
    if denom == 0:
        return float(k)
    return float(k + 0.5 * (a - c) / denom)


# ------------------------------------------------------------------ picture
def _save_spectrum_image(freqs, magnitude, dominant_hz, classification, cfg, out_path: Path) -> None:
    from matplotlib.figure import Figure  # no pyplot: safe inside a web server

    fig = Figure(figsize=(7, 3.6), dpi=100)
    ax = fig.add_subplot(111)
    top = min(SPECTRUM_PLOT_MAX_HZ, cfg["sample_rate"] / 2)
    mask = freqs <= top
    peak = float(magnitude.max()) or 1.0
    ax.plot(freqs[mask], magnitude[mask] / peak, linewidth=1.2, color="#1f5fa8")
    ax.axvline(cfg["void_below_hz"], color="#c0392b", linestyle="--", linewidth=1,
               label=f"void below {cfg['void_below_hz']:.0f} Hz")
    ax.axvline(cfg["solid_above_hz"], color="#2e8b57", linestyle="--", linewidth=1,
               label=f"solid above {cfg['solid_above_hz']:.0f} Hz")
    ax.axvline(dominant_hz, color="black", linewidth=1.2,
               label=f"tap: {dominant_hz:.0f} Hz ({classification})")
    ax.set_xlim(0, top)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Relative loudness")
    ax.set_title("Coin-tap spectrum")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fig.savefig(str(out_path), format="png")
    except OSError as exc:
        raise AudioAnalysisError(f"The spectrum picture could not be saved to {out_path}.") from exc


# ------------------------------------------------------------------ main
def analyze_tap(
    wav_path: PathLike,
    spectrum_path: Optional[PathLike] = None,
    thresholds_path: Optional[PathLike] = None,
) -> AudioResult:
    """
    Analyse one coin-tap recording.

    wav_path        the WAV file to analyse
    spectrum_path   where to save the spectrum PNG. If left out, it is saved
                    next to the WAV file as "<name>_spectrum.png".
    thresholds_path only for tests: use a different thresholds.yaml

    Raises AudioAnalysisError (with a plain-English message) if the recording
    cannot be used.
    """
    wav_path = Path(wav_path)
    cfg = _load_audio_config(str(Path(thresholds_path) if thresholds_path else _default_thresholds_path()))

    # 1. Load
    rate, data = _load_wav(wav_path)
    if data.size == 0:
        raise AudioAnalysisError("The recording is empty. Please record the coin tap again.")
    if not np.all(np.isfinite(data)):
        raise AudioAnalysisError("The recording is damaged. Please record the coin tap again.")
    if rate <= 0:
        raise AudioAnalysisError("The recording is damaged (no sample rate). Please record it again.")

    # 2. Silence and clipping (checked on the original, before any processing)
    if float(np.max(np.abs(data))) < SILENCE_LEVEL:
        raise AudioAnalysisError("The recording is silent. Please tap the wall closer to the phone and record again.")
    if _has_clipping(data):
        raise AudioAnalysisError(
            "The recording is too loud and the sound is distorted (clipped). "
            "Please tap more gently or hold the phone a little further away, then record again."
        )

    # 3. Mono, then the expected sample rate
    mono = data.mean(axis=1) if data.ndim == 2 else data
    target = cfg["sample_rate"]
    if rate != target:
        g = math.gcd(int(rate), int(target))
        mono = signal.resample_poly(mono, target // g, int(rate) // g)
    sr = target

    # 4. Length check (must fit at least one analysis window)
    window_len = int(round(sr * cfg["window_ms"] / 1000.0))
    if window_len < 4:
        raise AudioAnalysisError("The analysis window in the settings is too small to use.")
    if mono.size < window_len:
        raise AudioAnalysisError(
            f"The recording is too short ({mono.size / sr * 1000:.0f} ms). "
            f"It must be at least {cfg['window_ms']:.0f} ms long, and a normal recording is about 3 seconds."
        )

    # 5. High-pass filter (zero-phase, so the tap does not shift in time)
    nyquist = sr / 2.0
    if not 0 < cfg["highpass_hz"] < nyquist:
        raise AudioAnalysisError("The high-pass setting is not valid for this sample rate.")
    sos = signal.butter(FILTER_ORDER, cfg["highpass_hz"] / nyquist, btype="highpass", output="sos")
    try:
        filtered = signal.sosfiltfilt(sos, mono)
    except ValueError as exc:
        raise AudioAnalysisError("The recording is too short to filter. Please record the tap again.") from exc

    # 6. Find the tap
    level = np.abs(filtered)
    guard = int(round(sr * EDGE_GUARD_MS / 1000.0))
    if level.size > 2 * guard + window_len:
        level[:guard] = 0.0
        level[-guard:] = 0.0
    peak_idx = int(np.argmax(level))
    peak_val = float(level[peak_idx])
    if peak_val < SILENCE_LEVEL:
        raise AudioAnalysisError(
            "No tap was heard. The recording only has low rumble or hum. Please tap the wall firmly and record again."
        )
    typical = float(np.median(level))
    if typical > 0 and peak_val / typical < PEAK_TO_TYPICAL_MIN:
        raise AudioAnalysisError(
            "No clear tap was found. The recording is too noisy or the tap is too soft. "
            "Please move away from noise and tap the wall firmly once."
        )

    # 7. 50 ms window around the tap (slid inward if the tap is near an edge)
    start = peak_idx - window_len // 2
    start = max(0, min(start, filtered.size - window_len))
    segment = filtered[start:start + window_len] * np.hanning(window_len)

    # 8. FFT and dominant frequency
    n_fft = 1 << int(math.ceil(math.log2(window_len * FFT_ZERO_PAD_FACTOR)))
    spectrum = np.abs(np.fft.rfft(segment, n=n_fft))
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)
    spectrum[0] = 0.0  # ignore the DC bin
    k = int(np.argmax(spectrum))
    if spectrum[k] <= 0:
        raise AudioAnalysisError("No clear tap was found in the recording. Please record again.")
    dominant_hz = float(_refine_peak(spectrum, k) * sr / n_fft)

    # 9. Classify using the limits from the config file
    if dominant_hz < cfg["void_below_hz"]:
        classification = "void"
    elif dominant_hz > cfg["solid_above_hz"]:
        classification = "solid"
    else:
        classification = "uncertain"

    # 10. Save the picture
    out = Path(spectrum_path) if spectrum_path else wav_path.with_name(wav_path.stem + "_spectrum.png")
    _save_spectrum_image(freqs, spectrum, dominant_hz, classification, cfg, out)

    return AudioResult(
        dominant_hz=round(dominant_hz, 1),
        classification=classification,
        spectrum_image_path=str(out),
    )
