"""
Tests for the coin-tap audio module (app/audio).

No real recordings are used. Every test sound is made with code:
a short "tap" is a fading sine wave (like a coin hitting a wall) plus a
little background noise.
"""

import wave
from pathlib import Path

import numpy as np
import pytest
import yaml
from scipy.io import wavfile

from app.audio.analyze import AudioAnalysisError, analyze_tap
from app.core.schemas import AudioResult

SR = 48000


# ------------------------------------------------------------ sound makers
def make_tap(freq_hz, sr=SR, seconds=3.0, tap_at_s=1.0, decay_s=0.01, amp=0.5, noise=0.002, seed=1):
    """A quiet room with one tap: a fading sine wave starting at tap_at_s."""
    rng = np.random.default_rng(seed)
    n = int(sr * seconds)
    sound = rng.normal(0.0, noise, n)
    t = np.arange(int(sr * 0.15)) / sr
    burst = amp * np.exp(-t / decay_s) * np.sin(2 * np.pi * freq_hz * t)
    start = int(sr * tap_at_s)
    sound[start:start + burst.size] += burst[: n - start]
    return sound


def write_wav(path: Path, samples, sr=SR, kind="int16"):
    """Save samples (floats, -1..1; shape (n,) or (n, 2)) as a WAV file of the given type."""
    samples = np.asarray(samples, dtype=np.float64)
    if kind == "float32":
        wavfile.write(str(path), sr, samples.astype(np.float32))
    elif kind == "int16":
        wavfile.write(str(path), sr, np.round(np.clip(samples, -1, 1) * 32767).astype(np.int16))
    elif kind == "int32":
        wavfile.write(str(path), sr, np.round(np.clip(samples, -1, 1) * 2147483647).astype(np.int32))
    elif kind == "int24":
        ints = np.round(np.clip(samples, -1, 1) * 8388607).astype(np.int64)
        flat = ints.reshape(-1)
        raw = bytearray()
        for v in flat:
            raw += int(v & 0xFFFFFF).to_bytes(3, "little")
        channels = 1 if samples.ndim == 1 else samples.shape[1]
        with wave.open(str(path), "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(3)
            w.setframerate(sr)
            w.writeframes(bytes(raw))
    else:
        raise ValueError(kind)
    return path


# ------------------------------------------------------------ classification
def test_low_tap_is_void(tmp_path):
    wav = write_wav(tmp_path / "low.wav", make_tap(500))
    result = analyze_tap(wav, spectrum_path=tmp_path / "low.png")
    assert isinstance(result, AudioResult)
    assert result.classification == "void"
    assert result.dominant_hz < 900


def test_high_tap_is_solid(tmp_path):
    wav = write_wav(tmp_path / "high.wav", make_tap(2000))
    result = analyze_tap(wav, spectrum_path=tmp_path / "high.png")
    assert result.classification == "solid"
    assert abs(result.dominant_hz - 2000) < 60


def test_middle_tap_is_uncertain(tmp_path):
    wav = write_wav(tmp_path / "mid.wav", make_tap(1100))
    result = analyze_tap(wav, spectrum_path=tmp_path / "mid.png")
    assert result.classification == "uncertain"
    assert abs(result.dominant_hz - 1100) < 60


def test_tap_position_does_not_matter(tmp_path):
    early = write_wav(tmp_path / "early.wav", make_tap(2000, tap_at_s=0.5))
    late = write_wav(tmp_path / "late.wav", make_tap(2000, tap_at_s=2.6))
    a = analyze_tap(early, spectrum_path=tmp_path / "a.png")
    b = analyze_tap(late, spectrum_path=tmp_path / "b.png")
    assert a.classification == b.classification == "solid"


def test_tap_near_edges_of_file(tmp_path):
    for name, at in (("start", 0.05), ("end", 2.85)):
        wav = write_wav(tmp_path / f"{name}.wav", make_tap(2000, tap_at_s=at))
        result = analyze_tap(wav, spectrum_path=tmp_path / f"{name}.png")
        assert result.classification == "solid", name


def test_limits_come_from_config_not_code(tmp_path):
    """Move the void limit up in a copy of the settings: 1100 Hz must now be 'void'."""
    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "thresholds.yaml").read_text(encoding="utf-8"))
    cfg["audio"]["void_below_hz"] = 1500
    cfg["audio"]["solid_above_hz"] = 1800
    custom = tmp_path / "custom.yaml"
    custom.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    wav = write_wav(tmp_path / "mid.wav", make_tap(1100))
    result = analyze_tap(wav, spectrum_path=tmp_path / "m.png", thresholds_path=custom)
    assert result.classification == "void"


# ------------------------------------------------------------ file formats
def test_stereo_file_works(tmp_path):
    tap = make_tap(2000)
    stereo = np.column_stack([tap, tap * 0.8])
    wav = write_wav(tmp_path / "stereo.wav", stereo)
    result = analyze_tap(wav, spectrum_path=tmp_path / "s.png")
    assert result.classification == "solid"


def test_other_sample_rates_are_resampled(tmp_path):
    for sr in (44100, 22050, 96000):
        wav = write_wav(tmp_path / f"sr{sr}.wav", make_tap(2000, sr=sr), sr=sr)
        result = analyze_tap(wav, spectrum_path=tmp_path / f"sr{sr}.png")
        assert result.classification == "solid", sr
        assert abs(result.dominant_hz - 2000) < 60, sr


def test_all_bit_depths(tmp_path):
    for kind in ("int16", "int24", "int32", "float32"):
        wav = write_wav(tmp_path / f"{kind}.wav", make_tap(500), kind=kind)
        result = analyze_tap(wav, spectrum_path=tmp_path / f"{kind}.png")
        assert result.classification == "void", kind


def test_24bit_stereo(tmp_path):
    tap = make_tap(2000)
    wav = write_wav(tmp_path / "s24.wav", np.column_stack([tap, tap]), kind="int24")
    result = analyze_tap(wav, spectrum_path=tmp_path / "s24.png")
    assert result.classification == "solid"


# ------------------------------------------------------------ the picture
def test_spectrum_image_is_saved_at_given_path(tmp_path):
    wav = write_wav(tmp_path / "t.wav", make_tap(2000))
    out = tmp_path / "pictures" / "deep" / "spec.png"
    result = analyze_tap(wav, spectrum_path=out)
    assert result.spectrum_image_path == str(out)
    assert out.is_file()
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_spectrum_image_defaults_next_to_wav(tmp_path):
    wav = write_wav(tmp_path / "tap.wav", make_tap(2000))
    result = analyze_tap(wav)
    assert Path(result.spectrum_image_path) == tmp_path / "tap_spectrum.png"
    assert Path(result.spectrum_image_path).is_file()


# ------------------------------------------------------------ clear errors
def test_missing_file(tmp_path):
    with pytest.raises(AudioAnalysisError) as err:
        analyze_tap(tmp_path / "nope.wav")
    assert "not found" in err.value.message


def test_not_a_wav_file(tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"this is not audio at all")
    with pytest.raises(AudioAnalysisError) as err:
        analyze_tap(bad)
    assert "WAV" in err.value.message


def test_empty_audio(tmp_path):
    wav = write_wav(tmp_path / "empty.wav", np.zeros(0))
    with pytest.raises(AudioAnalysisError) as err:
        analyze_tap(wav)
    assert "empty" in err.value.message


def test_silent_audio(tmp_path):
    wav = write_wav(tmp_path / "silent.wav", np.zeros(SR * 3))
    with pytest.raises(AudioAnalysisError) as err:
        analyze_tap(wav)
    assert "silent" in err.value.message


def test_audio_shorter_than_window(tmp_path):
    short = make_tap(2000, seconds=3.0)[:1000]  # about 21 ms
    wav = write_wav(tmp_path / "short.wav", short + 0.1 * np.sin(np.arange(1000)))
    with pytest.raises(AudioAnalysisError) as err:
        analyze_tap(wav)
    assert "too short" in err.value.message


def test_noise_only_has_no_clear_tap(tmp_path):
    rng = np.random.default_rng(3)
    wav = write_wav(tmp_path / "noise.wav", rng.normal(0, 0.05, SR * 3))
    with pytest.raises(AudioAnalysisError) as err:
        analyze_tap(wav)
    assert "No clear tap" in err.value.message


def test_low_rumble_only_has_no_tap(tmp_path):
    t = np.arange(SR * 3) / SR
    wav = write_wav(tmp_path / "rumble.wav", 0.5 * np.sin(2 * np.pi * 80 * t))
    with pytest.raises(AudioAnalysisError):
        analyze_tap(wav)


def test_clipped_audio(tmp_path):
    loud = np.clip(make_tap(2000, amp=6.0), -1, 1)
    wav = write_wav(tmp_path / "clipped.wav", loud)
    with pytest.raises(AudioAnalysisError) as err:
        analyze_tap(wav)
    assert "clipped" in err.value.message


def test_loud_but_not_clipped_is_fine(tmp_path):
    wav = write_wav(tmp_path / "loud.wav", make_tap(2000, amp=0.95))
    result = analyze_tap(wav, spectrum_path=tmp_path / "loud.png")
    assert result.classification == "solid"


def test_result_works_with_str_paths(tmp_path):
    wav = write_wav(tmp_path / "t.wav", make_tap(2000))
    result = analyze_tap(str(wav), spectrum_path=str(tmp_path / "t.png"))
    assert result.classification == "solid"
