"""
Marker + scale step (Stage 3).

Main function:  find_scale(image_path) -> ScaleResult

What it does, in order:
  1. Loads the photo (fixes phone rotation from EXIF, shrinks huge photos).
  2. Finds the printed ArUco marker.
  3. Uses the marker's 4 corners to "un-tilt" the photo (perspective correction)
     so the wall looks as if it was photographed straight on.
  4. Measures the marker in the straightened photo and works out
     mm_per_px = real marker width (mm) / marker width (pixels).
  5. Evens out shadows/lighting with CLAHE (in LAB colour space).
  6. Saves the straightened photo and returns a ScaleResult.

The marker's real size (50 mm) is read from config/thresholds.yaml.

If the photo cannot be used, a ScaleError is raised with a plain-English
message (ScaleResult has no field for a reason, so an error is the best fit).
MarkerNotFoundError is the "no marker" version of it. The pipeline should
catch it and save the inspection as "failed" with that message.

NOTE ON ORIENTATION: the straightened photo is turned so the marker is upright.
So the marker should be stuck on the wall "right way up" (not sideways), or
crack angles will be measured relative to the sideways marker.
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple, Union

import cv2
import numpy as np
import yaml
from PIL import Image, ImageOps

from app.core.schemas import ScaleResult

PathLike = Union[str, Path]

# --------------------------------------------------------------------------
# Settings that are NOT in config/thresholds.yaml (it is a shared file and was
# not changed). They are named constants so they are easy to find and move into
# the config later (needs the project owner's OK).
# --------------------------------------------------------------------------
# Which marker we print and look for. The config file does not list one.
# make_marker.py uses the same two lines, so print and detection always agree.
ARUCO_DICTIONARY_NAME = "DICT_4X4_50"
ARUCO_MARKER_ID = 0
ID_CARD_MIN_SIDE_PX = 80
ID_CARD_MIN_AREA_FRACTION = 0.002
ID_CARD_MAX_AREA_FRACTION = 0.40
ID_CARD_ASPECT_MIN = 1.30
ID_CARD_ASPECT_MAX = 1.70

MAX_IMAGE_SIDE_PX = 4000        # bigger photos are shrunk to this (longest side)
DETECT_MIN_PERIMETER_RATE = 0.01  # let the detector see small markers, so we can say "too small"
MIN_MARKER_SIDE_PX = 80         # marker narrower than this (in the photo) is rejected
GOOD_MARKER_SIDE_PX = 400       # marker this wide or more gets full "size" score
MIN_MARKER_CONTRAST = 40        # black-vs-white difference (0-255) needed on the marker
BLUR_FAIL_SHARPNESS = 0.10      # marker edges softer than this = blurry photo, rejected
BLUR_GOOD_SHARPNESS = 0.30      # edges this crisp or better get full "sharpness" score
TILT_BAD_RATIO = 0.35           # shortest/longest marker side at which tilt score is 0
TILT_GOOD_RATIO = 0.85          # ... and at which tilt score is 1
CONSISTENCY_BAD_ERROR = 0.05    # 5% disagreement in the straightened marker = score 0
WARP_WINDOW_MARKER_WIDTHS = 20  # straightened photo reaches at most this many marker widths from the marker
MAX_WARP_SIDE_PX = 4000         # straightened photo is never bigger than this (longest side)
WARP_FILL_GRAY = 128            # colour for areas outside the original photo
CLAHE_CLIP_LIMIT = 2.0          # CLAHE strength
CLAHE_TILE_GRID = 8             # CLAHE works on an 8 x 8 grid of patches
# How much each quality score counts in the confidence number (they add up to 1).
CONF_WEIGHTS = {"sharpness": 0.35, "size": 0.30, "tilt": 0.20, "consistency": 0.15}
MIN_SCORE = 0.05                # no single score is allowed to drop below this in the confidence


class ScaleError(Exception):
    """A problem with the photo. The message is plain English and safe to show a user."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class MarkerNotFoundError(ScaleError):
    """The marker could not be found in the photo."""


# ------------------------------------------------------------------ config
def _default_thresholds_path() -> Path:
    # app/vision/scale.py -> project root is two folders up from "app"
    return Path(__file__).resolve().parents[2] / "config" / "thresholds.yaml"


@lru_cache(maxsize=8)
def _load_marker_config(path_str: str) -> dict:
    path = Path(path_str)
    if not path.is_file():
        raise ScaleError(f"Settings file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        marker_mm = float(data["marker"]["aruco_size_mm"])
        if marker_mm <= 0:
            raise ValueError("marker size must be above zero")
        card_short_mm = float(data["marker"]["id_card_short_side_mm"])
        card_long_mm = float(data["marker"]["id_card_long_side_mm"])
        if card_short_mm <= 0 or card_long_mm <= card_short_mm:
            raise ValueError("ID card dimensions must be positive and the long side must be longer")
        return {"marker_mm": marker_mm, "card_short_mm": card_short_mm, "card_long_mm": card_long_mm}
    except (KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise ScaleError(f"The marker settings in {path.name} are missing or not valid ({exc}).") from exc


# ------------------------------------------------------------------ loading
def load_photo(path: Path) -> np.ndarray:
    """Open a photo upright (EXIF rotation applied), shrink it if huge. Returns a BGR array."""
    if not path.is_file():
        raise ScaleError(f"Photo file not found: {path}")
    try:
        with Image.open(path) as img:
            img.draft("RGB", (MAX_IMAGE_SIDE_PX, MAX_IMAGE_SIDE_PX))  # fast shrink for big JPEGs
            img = ImageOps.exif_transpose(img)  # phones store "rotate me" in EXIF
            img = img.convert("RGB")
            rgb = np.asarray(img)
    except Exception as exc:
        raise ScaleError(
            "The photo could not be opened. Please upload a normal JPEG or PNG photo."
        ) from exc
    if rgb.ndim != 3 or rgb.shape[0] < 2 or rgb.shape[1] < 2:
        raise ScaleError("The photo is empty or damaged. Please take the photo again.")
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    longest = max(bgr.shape[:2])
    if longest > MAX_IMAGE_SIDE_PX:
        f = MAX_IMAGE_SIDE_PX / longest
        bgr = cv2.resize(bgr, (round(bgr.shape[1] * f), round(bgr.shape[0] * f)), interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(bgr)


# ------------------------------------------------------------------ marker
def make_detector() -> "cv2.aruco.ArucoDetector":
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, ARUCO_DICTIONARY_NAME))
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX  # corners to a fraction of a pixel
    params.minMarkerPerimeterRate = DETECT_MIN_PERIMETER_RATE
    return cv2.aruco.ArucoDetector(dictionary, params)


def _detect(gray: np.ndarray) -> Tuple[Optional[np.ndarray], bool]:
    """
    Look for our marker. Returns (corners, other_markers_seen).
    corners is a 4x2 array in the order top-left, top-right, bottom-right,
    bottom-left (as the marker itself is drawn), or None.
    """
    corners, ids, _ = make_detector().detectMarkers(gray)
    if ids is None or len(ids) == 0:
        return None, False
    best, best_area = None, -1.0
    for c, i in zip(corners, ids.flatten()):
        if int(i) != ARUCO_MARKER_ID:
            continue
        quad = c.reshape(4, 2).astype(np.float64)
        area = abs(cv2.contourArea(quad.astype(np.float32)))
        if area > best_area:
            best, best_area = quad, area
    return best, best is None


def _order_card_quad(quad: np.ndarray) -> np.ndarray:
    """Rotate contour-order card corners so the first edge is a short side."""
    points = np.asarray(quad, dtype=np.float64).reshape(4, 2)
    lengths = _side_lengths(points)
    short_edge = int(np.argmin(lengths))
    return np.roll(points, -short_edge, axis=0)


def _detect_id_card(gray: np.ndarray) -> Optional[np.ndarray]:
    """Find the largest sharp, convex quadrilateral with a 6:9-card aspect ratio.

    The user must include the whole physical card with a visible outer edge. This
    deliberately does not infer scale from text or card artwork.
    """
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 45, 135)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_area = float(gray.shape[0] * gray.shape[1])
    candidates = []
    for contour in contours:
        area = abs(float(cv2.contourArea(contour)))
        if area < image_area * ID_CARD_MIN_AREA_FRACTION or area > image_area * ID_CARD_MAX_AREA_FRACTION:
            continue
        perimeter = float(cv2.arcLength(contour, True))
        if perimeter <= 0:
            continue
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        ordered = _order_card_quad(approx.reshape(4, 2))
        sides = _side_lengths(ordered)
        short_px = float((sides[0] + sides[2]) / 2.0)
        long_px = float((sides[1] + sides[3]) / 2.0)
        aspect = long_px / max(short_px, 1e-6)
        if short_px < ID_CARD_MIN_SIDE_PX or not ID_CARD_ASPECT_MIN <= aspect <= ID_CARD_ASPECT_MAX:
            continue
        candidates.append((area, ordered))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _side_lengths(quad: np.ndarray) -> np.ndarray:
    return np.array([np.linalg.norm(quad[(k + 1) % 4] - quad[k]) for k in range(4)])


def _clamp01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


# ------------------------------------------------------------------ warp
def _build_warp(quad: np.ndarray, image_shape: Tuple[int, int]) -> Tuple[np.ndarray, Tuple[int, int]]:
    """
    Homography that makes the marker an upright square and shows as much of the
    photo as is sensible. Returns (3x3 matrix, (canvas_width, canvas_height)).
    """
    h, w = image_shape
    side = float(_side_lengths(quad).mean())
    dst = np.array([[0, 0], [side, 0], [side, side], [0, side]], dtype=np.float32)
    H0 = cv2.getPerspectiveTransform(quad.astype(np.float32), dst)

    # Where do the photo's own corners land? (if any is behind the camera plane, ignore the photo outline)
    photo_corners = np.array([[0, 0, 1], [w, 0, 1], [w, h, 1], [0, h, 1]], dtype=np.float64).T
    mapped = H0 @ photo_corners
    window = WARP_WINDOW_MARKER_WIDTHS * side
    lo_x, hi_x, lo_y, hi_y = -window, side + window, -window, side + window
    if np.all(mapped[2] > 1e-9):
        xs, ys = mapped[0] / mapped[2], mapped[1] / mapped[2]
        lo_x, hi_x = max(lo_x, xs.min()), min(hi_x, xs.max())
        lo_y, hi_y = max(lo_y, ys.min()), min(hi_y, ys.max())
    # always keep the marker itself inside
    lo_x, hi_x = min(lo_x, 0.0), max(hi_x, side)
    lo_y, hi_y = min(lo_y, 0.0), max(hi_y, side)

    span = max(hi_x - lo_x, hi_y - lo_y)
    f = min(1.0, MAX_WARP_SIDE_PX / span)  # shrink only, never enlarge
    A = np.array([[f, 0, -lo_x * f], [0, f, -lo_y * f], [0, 0, 1]], dtype=np.float64)
    canvas = (max(2, int(math.ceil((hi_x - lo_x) * f))), max(2, int(math.ceil((hi_y - lo_y) * f))))
    return A @ H0, canvas


def _build_id_card_warp(
    quad: np.ndarray, image_shape: Tuple[int, int], aspect_ratio: float
) -> Tuple[np.ndarray, Tuple[int, int], np.ndarray]:
    """Straighten a 6x9 cm card to a portrait 2:3 rectangle and retain wall area."""
    h, w = image_shape
    ordered = _order_card_quad(quad)
    sides = _side_lengths(ordered)
    short_px = float((sides[0] + sides[2]) / 2.0)
    target_h = short_px * aspect_ratio
    dst = np.array([[0, 0], [short_px, 0], [short_px, target_h], [0, target_h]], dtype=np.float32)
    H0 = cv2.getPerspectiveTransform(ordered.astype(np.float32), dst)

    photo_corners = np.array([[0, 0, 1], [w, 0, 1], [w, h, 1], [0, h, 1]], dtype=np.float64).T
    mapped = H0 @ photo_corners
    window = WARP_WINDOW_MARKER_WIDTHS * target_h
    lo_x, hi_x, lo_y, hi_y = -window, short_px + window, -window, target_h + window
    if np.all(mapped[2] > 1e-9):
        xs, ys = mapped[0] / mapped[2], mapped[1] / mapped[2]
        lo_x, hi_x = max(lo_x, xs.min()), min(hi_x, xs.max())
        lo_y, hi_y = max(lo_y, ys.min()), min(hi_y, ys.max())
    lo_x, hi_x = min(lo_x, 0.0), max(hi_x, short_px)
    lo_y, hi_y = min(lo_y, 0.0), max(hi_y, target_h)
    span = max(hi_x - lo_x, hi_y - lo_y)
    f = min(1.0, MAX_WARP_SIDE_PX / span)
    A = np.array([[f, 0, -lo_x * f], [0, f, -lo_y * f], [0, 0, 1]], dtype=np.float64)
    canvas = (max(2, int(math.ceil((hi_x - lo_x) * f))), max(2, int(math.ceil((hi_y - lo_y) * f))))
    return A @ H0, canvas, ordered


# ------------------------------------------------------------------ quality
def _sharpness(gray: np.ndarray, quad: np.ndarray) -> Tuple[float, float]:
    """
    Edge crispness of the marker, from 0 (very blurry) to about 0.5 (razor sharp).
    Returns (sharpness, contrast).

    Idea: a perfectly sharp black/white edge changes by half its height per pixel
    (using neighbouring pixels on both sides); a blurred edge with blur radius s
    pixels changes by only about 0.4 / s of its height per pixel. So
        sharpness = steepest edge slope / (white level - black level)
    Slopes come from the marker and a thin strip of white around it.
    """
    side = float(_side_lengths(quad).mean())
    pad = 0.1 * side
    x0 = int(max(0, math.floor(quad[:, 0].min() - pad)))
    x1 = int(min(gray.shape[1], math.ceil(quad[:, 0].max() + pad)))
    y0 = int(max(0, math.floor(quad[:, 1].min() - pad)))
    y1 = int(min(gray.shape[0], math.ceil(quad[:, 1].max() + pad)))
    crop = gray[y0:y1, x0:x1].astype(np.float64)
    if crop.shape[0] < 5 or crop.shape[1] < 5:
        return 0.0, 0.0
    contrast = float(np.percentile(crop, 95) - np.percentile(crop, 5))
    if contrast <= 0:
        return 0.0, contrast
    gy, gx = np.gradient(crop)
    steepest = float(np.percentile(np.maximum(np.abs(gx), np.abs(gy)), 99))
    return steepest / contrast, contrast


def _confidence(side_px: float, sharpness: float, ratio: float, consistency_err: float) -> float:
    """
    Confidence = how much to trust mm_per_px, from 0 to 1.

    Four quality scores, each from 0 (bad) to 1 (good):
      sharpness   crisp marker edges (blur makes the corners fuzzy).
                  0 at BLUR_FAIL_SHARPNESS, 1 at BLUR_GOOD_SHARPNESS.
      size        marker width in the photo. More pixels = each pixel of corner
                  error matters less. 0 at MIN_MARKER_SIDE_PX, 1 at GOOD_MARKER_SIDE_PX.
      tilt        how square the marker looks: shortest side / longest side
                  (1 = straight on, smaller = more tilted, and tilt makes corner
                  errors count for more). 0 at TILT_BAD_RATIO, 1 at TILT_GOOD_RATIO.
      consistency after straightening, the marker should be a perfect square of
                  the expected size; any disagreement means the corners were
                  found badly. 1 = perfect, 0 at CONSISTENCY_BAD_ERROR.
    They are combined as a weighted geometric mean (CONF_WEIGHTS):
        confidence = sharpness^0.35 x size^0.30 x tilt^0.20 x consistency^0.15
    so a single bad score pulls the confidence down a lot, which is what we want
    (one weak link makes the measurement unreliable). Each score is kept at
    MIN_SCORE or above so the result never collapses to exactly zero.
    """
    scores = {
        "sharpness": _clamp01((sharpness - BLUR_FAIL_SHARPNESS) / (BLUR_GOOD_SHARPNESS - BLUR_FAIL_SHARPNESS)),
        "size": _clamp01((side_px - MIN_MARKER_SIDE_PX) / (GOOD_MARKER_SIDE_PX - MIN_MARKER_SIDE_PX)),
        "tilt": _clamp01((ratio - TILT_BAD_RATIO) / (TILT_GOOD_RATIO - TILT_BAD_RATIO)),
        "consistency": _clamp01(1.0 - consistency_err / CONSISTENCY_BAD_ERROR),
    }
    value = 1.0
    for name, weight in CONF_WEIGHTS.items():
        value *= max(scores[name], MIN_SCORE) ** weight
    return round(_clamp01(value), 3)


# ------------------------------------------------------------------ shadows
def _remove_shadows(bgr: np.ndarray) -> np.ndarray:
    """CLAHE on the lightness channel only (colours are left alone)."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=(CLAHE_TILE_GRID, CLAHE_TILE_GRID))
    return cv2.cvtColor(cv2.merge((clahe.apply(l), a, b)), cv2.COLOR_LAB2BGR)


def _save_png(path: Path, bgr: np.ndarray) -> None:
    ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        raise ScaleError("The straightened photo could not be created.")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(buf.tobytes())  # (cv2.imwrite fails on non-English folder names on Windows)
    except OSError as exc:
        raise ScaleError(f"The straightened photo could not be saved to {path}.") from exc


# ------------------------------------------------------------------ main
def find_scale(
    image_path: PathLike,
    warped_path: Optional[PathLike] = None,
    thresholds_path: Optional[PathLike] = None,
) -> ScaleResult:
    """
    Find the STHIRA marker or 6x9 cm ID card in a photo and work out the scale.

    image_path      the photo
    warped_path     where to save the straightened photo (PNG). If left out it is
                    saved next to the photo as "<name>_warped.png".
    thresholds_path only for tests: use a different thresholds.yaml

    Raises ScaleError (plain-English .message) when the photo cannot be used,
    and MarkerNotFoundError when neither scale reference is visible.
    """
    image_path = Path(image_path)
    cfg = _load_marker_config(str(Path(thresholds_path) if thresholds_path else _default_thresholds_path()))
    marker_mm = cfg["marker_mm"]
    card_short_mm = cfg["card_short_mm"]
    card_long_mm = cfg["card_long_mm"]
    card_aspect = card_long_mm / card_short_mm

    # 1. Load
    bgr = load_photo(image_path)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # 2. Prefer the coded marker, then try the configured 6x9 cm card.
    quad, only_other_markers = _detect(gray)
    reference_type = "aruco"
    if quad is None:
        quad = _detect_id_card(gray)
        if quad is None:
            if only_other_markers:
                raise MarkerNotFoundError(
                    "A marker was found, but it is not the STHIRA marker; no full 6x9 cm card was detected either. "
                    "Place the entire 6x9 cm card beside the crack or use the STHIRA marker."
                )
            raise MarkerNotFoundError(
                "Marker not visible and no scale reference found. Please retake the photo with the complete 6x9 cm ID card "
                "beside the crack or use the STHIRA marker; keep its outline sharp and unobstructed."
            )
        reference_type = "id_card"

    if reference_type == "aruco":
        sides = _side_lengths(quad)
        side_px = float(sides.mean())
        if side_px < MIN_MARKER_SIDE_PX:
            raise ScaleError(
                f"The marker is too small in the photo ({side_px:.0f} pixels wide, at least {MIN_MARKER_SIDE_PX} needed). "
                "Please move closer so the marker fills more of the photo, then retake it."
            )
        ratio = float(sides.min() / sides.max())
        H, canvas = _build_warp(quad, gray.shape)
        warped = cv2.warpPerspective(
            bgr, H, canvas, flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT,
            borderValue=(WARP_FILL_GRAY, WARP_FILL_GRAY, WARP_FILL_GRAY),
        )
        warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        expected = cv2.perspectiveTransform(quad.reshape(1, 4, 2).astype(np.float32), H.astype(np.float64)).reshape(4, 2)
        expected_side = float(_side_lengths(expected).mean())
        again, _ = _detect(warped_gray)
        if again is not None:
            measured = _side_lengths(again)
            reference_px = float(measured.mean())
            consistency_err = max(
                float(np.abs(measured - reference_px).max() / reference_px),
                abs(reference_px - expected_side) / expected_side,
            )
            reference_quad = again
        else:
            reference_px = expected_side
            consistency_err = CONSISTENCY_BAD_ERROR / 2
            reference_quad = expected
        mm_per_px = marker_mm / reference_px
    else:
        sides = _side_lengths(quad)
        short_px = float((sides[0] + sides[2]) / 2.0)
        long_px = float((sides[1] + sides[3]) / 2.0)
        if short_px < ID_CARD_MIN_SIDE_PX:
            raise ScaleError(
                f"The 6x9 cm card is too small in the photo ({short_px:.0f} pixels across its short side; "
                f"at least {ID_CARD_MIN_SIDE_PX} are needed). Move closer and retake the photo."
            )
        H, canvas, quad = _build_id_card_warp(quad, gray.shape, card_aspect)
        warped = cv2.warpPerspective(
            bgr, H, canvas, flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT,
            borderValue=(WARP_FILL_GRAY, WARP_FILL_GRAY, WARP_FILL_GRAY),
        )
        warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        reference_quad = cv2.perspectiveTransform(quad.reshape(1, 4, 2).astype(np.float32), H.astype(np.float64)).reshape(4, 2)
        measured = _side_lengths(reference_quad)
        reference_px = float((measured[0] + measured[2]) / 2.0)
        long_measured_px = float((measured[1] + measured[3]) / 2.0)
        consistency_err = max(
            abs(measured[0] - measured[2]) / max(reference_px, 1e-6),
            abs(measured[1] - measured[3]) / max(long_measured_px, 1e-6),
            abs((long_measured_px / max(reference_px, 1e-6)) - card_aspect) / card_aspect,
        )
        side_px = reference_px
        ratio = 1.0
        mm_per_px = card_short_mm / reference_px

    # 5. Check that the chosen scale reference is sharp and contrasty enough.
    sharpness, contrast = _sharpness(warped_gray, reference_quad)
    if contrast < MIN_MARKER_CONTRAST:
        raise ScaleError(
            "The scale reference is too dark or washed out to measure. "
            "Retake the photo in even light, without glare or heavy shadow over the marker/card."
        )
    if sharpness < BLUR_FAIL_SHARPNESS:
        raise ScaleError(
            "The photo is blurry around the scale reference. Hold the phone steady and retake it."
        )
    confidence = _confidence(side_px, sharpness, ratio, consistency_err)

    # 6. Even out shadows, save
    cleaned = _remove_shadows(warped)
    out = Path(warped_path) if warped_path else image_path.with_name(image_path.stem + "_warped.png")
    _save_png(out, cleaned)

    return ScaleResult(
        marker_found=(reference_type == "aruco"),
        reference_type=reference_type,
        mm_per_px=mm_per_px,
        confidence=confidence,
        warped_image_path=str(out),
    )
