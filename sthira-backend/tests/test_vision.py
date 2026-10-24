"""
Tests for the marker + scale module (app/vision).

No real photos are used. Every test picture is made with code:
a plain wall-coloured background with the ArUco marker on a white sticker,
plus three red discs at known positions that act as an independent ruler.

How the accuracy is checked
---------------------------
The marker is P pixels wide in the flat (front-on) picture, so the true
scale there is  marker_mm / P  mm per pixel. The three red discs are a known
number of pixels apart in that flat picture, so their true distances in mm are
known. After the picture is tilted / rotated / shadowed / blurred, find_scale()
straightens it. We then measure the discs in the straightened picture and
convert with the returned mm_per_px. If everything works, those distances match
the true ones. The "error" printed by each test is the worst of the three
distance errors, in percent. (Run  python -m pytest -s  to see the printed lines.)
"""

import io
from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml
from PIL import Image

from app.core.schemas import ScaleResult
from app.vision import make_marker
from app.vision.scale import (
    ARUCO_DICTIONARY_NAME,
    ARUCO_MARKER_ID,
    MarkerNotFoundError,
    ScaleError,
    find_scale,
    load_photo,
)

W, H = 1600, 1200
WALL_BGR = (200, 212, 218)       # a plain wall colour
MARKER_MM = 50.0                 # same as config/thresholds.yaml
MARKER_PX = 300                  # marker size in the flat picture (true scale = 50/300 mm per px)
MARKER_POS = (200, 400)          # top-left of the black square in the flat picture
DISCS = [(900, 300), (1400, 300), (1000, 1000)]   # red disc centres (flat picture)
DISC_RADIUS = 25
TRUE_MM_PER_PX = MARKER_MM / MARKER_PX

ERRORS = {}   # case name -> worst distance error in percent (printed at the end of a run)


# ------------------------------------------------------------ picture makers
def make_scene(marker_px=MARKER_PX, marker_id=ARUCO_MARKER_ID, with_marker=True, size=(W, H), seed=0):
    """Flat front-on picture: wall + white sticker with marker + 3 red discs."""
    w, h = size
    rng = np.random.default_rng(seed)
    img = np.empty((h, w, 3), np.float32)
    img[:] = WALL_BGR
    img += np.linspace(-6, 6, w, dtype=np.float32)[None, :, None]        # gentle light gradient
    img += rng.normal(0, 2.5, img.shape).astype(np.float32)               # sensor noise
    img = np.clip(img, 0, 255).astype(np.uint8)

    if with_marker:
        dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, ARUCO_DICTIONARY_NAME))
        square = cv2.aruco.generateImageMarker(dictionary, marker_id, marker_px)
        margin = marker_px // 6                                           # white sticker border
        x, y = MARKER_POS
        img[y - margin:y + marker_px + margin, x - margin:x + marker_px + margin] = 255
        img[y:y + marker_px, x:x + marker_px] = square[:, :, None]
    for cx, cy in DISCS:
        cv2.circle(img, (cx, cy), DISC_RADIUS, (30, 30, 200), -1, cv2.LINE_AA)   # red (BGR)
    return img


def warp(img, matrix, size=None):
    h, w = img.shape[:2]
    size = size or (w, h)
    return cv2.warpPerspective(img, matrix, size, flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=WALL_BGR)


def tilt_matrix(strength):
    """Perspective tilt: the right side moves away from the camera. strength 0..1."""
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    squeeze = 0.35 * strength * H
    dst = np.float32([[0, 0], [W * 0.92, squeeze], [W * 0.92, H - squeeze], [0, H]])
    return cv2.getPerspectiveTransform(src, dst)


def rotate_matrix(angle_deg, size_in=(W, H), size_out=(2000, 2000)):
    M = cv2.getRotationMatrix2D((size_in[0] / 2, size_in[1] / 2), angle_deg, 1.0)
    M[0, 2] += (size_out[0] - size_in[0]) / 2
    M[1, 2] += (size_out[1] - size_in[1]) / 2
    return np.vstack([M, [0, 0, 1]])


def add_shadow(img, factor=0.35):
    """A dark diagonal band across the picture, crossing the marker's right side."""
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = (xx - 0.35 * w) + 0.25 * (yy - 0.5 * h)         # signed distance-ish from a slanted line
    band = np.clip((d + 260) / 30, 0, 1) * np.clip((560 - d) / 30, 0, 1)   # soft-edged band
    gain = 1.0 - (1.0 - factor) * band
    return np.clip(img.astype(np.float32) * gain[:, :, None], 0, 255).astype(np.uint8)


def save_photo(path: Path, img):
    ok, buf = cv2.imencode(".png", img)
    assert ok
    path.write_bytes(buf.tobytes())
    return path


# ------------------------------------------------------------ measuring the result
def red_disc_centres(bgr):
    """Centres (x, y) of the 3 biggest red blobs in a picture."""
    b, g, r = [bgr[:, :, i].astype(np.int32) for i in range(3)]
    mask = ((r - np.maximum(g, b)) > 0.45 * r) & (r > 40)
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
    order = sorted(range(1, n), key=lambda i: -stats[i, cv2.CC_STAT_AREA])[:3]
    assert len(order) == 3, f"found {len(order)} red discs in the straightened picture, expected 3"
    return [tuple(cents[i]) for i in order]


def pair_distances(points):
    d = []
    for i in range(3):
        for j in range(i + 1, 3):
            d.append(float(np.hypot(points[i][0] - points[j][0], points[i][1] - points[j][1])))
    return sorted(d)


TRUE_DISTANCES_MM = sorted(
    float(np.hypot(a[0] - b[0], a[1] - b[1])) * TRUE_MM_PER_PX
    for i, a in enumerate(DISCS) for b in DISCS[i + 1:]
)


def worst_error_percent(result: ScaleResult):
    """Measure the discs in the straightened picture, return worst distance error in %."""
    warped = cv2.imdecode(np.frombuffer(Path(result.warped_image_path).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    measured_mm = [d * result.mm_per_px for d in pair_distances(red_disc_centres(warped))]
    return max(abs(m - t) / t * 100 for m, t in zip(measured_mm, TRUE_DISTANCES_MM))


def run_case(tmp_path, name, img, limit_percent):
    photo = save_photo(tmp_path / f"{name}.png", img)
    result = find_scale(photo, warped_path=tmp_path / f"{name}_warped.png")
    err = worst_error_percent(result)
    ERRORS[name] = err
    print(f"[{name}] mm_per_px={result.mm_per_px:.5f}  confidence={result.confidence:.2f}  "
          f"worst distance error={err:.2f}%")
    assert isinstance(result, ScaleResult)
    assert result.marker_found is True
    assert 0 <= result.confidence <= 1
    assert err < limit_percent, f"{name}: error {err:.2f}% is not below {limit_percent}%"
    return result


# ------------------------------------------------------------ accuracy cases
def test_flat_photo_scale_is_accurate(tmp_path):
    result = run_case(tmp_path, "flat", make_scene(), 1.0)
    # the flat picture's true scale is known exactly
    assert abs(result.mm_per_px - TRUE_MM_PER_PX) / TRUE_MM_PER_PX < 0.01


def test_tilted_photo_is_straightened(tmp_path):
    for strength in (0.4, 0.8):
        run_case(tmp_path, f"tilt_{strength}", warp(make_scene(), tilt_matrix(strength)), 2.0)


def test_rotated_photo(tmp_path):
    for angle in (30, 90, 180):
        img = warp(make_scene(), rotate_matrix(angle), (2000, 2000))
        run_case(tmp_path, f"rotated_{angle}", img, 1.5)


def test_tilted_and_rotated_photo(tmp_path):
    img = warp(warp(make_scene(), tilt_matrix(0.6)), rotate_matrix(-20), (2000, 2000))
    run_case(tmp_path, "tilt_and_rotate", img, 2.0)


def test_dark_shadow_across_photo(tmp_path):
    run_case(tmp_path, "shadow", add_shadow(make_scene()), 2.0)


def test_mildly_blurred_photo_still_measures_but_with_less_confidence(tmp_path):
    sharp = run_case(tmp_path, "sharp_ref", make_scene(), 1.0)
    blurred = run_case(tmp_path, "blur_mild", cv2.GaussianBlur(make_scene(), (0, 0), 2.0), 2.0)
    assert blurred.confidence < sharp.confidence


def test_confidence_is_lower_for_worse_photos(tmp_path):
    flat = find_scale(save_photo(tmp_path / "a.png", make_scene()), warped_path=tmp_path / "a_w.png")
    tilted = find_scale(save_photo(tmp_path / "b.png", warp(make_scene(), tilt_matrix(0.9))),
                        warped_path=tmp_path / "b_w.png")
    small = find_scale(save_photo(tmp_path / "c.png", make_scene(marker_px=120)), warped_path=tmp_path / "c_w.png")
    print(f"[confidence] flat={flat.confidence:.2f} tilted={tilted.confidence:.2f} small marker={small.confidence:.2f}")
    assert flat.confidence > tilted.confidence
    assert flat.confidence > small.confidence
    assert flat.confidence > 0.8


def test_small_but_big_enough_marker_is_accurate(tmp_path):
    # a 150 px marker is allowed; the scale is coarser, so a looser limit
    img = make_scene(marker_px=150)
    photo = save_photo(tmp_path / "small.png", img)
    result = find_scale(photo, warped_path=tmp_path / "small_w.png")
    assert abs(result.mm_per_px - MARKER_MM / 150) / (MARKER_MM / 150) < 0.02


# ------------------------------------------------------------ output files
def test_warped_picture_is_saved_and_marker_is_upright_square(tmp_path):
    img = warp(warp(make_scene(), tilt_matrix(0.6)), rotate_matrix(25), (2000, 2000))
    result = find_scale(save_photo(tmp_path / "p.png", img), warped_path=tmp_path / "out" / "w.png")
    out = Path(result.warped_image_path)
    assert out == tmp_path / "out" / "w.png"
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    warped = cv2.imdecode(np.frombuffer(out.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    # the marker can still be found in the saved (shadow-corrected) picture, and it is a square
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, ARUCO_DICTIONARY_NAME))
    corners, ids, _ = cv2.aruco.ArucoDetector(dictionary).detectMarkers(cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY))
    assert ids is not None
    quad = corners[0].reshape(4, 2)
    sides = [np.linalg.norm(quad[(k + 1) % 4] - quad[k]) for k in range(4)]
    assert max(sides) / min(sides) < 1.02
    assert abs(np.mean(sides) * result.mm_per_px - MARKER_MM) < 0.5   # marker measures ~50 mm


def test_default_output_path_is_next_to_photo(tmp_path):
    photo = save_photo(tmp_path / "wall.png", make_scene())
    result = find_scale(photo)
    assert Path(result.warped_image_path) == tmp_path / "wall_warped.png"
    assert Path(result.warped_image_path).is_file()


def test_str_paths_work(tmp_path):
    photo = save_photo(tmp_path / "wall.png", make_scene())
    result = find_scale(str(photo), warped_path=str(tmp_path / "w.png"))
    assert result.marker_found


def test_shadow_removal_evens_out_lighting(tmp_path):
    img = add_shadow(make_scene())
    result = find_scale(save_photo(tmp_path / "s.png", img), warped_path=tmp_path / "s_w.png")
    warped = cv2.imdecode(np.frombuffer(Path(result.warped_image_path).read_bytes(), np.uint8), cv2.IMREAD_COLOR)

    def lightness(a):
        return cv2.cvtColor(a, cv2.COLOR_BGR2LAB)[:, :, 0].astype(np.float32)

    # For this flat (front-on) picture the straightened picture lines up pixel for pixel
    # with the original, so the same wall patches can be compared before and after.
    assert warped.shape[:2] == img.shape[:2] or abs(warped.shape[0] - img.shape[0]) <= 2
    lit_box, shadow_box = (slice(700, 800), slice(1000, 1100)), (slice(700, 800), slice(600, 700))
    before = lightness(img)[shadow_box].mean() / lightness(img)[lit_box].mean()
    after = lightness(warped)[shadow_box].mean() / lightness(warped)[lit_box].mean()
    print(f"[shadow removal] shadowed wall is {before:.2f} as bright as lit wall before, {after:.2f} after")
    assert before < 0.8          # the test picture really has a dark shadow
    assert after > before        # CLAHE makes the shadow less severe (it does not remove it completely)


# ------------------------------------------------------------ settings
def test_marker_size_comes_from_config_not_code(tmp_path):
    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "thresholds.yaml").read_text(encoding="utf-8"))
    cfg["marker"]["aruco_size_mm"] = 100
    custom = tmp_path / "custom.yaml"
    custom.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    photo = save_photo(tmp_path / "p.png", make_scene())
    a = find_scale(photo, warped_path=tmp_path / "a.png")
    b = find_scale(photo, warped_path=tmp_path / "b.png", thresholds_path=custom)
    assert abs(b.mm_per_px / a.mm_per_px - 2.0) < 0.01


# ------------------------------------------------------------ loading photos
def test_phone_rotation_in_exif_is_applied(tmp_path):
    # A phone held sideways saves the pixels rotated and adds EXIF "orientation 6" (rotate 90 clockwise to view).
    upright = make_scene()
    sideways = cv2.rotate(upright, cv2.ROTATE_90_COUNTERCLOCKWISE)
    pil = Image.fromarray(cv2.cvtColor(sideways, cv2.COLOR_BGR2RGB))
    exif = Image.Exif()
    exif[0x0112] = 6
    path = tmp_path / "phone.jpg"
    pil.save(str(path), "JPEG", quality=95, exif=exif)
    loaded = load_photo(path)
    assert loaded.shape[:2] == upright.shape[:2]          # back to landscape, as the person saw it
    assert np.abs(loaded.astype(int) - upright.astype(int)).mean() < 6   # and the same picture (JPEG loss only)
    result = find_scale(path, warped_path=tmp_path / "phone_w.png")
    assert abs(result.mm_per_px - TRUE_MM_PER_PX) / TRUE_MM_PER_PX < 0.02


def test_jpeg_photo_works(tmp_path):
    path = tmp_path / "p.jpg"
    Image.fromarray(cv2.cvtColor(make_scene(), cv2.COLOR_BGR2RGB)).save(str(path), "JPEG", quality=85)
    result = find_scale(path, warped_path=tmp_path / "p_w.png")
    assert abs(result.mm_per_px - TRUE_MM_PER_PX) / TRUE_MM_PER_PX < 0.02


def test_very_large_photo_is_shrunk_safely(tmp_path):
    big_w, big_h = 6000, 4500
    k = 3.75
    img = cv2.resize(make_scene(), (big_w, big_h), interpolation=cv2.INTER_CUBIC)   # same scene, 3.75x the pixels
    loaded_path = save_photo(tmp_path / "big.png", img)
    loaded = load_photo(loaded_path)
    assert max(loaded.shape[:2]) <= 4000
    result = find_scale(loaded_path, warped_path=tmp_path / "big_w.png")
    # true scale: the marker is 300*k px wide in the big photo
    assert abs(result.mm_per_px - MARKER_MM / (MARKER_PX * k) * (big_w / loaded.shape[1])) / result.mm_per_px < 0.02
    assert max(cv2.imread(str(tmp_path / "big_w.png")).shape[:2]) <= 4000


# ------------------------------------------------------------ errors
def test_missing_file(tmp_path):
    with pytest.raises(ScaleError) as err:
        find_scale(tmp_path / "nope.jpg")
    assert "not found" in err.value.message


def test_file_that_is_not_an_image(tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"this is not a picture")
    with pytest.raises(ScaleError) as err:
        find_scale(bad)
    assert "could not be opened" in err.value.message


def test_no_marker_in_photo(tmp_path):
    photo = save_photo(tmp_path / "plain.png", make_scene(with_marker=False))
    with pytest.raises(MarkerNotFoundError) as err:
        find_scale(photo)
    assert "Marker not visible" in err.value.message
    assert "retake" in err.value.message


def test_marker_cut_off_by_photo_edge(tmp_path):
    img = make_scene()[:, 330:]          # cuts through the marker
    photo = save_photo(tmp_path / "cut.png", img)
    with pytest.raises(MarkerNotFoundError):
        find_scale(photo)


def test_wrong_marker_id(tmp_path):
    photo = save_photo(tmp_path / "other.png", make_scene(marker_id=ARUCO_MARKER_ID + 5))
    with pytest.raises(MarkerNotFoundError) as err:
        find_scale(photo)
    assert "not the STHIRA marker" in err.value.message


def test_marker_too_small_in_frame(tmp_path):
    photo = save_photo(tmp_path / "tiny.png", make_scene(marker_px=50))
    with pytest.raises(ScaleError) as err:
        find_scale(photo)
    assert "too small" in err.value.message
    assert not isinstance(err.value, MarkerNotFoundError)


def test_blurry_photo_is_rejected(tmp_path):
    photo = save_photo(tmp_path / "blurry.png", cv2.GaussianBlur(make_scene(), (0, 0), 7.0))
    with pytest.raises(ScaleError) as err:
        find_scale(photo)
    print(f"[blurry] message: {err.value.message}")
    assert "blurry" in err.value.message or "Marker not visible" in err.value.message


def test_very_dark_marker_is_rejected_or_not_found(tmp_path):
    dark = (make_scene().astype(np.float32) * 0.08).astype(np.uint8)
    photo = save_photo(tmp_path / "dark.png", dark)
    with pytest.raises(ScaleError):
        find_scale(photo)


# ------------------------------------------------------------ marker maker
def test_printable_marker_has_right_size_and_print_size(tmp_path):
    image, marker_px, ppm = make_marker.build_marker_image(MARKER_MM)
    assert marker_px == 591                                   # 5 cm at 300 dpi, rounded to whole pixels
    assert abs(marker_px / ppm * 1000 - MARKER_MM) < 0.01     # and exactly 50 mm on paper
    border_px = (image.shape[0] - marker_px) // 2
    assert 9.5 < border_px / ppm * 1000 < 10.5                # white border about 10 mm
    assert image[:border_px].min() == 255 and image[:, :border_px].min() == 255   # border is white


def test_make_marker_script_saves_png_with_print_size(tmp_path):
    out = tmp_path / "m.png"
    assert make_marker.main(["--out", str(out)]) == 0
    with Image.open(out) as img:
        dpi_x = img.info["dpi"][0]
        assert 299 < dpi_x < 302
        # width of the black square on paper, from the file's own print size
        arr = np.asarray(img.convert("L"))
        cols = np.where(arr.min(axis=0) < 128)[0]
        black_px = cols.max() - cols.min() + 1
        assert abs(black_px / dpi_x * 25.4 - MARKER_MM) < 0.2


def test_printed_marker_file_can_be_measured(tmp_path):
    out = tmp_path / "m.png"
    make_marker.main(["--out", str(out)])
    result = find_scale(out, warped_path=tmp_path / "m_w.png")
    assert abs(result.mm_per_px - MARKER_MM / 591) / (MARKER_MM / 591) < 0.01
