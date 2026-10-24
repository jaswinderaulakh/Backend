"""Create a concise PDF report for a STHIRA inspection."""
from __future__ import annotations

from datetime import timezone
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from app.core.schemas import InspectionResult
from app.core.settings import PROJECT_ROOT
from app.core.storage import resolve, storage_root
from app.costing.estimate import compare_repair_options


def _rupees(amount: float) -> str:
    """Format a number with Indian digit grouping and a font-safe currency label."""
    value = f"{amount:.2f}"
    integer, decimal = value.split(".")
    if len(integer) > 3:
        tail, head = integer[-3:], integer[:-3]
        groups = []
        while head:
            groups.insert(0, head[-2:])
            head = head[:-2]
        integer = ",".join(groups + [tail])
    return f"Rs. {integer}.{decimal}"


def _image_file(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    candidate = Path(path_value)
    options = [candidate] if candidate.is_absolute() else [storage_root() / candidate, PROJECT_ROOT / candidate]
    for option in options:
        try:
            if option.is_file():
                return option
        except (OSError, ValueError):
            continue
    return None


def _add_optional_image(story: list, label: str, path_value: str | None, styles) -> None:
    path = _image_file(path_value)
    story.append(Paragraph(label, styles["Heading3"]))
    if path is None:
        story.append(Paragraph("Not available (image file is missing).", styles["BodyText"]))
    else:
        try:
            image = Image(str(path), width=75 * mm, height=52 * mm, kind="proportional", hAlign="LEFT")
            story.append(image)
        except Exception:
            story.append(Paragraph("Not available (image could not be opened).", styles["BodyText"]))


def make_pdf(result: InspectionResult, out_path: str) -> str:
    """Write a one- or two-page inspection PDF and return its path."""
    destination = Path(out_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], alignment=TA_CENTER,
                              textColor=colors.HexColor("#174A63"), spaceAfter=8))
    story: list = [Paragraph("STHIRA Structural Health Inspection", styles["ReportTitle"])]
    created = result.created_at
    if created.tzinfo is not None:
        created = created.astimezone(timezone.utc)
    story.append(Paragraph(f"Inspection date: {escape(created.strftime('%d %b %Y, %H:%M UTC'))}", styles["BodyText"]))
    story.append(Spacer(1, 4 * mm))

    details = [
        ["Building", result.building_name or f"Building {result.building_id}"],
        ["Floor", result.floor or "Not recorded"], ["Location", result.location or "Not recorded"],
        ["Exposure class", result.exposure_class.title()],
    ]
    table = Table([[Paragraph(escape(str(a)), styles["BodyText"]), Paragraph(escape(str(b)), styles["BodyText"])] for a, b in details],
                  colWidths=[38 * mm, 130 * mm])
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8F0F3")),
                               ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#B7C7CE")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 6)]))
    story.extend([table, Spacer(1, 4 * mm)])

    if result.crack:
        c = result.crack
        story.append(Paragraph("Measured results", styles["Heading2"]))
        values = [["Widest crack", f"{c.max_width_mm:g} mm"], ["Average width", f"{c.mean_width_mm:g} mm"],
                  ["Crack length", f"{c.length_mm:g} mm"], ["Angle", f"{c.angle_deg:g} degrees"]]
        if result.scale and result.scale.mm_per_px is not None:
            values.append(["Scale", f"{result.scale.mm_per_px:g} mm/pixel"])
        if result.audio:
            hz = "unavailable" if result.audio.dominant_hz is None else f"{result.audio.dominant_hz:g} Hz"
            values.append(["Tap sound", f"{hz} ({result.audio.classification})"])
        if result.health_score is not None:
            values.append(["Health score", f"{result.health_score:g} / 100"])
        numbers = Table([[a, b] for a, b in values], colWidths=[48 * mm, 120 * mm])
        numbers.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .3, colors.lightgrey),
                                     ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F8F9")),
                                     ("PADDING", (0, 0), (-1, -1), 5)]))
        story.extend([numbers, Spacer(1, 3 * mm)])

    if result.verdict:
        story.append(Paragraph("Assessment", styles["Heading2"]))
        story.append(Paragraph(f"<b>{escape(result.verdict.label)}</b> (severity {result.verdict.severity} of 5)", styles["BodyText"]))
        story.append(Paragraph(escape(result.verdict.reason), styles["BodyText"]))
        if result.crack:
            # The rule engine includes the configured number in its explanation.
            flag = result.exceeds_is456_limit
            status = "exceeds" if flag else "does not exceed" if flag is False else "could not be checked against"
            story.append(Paragraph(f"IS 456 check: the {result.exposure_class} exposure limit is {status} by the measured maximum crack width.", styles["BodyText"]))
        story.append(Spacer(1, 3 * mm))

    if result.cost:
        story.append(Paragraph("Repair estimate (Bill of Quantities)", styles["Heading2"]))
        if result.cost.rates_are_placeholder:
            story.append(Paragraph("Warning: rates are placeholders, not verified CPWD DSR prices.", styles["BodyText"]))
        header = ["Work", "Qty", "Rate", "Amount"]
        rows = [header]
        for item in result.cost.items:
            rows.append([Paragraph(escape(item.description), styles["BodyText"]),
                         f"{item.quantity:g} {escape(item.unit)}", _rupees(item.rate_rs), _rupees(item.amount_rs)])
        if not result.cost.items:
            rows.append(["No repair item recommended", "—", "—", _rupees(0)])
        rows.append(["Total", "", "", _rupees(result.cost.total_rs)])
        boq = Table(rows, colWidths=[76 * mm, 30 * mm, 31 * mm, 31 * mm], repeatRows=1)
        boq.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#174A63")),
                                 ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                 ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#B7C7CE")),
                                 ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E8F0F3")),
                                 ("ALIGN", (1, 1), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                 ("PADDING", (0, 0), (-1, -1), 5)]))
        story.extend([boq, Spacer(1, 2 * mm)])
        if result.verdict and result.crack:
            choices = compare_repair_options(result.verdict, result.crack)
            story.append(Paragraph(f"Indicative options: cheaper crack sealing {_rupees(choices['cheaper'].total_rs)}; "
                                   f"recommended repair {_rupees(choices['recommended'].total_rs)}. "
                                   "The cheaper option may not be suitable for structural damage.", styles["BodyText"]))

    # Keep the report useful even if analysis is incomplete or an image is absent.
    story.extend([Spacer(1, 3 * mm)])
    _add_optional_image(story, "Inspection photo", result.photo_path, styles)
    if result.crack:
        _add_optional_image(story, "Crack heatmap", result.crack.heatmap_path, styles)
    if result.audio:
        _add_optional_image(story, "Tap audio spectrum", result.audio.spectrum_image_path, styles)

    doc = SimpleDocTemplate(str(destination), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm, title="STHIRA Inspection Report")
    doc.build(story)
    return str(destination)
