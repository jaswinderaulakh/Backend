"""
Tests for Stage 4 (crack measurement).

Every picture is made by code, with a crack of KNOWN width, length and angle,
so the answers can be checked. Run:  python -m pytest tests/test_crack.py
"""

import math

import cv2
import numpy as np
import pytest

from app.crack.measure import (
    AmbiguousImageError,
    CrackError,
    ImageQualityError,
    NoCrackFoundError,
    measure_crack,
    measure_crack_detailed,
)

MM_PER_PX = 0.1          # in the test pictures, 1 pixel = 0.1 mm
H, W = 400, 700


# ---------------------------------------------------------------- helpers
def make_wall(seed=0, base=170, noise=3.0, gradient=20.0):
    """A grey wall with a gentle lighting change (float picture)."""
    img = np.full((H, W), float(base))
    img += np.linspace(-gradient / 2, gradient / 2, W)[None, :]
    return img, np.random.default_rng(seed), noise


def finish(img, rng, noise, blur=0.7):
    """Soften a little (like a real camera) and add sensor noise."""
    img = cv2.GaussianBlur(img, (0, 0), blur)
    img = img + rng.normal(0, noise, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def line(img, p1, p2, thickness, value=50):
    cv2.line(img, p1, p2, float(value), thickness, cv2.LINE_8)


def save(path, gray, as_name="photo.png"):
    file = path / as_name
    ok, buf = cv2.imencode(".png", cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR))
    assert ok
    buf.tofile(str(file))
    return str(file)


def bar_photo(path, thickness, name="bar.png", seed=0):
    """A horizontal crack that is EXACTLY `thickness` pixels wide."""
    img, rng, noise = make_wall(seed)
    top = 200 - thickness // 2
    img[top:top + thickness, 60:640] = 50.0
    return save(path, finish(img, rng, noise), name)


def straight_crack_photo(path, p1, p2, thickness, name="photo.png", seed=0):
    img, rng, noise = make_wall(seed)
    line(img, p1, p2, thickness)
    return save(path, finish(img, rng, noise), name)


def angle_gap(a, b):
    """Difference between two line directions (0 and 180 are the same)."""
    d = abs(a - b) % 180
    return min(d, 180 - d)


# ---------------------------------------------------------------- width
def test_width_of_known_cracks(tmp_path):
    # Whole-pixel rounding means the answer can be about 1 pixel off.
    for thickness in (5, 8, 12, 20):
        result = measure_crack(bar_photo(tmp_path, thickness, f"w{thickness}.png"), MM_PER_PX)
        expected = thickness * MM_PER_PX
        assert abs(result.mean_width_mm - expected) <= 1.2 * MM_PER_PX, (thickness, result.mean_width_mm)
        assert abs(result.max_width_mm - expected) <= 1.2 * MM_PER_PX, (thickness, result.max_width_mm)
        assert result.max_width_mm >= result.mean_width_mm


def test_widths_double_when_scale_doubles(tmp_path):
    photo = bar_photo(tmp_path, 9)
    a = measure_crack(photo, 0.1)
    b = measure_crack(photo, 0.2)
    assert abs(b.mean_width_mm / a.mean_width_mm - 2.0) < 0.15
    assert abs(b.length_mm / a.length_mm - 2.0) < 0.1


def test_tapered_crack_max_is_bigger_than_mean(tmp_path):
    img, rng, noise = make_wall()
    # a wedge: 2 px wide on the left, 14 px wide on the right
    poly = np.array([[60, 199], [640, 193], [640, 207], [60, 201]], dtype=np.int32)
    cv2.fillPoly(img, [poly], 50.0)
    photo = save(tmp_path, finish(img, rng, noise))
    result = measure_crack(photo, MM_PER_PX)
    assert 11 * MM_PER_PX <= result.max_width_mm <= 16 * MM_PER_PX
    assert result.mean_width_mm < 0.75 * result.max_width_mm


# ---------------------------------------------------------------- length
def test_straight_length_is_measured_in_mm(tmp_path):
    photo = straight_crack_photo(tmp_path, (60, 200), (640, 200), 4)
    result = measure_crack(photo, MM_PER_PX)
    expected = 580 * MM_PER_PX
    assert abs(result.length_mm - expected) / expected < 0.05


def test_curved_crack_length_follows_the_path(tmp_path):
    img, rng, noise = make_wall()
    xs = np.arange(60, 641)
    ys = 200 + 80 * np.sin((xs - 60) / 580 * 2 * math.pi)
    pts = np.column_stack([xs, ys]).astype(np.int32)
    cv2.polylines(img, [pts], False, 50.0, 4, cv2.LINE_8)
    photo = save(tmp_path, finish(img, rng, noise))
    result = measure_crack(photo, MM_PER_PX)

    arc_px = float(np.sum(np.hypot(np.diff(xs), np.diff(ys))))
    straight_px = 580.0
    assert arc_px > 1.1 * straight_px                      # the test really is curvy
    assert abs(result.length_mm / MM_PER_PX - arc_px) / arc_px < 0.06
    assert result.length_mm / MM_PER_PX > 1.1 * straight_px  # not a straight-line measure


# ---------------------------------------------------------------- angle
def test_angle_horizontal_vertical_and_diagonals(tmp_path):
    cases = {
        "horizontal 0": ((60, 200), (640, 200), 0),
        "vertical 90": ((350, 30), (350, 370), 90),
        "rising 45": ((150, 340), (490, 60), None),   # computed below
        "falling 135": ((150, 60), (490, 340), None),
    }
    for name, (p1, p2, expected) in cases.items():
        if expected is None:
            dx, dy = p2[0] - p1[0], -(p2[1] - p1[1])
            expected = math.degrees(math.atan2(dy, dx)) % 180
        photo = straight_crack_photo(tmp_path, p1, p2, 4, name.replace(" ", "_") + ".png")
        result = measure_crack(photo, MM_PER_PX)
        assert 0 <= result.angle_deg <= 180
        assert angle_gap(result.angle_deg, expected) < 3.0, (name, result.angle_deg, expected)


def test_angle_convention_rising_is_below_90(tmp_path):
    rising = straight_crack_photo(tmp_path, (150, 340), (490, 60), 4, "rising.png")   # "/"
    falling = straight_crack_photo(tmp_path, (150, 60), (490, 340), 4, "falling.png")  # "\"
    assert measure_crack(rising, MM_PER_PX).angle_deg < 90
    assert measure_crack(falling, MM_PER_PX).angle_deg > 90


# ---------------------------------------------------------------- areas to ignore
def draw_marker_like_block(img, x, y, size):
    """A black-and-white checker block, like the printed marker."""
    img[y:y + size, x:x + size] = 255
    cell = size // 5
    for i in range(5):
        for j in range(5):
            if (i + j) % 2 == 0:
                img[y + i * cell:y + (i + 1) * cell, x + j * cell:x + (j + 1) * cell] = 10


def test_marker_area_is_ignored(tmp_path):
    plain, rng, noise = make_wall(seed=1)
    line(plain, (60, 330), (640, 330), 4)
    base = measure_crack(save(tmp_path, finish(plain, rng, noise), "plain.png"), MM_PER_PX)

    with_marker, rng, noise = make_wall(seed=1)
    line(with_marker, (60, 330), (640, 330), 4)
    draw_marker_like_block(with_marker, 40, 30, 150)
    photo = save(tmp_path, finish(with_marker, rng, noise), "marker.png")
    result = measure_crack(photo, MM_PER_PX, ignore_region=(40, 30, 150, 150))

    assert abs(result.length_mm - base.length_mm) / base.length_mm < 0.03
    assert abs(result.max_width_mm - base.max_width_mm) < 1.5 * MM_PER_PX
    assert angle_gap(result.angle_deg, base.angle_deg) < 2.0


def test_marker_touching_the_crack_does_not_inflate_width(tmp_path):
    img, rng, noise = make_wall(seed=2)
    line(img, (60, 120), (640, 120), 4)           # crack runs right past the marker
    draw_marker_like_block(img, 40, 135, 150)
    photo = save(tmp_path, finish(img, rng, noise))
    result = measure_crack(photo, MM_PER_PX, ignore_region=(40, 135, 150, 150))
    assert result.max_width_mm < 8 * MM_PER_PX


def test_grey_fill_outside_the_photo_is_ignored(tmp_path):
    img, rng, noise = make_wall(seed=3)
    line(img, (60, 200), (560, 200), 4)
    gray = finish(img, rng, noise)
    reference = measure_crack(save(tmp_path, gray, "ref.png"), MM_PER_PX)

    filled = gray.copy()
    filled[:, 600:] = 128                         # warp fill on the right
    filled[:25, :] = 128                          # ... and on top
    result = measure_crack(save(tmp_path, filled, "fill.png"), MM_PER_PX)
    assert abs(result.length_mm - reference.length_mm) / reference.length_mm < 0.03
    assert abs(result.max_width_mm - reference.max_width_mm) < 1.5 * MM_PER_PX


def test_bad_ignore_box_gives_clear_error(tmp_path):
    photo = straight_crack_photo(tmp_path, (60, 200), (640, 200), 4)
    with pytest.raises(CrackError):
        measure_crack(photo, MM_PER_PX, ignore_region=(10, 10, 0, 50))
    with pytest.raises(CrackError):
        measure_crack(photo, MM_PER_PX, ignore_region=(10, 10, 5))


# ---------------------------------------------------------------- pictures
def test_mask_and_heatmap_are_saved(tmp_path):
    photo = straight_crack_photo(tmp_path, (60, 200), (640, 200), 5)
    result = measure_crack(photo, MM_PER_PX)

    assert result.mask_path and result.heatmap_path
    mask = cv2.imdecode(np.fromfile(result.mask_path, np.uint8), cv2.IMREAD_GRAYSCALE)
    assert mask.shape == (H, W)
    assert set(np.unique(mask)) <= {0, 255}
    assert 0.002 < (mask > 0).mean() < 0.05           # some crack, not everything
    assert mask[200, 350] == 255 and mask[50, 350] == 0

    heat = cv2.imdecode(np.fromfile(result.heatmap_path, np.uint8), cv2.IMREAD_COLOR)
    assert heat is not None and heat.shape[0] > 100 and heat.shape[1] > 100


def test_custom_output_paths_are_used(tmp_path):
    photo = straight_crack_photo(tmp_path, (60, 200), (640, 200), 5)
    mask_out = tmp_path / "out" / "m.png"
    heat_out = tmp_path / "out" / "h.png"
    result = measure_crack(photo, MM_PER_PX, mask_path=str(mask_out), heatmap_path=str(heat_out))
    assert mask_out.is_file() and heat_out.is_file()
    assert result.mask_path == str(mask_out) and result.heatmap_path == str(heat_out)


# ---------------------------------------------------------------- precision limit
def test_thin_crack_is_marked_unreliable(tmp_path):
    report = measure_crack_detailed(bar_photo(tmp_path, 1), 0.2)
    assert report.width_is_reliable is False
    assert "Unreliable" in report.message
    assert abs(report.min_trusted_width_mm - 0.8) < 1e-9       # 4 pixels x 0.2 mm


def test_wide_crack_is_reliable_and_reports_the_limit(tmp_path):
    report = measure_crack_detailed(bar_photo(tmp_path, 10), 0.05)
    assert report.width_is_reliable is True
    assert abs(report.min_trusted_width_mm - 0.2) < 1e-9       # 4 pixels x 0.05 mm
    assert "trusted" in report.message


def test_coarse_scale_warns_about_hairline_cracks(tmp_path):
    report = measure_crack_detailed(bar_photo(tmp_path, 10), 0.12)  # trusted limit 0.48 mm > 0.1 mm hairline
    assert "hairline" in report.message


# ---------------------------------------------------------------- errors
def test_missing_file(tmp_path):
    with pytest.raises(CrackError) as info:
        measure_crack(str(tmp_path / "nope.png"), MM_PER_PX)
    assert "not found" in info.value.message


def test_unreadable_file(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_text("this is not a picture")
    with pytest.raises(CrackError) as info:
        measure_crack(str(bad), MM_PER_PX)
    assert "could not be opened" in info.value.message

    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    with pytest.raises(CrackError):
        measure_crack(str(empty), MM_PER_PX)


def test_invalid_scale_values(tmp_path):
    photo = straight_crack_photo(tmp_path, (60, 200), (640, 200), 4)
    for bad in (0, -0.1, None, float("nan"), float("inf"), "abc", True):
        with pytest.raises(CrackError) as info:
            measure_crack(photo, bad)
        assert "scale" in info.value.message


def test_plain_wall_gives_no_crack(tmp_path):
    img, rng, noise = make_wall(seed=5)
    photo = save(tmp_path, finish(img, rng, noise))
    with pytest.raises(NoCrackFoundError) as info:
        measure_crack(photo, MM_PER_PX)
    assert "No crack detected" in info.value.message


def test_too_dark_photo(tmp_path):
    img, rng, noise = make_wall()
    line(img, (60, 200), (640, 200), 4)
    dark = (finish(img, rng, noise).astype(float) * 0.12).astype(np.uint8)
    with pytest.raises(ImageQualityError) as info:
        measure_crack(save(tmp_path, dark), MM_PER_PX)
    assert "too dark" in info.value.message


def test_too_blurry_photo(tmp_path):
    img, rng, noise = make_wall()
    line(img, (60, 200), (640, 200), 6)
    sharp = finish(img, rng, noise)
    blurry = cv2.GaussianBlur(sharp, (0, 0), 7)
    with pytest.raises(ImageQualityError) as info:
        measure_crack(save(tmp_path, blurry), MM_PER_PX)
    assert "blurry" in info.value.message


def test_too_many_cracks_is_ambiguous(tmp_path):
    img, rng, noise = make_wall()
    for i in range(7):
        y = 40 + i * 50
        line(img, (80, y), (620, y + 15), 4)
    with pytest.raises(AmbiguousImageError) as info:
        measure_crack(save(tmp_path, finish(img, rng, noise)), MM_PER_PX)
    assert "unclear which" in info.value.message


def test_tiny_photo(tmp_path):
    tiny = np.full((30, 30), 170, np.uint8)
    with pytest.raises(ImageQualityError):
        measure_crack(save(tmp_path, tiny), MM_PER_PX)


def test_errors_are_crack_errors_with_messages(tmp_path):
    for cls in (ImageQualityError, NoCrackFoundError, AmbiguousImageError):
        assert issubclass(cls, CrackError)
    err = CrackError("hello")
    assert err.message == "hello" and str(err) == "hello"
