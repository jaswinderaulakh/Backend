"""
Crack measurement (Stage 4).

Main function:  measure_crack(image_path, mm_per_px) -> CrackResult

Input : the straightened ("warped") photo from the scale step, plus the scale
        (millimetres per pixel) as a plain number.
Output: max / mean width (mm), length (mm), angle (degrees), and two pictures
        (mask and heatmap) saved to disk.

This file does NOT import anything from app/vision/, so the two stages stay
independent.

How it works, in plain words:
  1. Load the photo, make it grey-scale.
  2. Ignore areas that are not wall: the grey fill outside the original photo
     and (optionally) the printed marker.
  3. Check the photo is bright and sharp enough.
  4. Find dark thin lines (the crack) with a classical, non-AI method.
  5. Keep the one region that looks most like a crack.
  6. Thin it to a 1-pixel skeleton and measure along it.
  7. Save the mask and the heatmap.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import yaml
from matplotlib.figure import Figure
from scipy import ndimage as ndi
from skimage.morphology import skeletonize

from app.core.schemas import CrackResult

logger = logging.getLogger(__name__)

# ======================================================================
# Settings that are NOT in config/thresholds.yaml
# (shared file, so not changed; same approach as the audio and scale stages).
# Suggestion: move them into the config later, with the project owner's OK.
# All are STARTING VALUES to be tuned on real campus photos.
# ======================================================================

# --- Which segmentation method to use -------------------------------
SEGMENTER = "classical"        # "classical" now; "yolo" once a model exists

# --- Areas to ignore ------------------------------------------------
# The scale step fills areas outside the original photo with this grey.
# Copied from WARP_FILL_GRAY in app/vision/scale.py (we must not import it).
WARP_FILL_GRAY = 128
MIN_FILL_AREA_PX = 200         # a grey patch must be at least this big ...
                               # ... AND touch the photo edge to count as "fill"
IGNORE_MARGIN_PX = 6           # extra safety border around the ignored marker box
FILL_SAFETY_BORDER_PX = 4      # extra safety border around the grey fill

# --- Photo quality checks -------------------------------------------
MIN_IMAGE_SIDE_PX = 64         # smaller photos cannot be measured
MIN_VALID_FRACTION = 0.10      # at least 10 % of the photo must be usable wall
MIN_MEAN_BRIGHTNESS = 40       # 0-255; below this the photo is "too dark"
BLUR_LAPLACIAN_VAR_MIN = 2.0   # below this the photo is "too blurry"

# --- Classical crack finder -----------------------------------------
SMOOTH_SIGMA_PX = 1.0          # light smoothing before filtering
FILTER_SPAN_MM = 8.0           # black-hat / adaptive window must be wider than the widest crack
FILTER_SPAN_MIN_PX = 15        # (window size is clamped to these limits, in pixels)
FILTER_SPAN_MAX_PX = 81
ADAPTIVE_C = 8                 # pixel must be this much darker than its surroundings
BLACKHAT_MIN = 12              # ... and the black-hat response must be at least this
EDGE_DEPTH_FRACTION = 0.5      # crack edge = where the dark dip is half as deep as its deepest part
EDGE_WINDOW_PX = 15            # size of the window used to find the deepest part nearby
CLOSE_KERNEL_PX = 3            # closes 1-pixel gaps in the crack
GROUP_DILATE_PX = 7            # pieces closer than this are treated as one crack

# --- Choosing the crack among the blobs -----------------------------
MIN_COMPONENT_AREA_PX = 30     # smaller blobs are noise
MIN_CRACK_LENGTH_MM = 5.0      # shorter marks are not cracks
MIN_CRACK_LENGTH_FLOOR_PX = 15 # ... but never less than this many pixels
MIN_ELONGATION = 3.0           # crack-like = at least 3x longer than wide
MAX_CRACK_REGIONS = 4          # more crack-like regions than this = ambiguous
MAX_BLOBS_BEFORE_FILTER = 3000 # more raw blobs than this = textured / noisy photo
MAX_MASK_FRACTION = 0.15       # crack covering >15 % of the usable wall = not a crack
MAX_HOLE_AREA_PX = 64          # small holes inside the crack mask are filled

# --- Width measurement ----------------------------------------------
# The distance transform measures between pixel CENTRES, so 2 x distance is
# on average half a pixel too wide. We subtract this to remove the bias.
WIDTH_CENTRE_CORRECTION_PX = 0.5

# --- Honest precision limit -----------------------------------------
# A crack needs at least this many pixels across before its width can be
# trusted. One pixel is the absolute limit of what a camera can resolve, but
# in our tests any crack from 1 to about 4 pixels wide was reported as about
# 3.5 pixels (camera blur plus whole-pixel rounding), so a reading at or
# below this value could be a much thinner crack.
MIN_TRUSTED_WIDTH_PX = 4.0

# --- Heatmap picture ------------------------------------------------
HEATMAP_COLORMAP = "turbo"
HEATMAP_FIGURE_WIDTH_IN = 8
HEATMAP_DPI = 100

DEFAULT_THRESHOLDS_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "thresholds.yaml"
)


# ======================================================================
# Errors (each has a plain-English .message)
# ======================================================================
class CrackError(Exception):
    """Base error for this stage. `.message` is safe to show to a user."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ImageQualityError(CrackError):
    """The photo is too dark, too blurry, too small or mostly unusable."""


class NoCrackFoundError(CrackError):
    """The photo is fine but no crack was found in it.

    CrackResult has no way to say "no crack" (angle, widths and so on need real
    numbers), so this is an error. Stage 7 may decide this is a normal
    "completed, no crack" case rather than a failed inspection.
    """


class AmbiguousImageError(CrackError):
    """Too many crack-like regions: we cannot tell which one is THE crack."""


# ======================================================================
# Result with extra information
# ======================================================================
@dataclass
class CrackReport:
    """CrackResult plus the extra facts that CrackResult has no field for."""

    result: CrackResult
    min_trusted_width_mm: float   # smallest width that can be trusted at this scale
    width_is_reliable: bool       # False if the crack is too thin to measure well
    message: str                  # plain-English note about how far to trust the numbers
    crack_regions_found: int      # how many crack-like regions were seen


# ======================================================================
# Public functions
# ======================================================================
def measure_crack(
    image_path: str,
    mm_per_px: float,
    ignore_region: Optional[Tuple[int, int, int, int]] = None,
    mask_path: Optional[str] = None,
    heatmap_path: Optional[str] = None,
    thresholds_path: Optional[str] = None,
) -> CrackResult:
    """Measure the crack in a straightened photo. Returns a CrackResult.

    image_path     the warped photo (ScaleResult.warped_image_path)
    mm_per_px      the scale (ScaleResult.mm_per_px)
    ignore_region  optional (x, y, w, h) box in pixels of the WARPED photo to
                   skip, normally the printed marker (see `_make_ignore_mask`)
    mask_path      where to save the mask picture (default: next to the photo)
    heatmap_path   where to save the heatmap (default: next to the photo)
    thresholds_path  only for tests

    Raises CrackError (or a subclass) with a plain-English `.message`.
    Use measure_crack_detailed() if you also want the precision note.
    """
    return measure_crack_detailed(
        image_path, mm_per_px, ignore_region, mask_path, heatmap_path, thresholds_path
    ).result


def measure_crack_detailed(
    image_path: str,
    mm_per_px: float,
    ignore_region: Optional[Tuple[int, int, int, int]] = None,
    mask_path: Optional[str] = None,
    heatmap_path: Optional[str] = None,
    thresholds_path: Optional[str] = None,
) -> CrackReport:
    """Same as measure_crack, but returns a CrackReport with the precision note."""
    scale = _check_scale(mm_per_px)
    config = _load_thresholds(thresholds_path)
    bgr = _load_image(image_path)

    height, width = bgr.shape[:2]
    if min(height, width) < MIN_IMAGE_SIDE_PX:
        raise ImageQualityError(
            "The photo is too small to measure a crack. Please retake it closer "
            "or at a higher resolution."
        )
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # --- 1. Work out which pixels are real wall ----------------------
    outside = _find_fill_region(bgr)
    ignored = _make_ignore_mask(ignore_region, (height, width))
    excluded = outside | ignored
    valid = ~excluded
    if valid.mean() < MIN_VALID_FRACTION:
        raise ImageQualityError(
            "Too little of the photo is usable wall. Please retake the photo "
            "with the crack and the marker clearly in view."
        )

    # Paint excluded areas with the nearest real wall colour, so they do not
    # create fake edges that look like cracks.
    gray_filled = _fill_with_nearest_wall(gray, excluded)

    # Keep a safety border away from the excluded areas.
    safe_zone = _shrink(valid, FILL_SAFETY_BORDER_PX)

    # --- 2. Quality checks -------------------------------------------
    _check_quality(gray_filled, valid, safe_zone)

    # --- 3. Find the crack -------------------------------------------
    raw = _segment(gray_filled, scale)
    raw &= safe_zone
    crack_mask, regions_found = _select_crack(raw, scale, int(safe_zone.sum()))
    crack_mask = _fill_small_holes(crack_mask)

    # --- 4. Measure ---------------------------------------------------
    skeleton = skeletonize(crack_mask)
    if int(skeleton.sum()) < 2:
        raise NoCrackFoundError("No crack detected in this photo.")

    # Width at each skeleton point: 2 x distance to the nearest background
    # pixel (see WIDTH_CENTRE_CORRECTION_PX for the half-pixel correction).
    distance = ndi.distance_transform_edt(crack_mask)
    widths_px = np.maximum(2.0 * distance[skeleton] - WIDTH_CENTRE_CORRECTION_PX, 1.0)
    widths_mm = widths_px * scale

    max_width_mm = float(widths_mm.max())
    mean_width_mm = float(widths_mm.mean())
    length_mm = _skeleton_length_px(skeleton) * scale
    angle_deg = _skeleton_angle_deg(skeleton)

    # --- 5. Pictures --------------------------------------------------
    mask_out, heatmap_out = _output_paths(image_path, mask_path, heatmap_path)
    _save_mask(crack_mask, mask_out)
    _save_heatmap(gray, crack_mask, skeleton, widths_mm, max_width_mm, heatmap_out)

    result = CrackResult(
        max_width_mm=max_width_mm,
        mean_width_mm=mean_width_mm,
        length_mm=float(length_mm),
        angle_deg=float(angle_deg),
        heatmap_path=str(heatmap_out),
        mask_path=str(mask_out),
    )

    # --- 6. Honest precision note ------------------------------------
    min_trusted_mm = MIN_TRUSTED_WIDTH_PX * scale
    reliable, note = _precision_note(
        max_width_mm, mean_width_mm, min_trusted_mm, scale, config
    )
    if not reliable:
        logger.warning("Crack width unreliable: %s", note)
    else:
        logger.info("Crack measured. %s", note)

    return CrackReport(
        result=result,
        min_trusted_width_mm=min_trusted_mm,
        width_is_reliable=reliable,
        message=note,
        crack_regions_found=regions_found,
    )


# ======================================================================
# Precision note
# ======================================================================
def _precision_note(max_mm, mean_mm, min_trusted_mm, mm_per_px, config) -> Tuple[bool, str]:
    """Say honestly how far the width numbers can be trusted.

    WHY RESOLUTION MATTERS: the camera sees the wall as a grid of pixels, each
    covering `mm_per_px` of wall. A crack narrower than about one pixel simply
    cannot be seen, and a crack only a few pixels wide is measured with an
    error as big as the crack itself (blur and rounding to whole pixels). To
    trust the width of a 0.1 mm hairline crack it must be about 4 pixels
    across, so each pixel may cover at most about 0.025 mm, which means the
    5 cm marker must span about 2000 pixels. At 0.12 mm per pixel a 0.1 mm
    crack is thinner than one pixel: the width is NOT reliable.
    """
    one_px = mm_per_px
    parts = []
    reliable = max_mm >= min_trusted_mm

    if not reliable:
        parts.append(
            f"Unreliable width: the crack is only {max_mm:.2f} mm wide at its widest, "
            f"which is less than {MIN_TRUSTED_WIDTH_PX:.0f} pixels in this photo "
            f"(1 pixel = {one_px:.3f} mm, smallest trusted width = {min_trusted_mm:.2f} mm). "
            "Please retake the photo closer to the wall."
        )
    else:
        parts.append(
            f"Smallest width that can be trusted at this scale: {min_trusted_mm:.2f} mm "
            f"(1 pixel = {one_px:.3f} mm)."
        )
        if mean_mm < min_trusted_mm:
            parts.append(
                f"The average width ({mean_mm:.2f} mm) is below that limit, so treat it as approximate."
            )

    hairline = config["hairline_below_mm"]
    if min_trusted_mm > hairline:
        parts.append(
            f"At this scale a hairline crack (under {hairline:g} mm) cannot be measured reliably; "
            "retake the photo closer for a better reading."
        )
    return reliable, " ".join(parts)


# ======================================================================
# Input checks and loading
# ======================================================================
def _check_scale(mm_per_px) -> float:
    if mm_per_px is None:
        raise CrackError("The scale (millimetres per pixel) is missing, so the crack cannot be measured.")
    if isinstance(mm_per_px, bool):
        raise CrackError("The scale (millimetres per pixel) is not a valid number.")
    try:
        value = float(mm_per_px)
    except (TypeError, ValueError):
        raise CrackError("The scale (millimetres per pixel) is not a valid number.")
    if not math.isfinite(value) or value <= 0:
        raise CrackError(
            "The scale (millimetres per pixel) must be a number greater than zero."
        )
    return value


def _load_thresholds(thresholds_path: Optional[str]) -> dict:
    path = Path(thresholds_path) if thresholds_path else DEFAULT_THRESHOLDS_PATH
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        return {"hairline_below_mm": float(data["crack"]["hairline_below_mm"])}
    except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError):
        raise CrackError(
            "The settings file config/thresholds.yaml is missing or has no "
            "crack.hairline_below_mm value."
        )


def _load_image(image_path: str) -> np.ndarray:
    path = Path(str(image_path))
    if not path.is_file():
        raise CrackError(f"The photo file was not found: {path}")
    try:
        data = np.fromfile(str(path), dtype=np.uint8)  # works with any Windows path
    except OSError:
        raise CrackError("The photo file could not be read.")
    image = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    if image is None:
        raise CrackError("The photo could not be opened. Please use a normal JPEG or PNG picture.")
    return image


# ======================================================================
# Areas to ignore
# ======================================================================
def _find_fill_region(bgr: np.ndarray) -> np.ndarray:
    """Pixels that are the flat grey fill outside the original photo.

    Only big grey patches that touch the photo edge count, so ordinary wall
    pixels that happen to be exactly 128 are not thrown away.
    """
    is_grey = np.all(bgr == WARP_FILL_GRAY, axis=2).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(is_grey, connectivity=4)
    height, width = is_grey.shape
    fill = np.zeros(is_grey.shape, dtype=bool)
    for index in range(1, count):
        x, y, w, h, area = stats[index]
        touches_edge = x == 0 or y == 0 or x + w == width or y + h == height
        if area >= MIN_FILL_AREA_PX and touches_edge:
            fill |= labels == index
    return fill


def _make_ignore_mask(region, shape) -> np.ndarray:
    """Turn the optional (x, y, w, h) box into a True/False picture.

    HOW THE PIPELINE WILL USE THIS (Stage 7): the scale step finds the marker
    in the ORIGINAL photo and straightens the photo. When the pipeline is
    connected, the marker's corners should be carried through the same
    straightening, and the pipeline passes the box around those corners as
    ignore_region=(x, y, w, h), in pixels of the WARPED photo. Until then,
    leave it as None. If the marker is not ignored, it is still unlikely to be
    chosen as the crack (it is a compact block, not a thin line), but it can
    disturb the result, so passing the box is the safe way.
    """
    mask = np.zeros(shape, dtype=bool)
    if region is None:
        return mask
    try:
        x, y, w, h = [int(round(v)) for v in region]
    except (TypeError, ValueError):
        raise CrackError("The area to ignore must be four numbers: x, y, width, height.")
    if w <= 0 or h <= 0:
        raise CrackError("The area to ignore must have a width and height above zero.")
    height, width = shape
    x0 = max(0, x - IGNORE_MARGIN_PX)
    y0 = max(0, y - IGNORE_MARGIN_PX)
    x1 = min(width, x + w + IGNORE_MARGIN_PX)
    y1 = min(height, y + h + IGNORE_MARGIN_PX)
    if x1 > x0 and y1 > y0:
        mask[y0:y1, x0:x1] = True
    return mask


def _fill_with_nearest_wall(gray: np.ndarray, excluded: np.ndarray) -> np.ndarray:
    """Copy the nearest real wall pixel into every excluded pixel."""
    if not excluded.any():
        return gray.copy()
    indices = ndi.distance_transform_edt(excluded, return_distances=False, return_indices=True)
    return gray[indices[0], indices[1]]


def _shrink(mask: np.ndarray, border_px: int) -> np.ndarray:
    """Move the edge of a True/False picture inwards by border_px."""
    if border_px <= 0:
        return mask.copy()
    kernel = _ellipse(2 * border_px + 1)
    padded = cv2.copyMakeBorder(mask.astype(np.uint8), border_px, border_px, border_px, border_px,
                                cv2.BORDER_REPLICATE)
    eroded = cv2.erode(padded, kernel)
    return eroded[border_px:-border_px, border_px:-border_px].astype(bool)


def _ellipse(size: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


# ======================================================================
# Quality checks
# ======================================================================
def _check_quality(gray_filled: np.ndarray, valid: np.ndarray, safe_zone: np.ndarray) -> None:
    mean_brightness = float(gray_filled[valid].mean())
    if mean_brightness < MIN_MEAN_BRIGHTNESS:
        raise ImageQualityError(
            "The photo is too dark to find a crack. Please retake it with more light."
        )
    # Blur: sharp photos have strong pixel-to-pixel changes.
    laplacian = cv2.Laplacian(gray_filled, cv2.CV_64F)
    region = laplacian[safe_zone] if safe_zone.any() else laplacian[valid]
    if float(region.var()) < BLUR_LAPLACIAN_VAR_MIN:
        raise ImageQualityError(
            "The photo is too blurry. Please hold the phone steady, let it focus, and retake it."
        )


# ======================================================================
# Segmentation (finding the crack pixels)
# ======================================================================
def _segment(gray_filled: np.ndarray, mm_per_px: float) -> np.ndarray:
    """Return a True/False picture of crack-like pixels (before cleaning up)."""
    if SEGMENTER == "yolo":
        return _segment_with_yolo(gray_filled)
    return _segment_classical(gray_filled, mm_per_px)


def _segment_with_yolo(gray_filled: np.ndarray) -> np.ndarray:
    """PLACEHOLDER for a YOLOv8-Seg crack model.

    TODO(YOLOv8-Seg): load the trained model once (not on every call), run it
    on the photo, and return one True/False picture of the same size as the
    input where True = crack pixel. Everything after this step (choosing the
    crack, skeleton, widths) stays exactly the same. Nothing is built or
    downloaded yet; switch on by setting SEGMENTER = "yolo".
    """
    raise NotImplementedError("The YOLOv8-Seg crack model is not built yet. Use SEGMENTER = 'classical'.")


def _odd(value: int) -> int:
    return value if value % 2 == 1 else value + 1


def _segment_classical(gray_filled: np.ndarray, mm_per_px: float) -> np.ndarray:
    smooth = cv2.GaussianBlur(gray_filled, (0, 0), SMOOTH_SIGMA_PX)

    span = int(round(FILTER_SPAN_MM / mm_per_px))
    span = _odd(int(np.clip(span, FILTER_SPAN_MIN_PX, FILTER_SPAN_MAX_PX)))

    # Black-hat: keeps thin DARK lines, removes smooth lighting changes.
    blackhat = cv2.morphologyEx(smooth, cv2.MORPH_BLACKHAT, _ellipse(span))
    # Adaptive threshold: a pixel is "dark" if it is clearly darker than its surroundings.
    adaptive = cv2.adaptiveThreshold(
        smooth, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, span, ADAPTIVE_C
    )
    # A blurred crack has soft edges. Keeping every faintly dark pixel would make the
    # crack look too wide, so the edge is placed where the dip is half as deep as
    # the deepest part nearby (the "half-maximum" edge).
    deepest_nearby = cv2.dilate(blackhat, np.ones((EDGE_WINDOW_PX, EDGE_WINDOW_PX), np.uint8))
    half_depth = blackhat >= EDGE_DEPTH_FRACTION * deepest_nearby
    candidate = (adaptive > 0) & (blackhat >= BLACKHAT_MIN) & half_depth

    closed = cv2.morphologyEx(
        candidate.astype(np.uint8), cv2.MORPH_CLOSE, _ellipse(CLOSE_KERNEL_PX)
    )
    return closed.astype(bool)


def _select_crack(raw: np.ndarray, mm_per_px: float, usable_pixels: int):
    """Keep the single most crack-like region. Returns (mask, regions_found)."""
    if not raw.any():
        raise NoCrackFoundError("No crack detected in this photo.")

    min_extent_px = max(MIN_CRACK_LENGTH_FLOOR_PX, MIN_CRACK_LENGTH_MM / mm_per_px)

    # Pieces of one broken crack are joined by growing the picture a little.
    grouped = cv2.dilate(raw.astype(np.uint8), _ellipse(GROUP_DILATE_PX))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(grouped, connectivity=8)
    if count - 1 > MAX_BLOBS_BEFORE_FILTER:
        raise AmbiguousImageError(
            "The wall surface is too rough or noisy to pick out one crack. "
            "Please retake the photo in even light."
        )

    candidates = []  # (extent, mask_crop, x, y)
    for index in range(1, count):
        x, y, w, h, _area = stats[index]
        crop = (labels[y:y + h, x:x + w] == index) & raw[y:y + h, x:x + w]
        pixels = int(crop.sum())
        if pixels < MIN_COMPONENT_AREA_PX:
            continue
        ys, xs = np.nonzero(crop)
        extent, elongation = _extent_and_elongation(xs, ys)
        if extent < min_extent_px or elongation < MIN_ELONGATION:
            continue
        candidates.append((extent, crop, x, y))

    if not candidates:
        raise NoCrackFoundError("No crack detected in this photo.")
    if len(candidates) > MAX_CRACK_REGIONS:
        raise AmbiguousImageError(
            f"Found {len(candidates)} separate crack-like marks, so it is unclear which one "
            "is the crack. Please retake the photo with only one crack in view."
        )

    extent, crop, x, y = max(candidates, key=lambda item: item[0])
    mask = np.zeros(raw.shape, dtype=bool)
    mask[y:y + crop.shape[0], x:x + crop.shape[1]] = crop

    if usable_pixels > 0 and mask.sum() / usable_pixels > MAX_MASK_FRACTION:
        raise AmbiguousImageError(
            "A very large part of the wall was marked as crack (maybe a shadow, stain or "
            "dirt). Please retake the photo in even light."
        )
    return mask, len(candidates)


def _extent_and_elongation(xs: np.ndarray, ys: np.ndarray):
    """Rough length and 'how line-like' for a set of pixels (PCA)."""
    if xs.size < 3:
        return 0.0, 0.0
    cov = np.cov(np.vstack([xs, ys]).astype(float))
    eigenvalues = np.sort(np.linalg.eigvalsh(cov))
    major, minor = max(eigenvalues[1], 0.0), max(eigenvalues[0], 1e-6)
    extent = math.sqrt(12.0 * major)        # length of a uniform line with this spread
    elongation = math.sqrt(major / minor)
    return extent, elongation


def _fill_small_holes(mask: np.ndarray) -> np.ndarray:
    """Fill tiny holes inside the crack (they would make widths too small)."""
    inverse = (~mask).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(inverse, connectivity=4)
    height, width = mask.shape
    result = mask.copy()
    for index in range(1, count):
        x, y, w, h, area = stats[index]
        touches_edge = x == 0 or y == 0 or x + w == width or y + h == height
        if area <= MAX_HOLE_AREA_PX and not touches_edge:
            result[labels == index] = True
    return result


# ======================================================================
# Measuring the skeleton
# ======================================================================
def _skeleton_length_px(skeleton: np.ndarray) -> float:
    """Length ALONG the skeleton path, in pixels (not a straight line).

    Every pair of touching skeleton pixels is one step: 1 pixel for
    side-by-side neighbours, sqrt(2) for diagonal ones. A diagonal step is
    skipped when a corner pixel already connects the same two pixels, so
    corners are not counted twice. Branches are included, so this is the
    total crack length. The skeleton stops about half a crack-width short of
    each end of the crack, a small underestimate that matters little for long
    cracks.
    """
    s = np.pad(skeleton.astype(bool), 1)
    centre = s[1:-1, 1:-1]
    right = s[1:-1, 2:]
    left = s[1:-1, :-2]
    down = s[2:, 1:-1]
    down_right = s[2:, 2:]
    down_left = s[2:, :-2]

    straight = np.count_nonzero(centre & right) + np.count_nonzero(centre & down)
    diag = np.count_nonzero(centre & down_right & ~right & ~down) + \
        np.count_nonzero(centre & down_left & ~left & ~down)
    return float(straight + math.sqrt(2.0) * diag)


def _skeleton_angle_deg(skeleton: np.ndarray) -> float:
    """Crack direction from PCA on the skeleton points.

    ANGLE DEFINITION (as the photo is seen on screen, y flipped so that "up"
    is positive):
        0 degrees   = horizontal crack  ( --- )
        90 degrees  = vertical crack    ( |   )
        45 degrees  = rising to the right ( /  )
        135 degrees = falling to the right ( \\ )
    The value is always from 0 up to (but not including) 180, because a
    crack has no "forward" direction: 0 and 180 are the same line.
    For a curved crack this is the overall direction (the main axis).
    """
    ys, xs = np.nonzero(skeleton)
    if xs.size < 2:
        return 0.0
    points = np.column_stack([xs.astype(float), -ys.astype(float)])  # flip y
    points -= points.mean(axis=0)
    eigenvalues, eigenvectors = np.linalg.eigh(np.cov(points.T))
    main_axis = eigenvectors[:, int(np.argmax(eigenvalues))]
    return math.degrees(math.atan2(main_axis[1], main_axis[0])) % 180.0


# ======================================================================
# Saving pictures
# ======================================================================
def _output_paths(image_path, mask_path, heatmap_path):
    base = Path(str(image_path))
    mask_out = Path(mask_path) if mask_path else base.with_name(base.stem + "_mask.png")
    heat_out = Path(heatmap_path) if heatmap_path else base.with_name(base.stem + "_heatmap.png")
    return mask_out, heat_out


def _save_mask(mask: np.ndarray, path: Path) -> None:
    """Black-and-white picture: white = crack."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".png", mask.astype(np.uint8) * 255)
    if not ok:
        raise CrackError("The crack mask picture could not be saved.")
    encoded.tofile(str(path))


def _save_heatmap(gray, mask, skeleton, widths_mm, max_width_mm, path: Path) -> None:
    """Photo in grey with the crack coloured by width (colour bar in mm)."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Give every crack pixel the width of its nearest skeleton point.
    skeleton_widths = np.zeros(mask.shape, dtype=np.float32)
    skeleton_widths[skeleton] = widths_mm
    nearest = ndi.distance_transform_edt(~skeleton, return_distances=False, return_indices=True)
    width_map = skeleton_widths[nearest[0], nearest[1]]
    shown = np.ma.masked_where(~mask, width_map)

    height, width = gray.shape
    fig_width = HEATMAP_FIGURE_WIDTH_IN
    fig = Figure(figsize=(fig_width, fig_width * height / width + 0.6), dpi=HEATMAP_DPI)
    ax = fig.add_subplot(111)
    ax.imshow(gray, cmap="gray", vmin=0, vmax=255)
    image = ax.imshow(shown, cmap=HEATMAP_COLORMAP, vmin=0.0,
                      vmax=max(max_width_mm, 1e-6), interpolation="nearest")
    bar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.02)
    bar.set_label("Crack width (mm)")
    ax.set_title(f"Crack width map (widest {max_width_mm:.2f} mm)")
    ax.axis("off")
    fig.savefig(str(path), bbox_inches="tight")
