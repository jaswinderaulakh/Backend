"""
Shared data shapes for STHIRA.

Every module (audio, vision, crack, rules, costing, campus) passes its
results to the next one using ONLY the classes in this file.
Do not change this file without asking the project owner.

Files (images, PDFs) are stored on disk; the paths here are relative to
the storage folder set in .env (STORAGE_DIR).
"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- Vision
class ScaleResult(BaseModel):
    """Output of the visual scale-reference step (app/vision)."""

    marker_found: bool                     # True if the 5 cm ArUco marker was detected
    reference_type: Optional[Literal["aruco", "id_card"]] = None  # detected calibration reference
    mm_per_px: Optional[float] = None      # real-world millimetres covered by one pixel (None if no reference)
    confidence: float = Field(0.0, ge=0, le=1)  # how much to trust the scale: 0 = not at all, 1 = fully
    warped_image_path: Optional[str] = None     # the tilt-corrected photo (None if no marker)


# ---------------------------------------------------------------- Crack
class CrackResult(BaseModel):
    """Output of the crack measurement step (app/crack)."""

    max_width_mm: float = Field(ge=0)      # widest point of the crack, in mm (used by the rules)
    mean_width_mm: float = Field(ge=0)     # average width along the crack, in mm
    length_mm: float = Field(ge=0)         # total crack length, in mm
    angle_deg: float = Field(ge=0, le=180) # crack direction in degrees (0 = horizontal, 90 = vertical)
    heatmap_path: Optional[str] = None     # picture showing width along the crack in colour
    mask_path: Optional[str] = None        # black-and-white picture of where the crack is


# ---------------------------------------------------------------- Audio
class AudioResult(BaseModel):
    """Output of the coin-tap sound check (app/audio)."""

    dominant_hz: Optional[float] = None    # loudest frequency of the tap in Hz (None if no tap found)
    classification: Literal["solid", "void", "uncertain"]  # solid = firm concrete, void = hollow, uncertain = in between
    spectrum_image_path: Optional[str] = None  # picture of the sound spectrum


# ---------------------------------------------------------------- Rules
class Verdict(BaseModel):
    """Output of the rule engine (app/rules)."""

    label: str                             # short result, e.g. "Shear risk: inspect first"
    severity: int = Field(ge=1, le=5)      # 1 = harmless ... 5 = urgent
    reason: str                            # plain-English explanation of why this verdict was given


# ---------------------------------------------------------------- Costing
class CostItem(BaseModel):
    """One line of the repair estimate (Bill of Quantities)."""

    description: str                       # what work is done, e.g. "Epoxy injection grouting of cracks"
    unit: str                              # unit of measure, e.g. "rmt" (running metre) or "sqm"
    quantity: float = Field(ge=0)          # how many units are needed
    rate_rs: float = Field(ge=0)           # price per unit, in rupees
    amount_rs: float = Field(ge=0)         # quantity x rate, in rupees


class CostEstimate(BaseModel):
    """Output of the costing step (app/costing)."""

    items: List[CostItem]                  # the line items of the estimate
    total_rs: float = Field(ge=0)          # sum of all line amounts, in rupees
    pdf_path: Optional[str] = None         # the generated PDF report (None until it is created)
    rates_are_placeholder: bool = True     # True while config/cpwd_rates.json still holds fake rates


# ---------------------------------------------------------------- Whole inspection
class InspectionResult(BaseModel):
    """Everything about one inspection. This is what the mobile app receives."""

    inspection_id: int                     # unique number of this inspection
    building_id: int                       # which building was inspected
    building_name: str                     # the building's name, for display
    floor: str                             # floor label, e.g. "Ground" or "2"
    location: str                          # where on the floor, e.g. "Near staircase B"
    exposure_class: Literal["mild", "moderate", "severe"]  # IS 456 exposure class, sets the crack-width limit
    created_by: Optional[int] = None       # id of the user who made the inspection
    created_at: datetime                   # when the inspection was submitted
    completed_at: Optional[datetime] = None  # when processing finished (None while still running)
    status: Literal["pending", "processing", "completed", "failed"]  # where the inspection is in the pipeline
    error_message: Optional[str] = None    # plain-English reason if status is "failed" (e.g. marker not found)

    photo_path: Optional[str] = None       # the original uploaded photo
    audio_path: Optional[str] = None       # the original uploaded WAV file

    scale: Optional[ScaleResult] = None    # filled in after the scale step
    crack: Optional[CrackResult] = None    # filled in after the crack step
    audio: Optional[AudioResult] = None    # filled in after the audio step
    verdict: Optional[Verdict] = None      # filled in after the rules step
    exceeds_is456_limit: Optional[bool] = None  # True if max crack width is above the IS 456 limit for this exposure class
    health_score: Optional[float] = Field(None, ge=0, le=100)  # 0-100, higher is healthier
    cost: Optional[CostEstimate] = None    # filled in after the costing step
