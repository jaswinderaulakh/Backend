"""Repair quantities and CPWD-rate estimates for measured cracks."""
from __future__ import annotations

from app.core.config import load_cpwd_rates, load_rules
from app.core.schemas import CostEstimate, CostItem, CrackResult, Verdict


def _repair_ids(verdict: Verdict) -> list[str]:
    """Select configured repair catalogue entries for a verdict."""
    if verdict.label in {"No crack detected", "Inconclusive, tap test needed"}:
        return []
    by_label = {row["label"]: row["id"] for row in load_rules()["rules"]}
    rule_id = by_label.get(verdict.label)
    return {
        "shear_risk": ["epoxy_injection_grouting", "polymer_mortar_plastering"],
        "void_risk": ["epoxy_injection_grouting", "polymer_mortar_plastering"],
        "plaster_spalling": ["polymer_mortar_plastering"],
        "minor": ["crack_sealing"],
        "hairline": [],
    }.get(rule_id, [])


def _items_for(repair_ids: list[str], crack: CrackResult, rates: dict) -> list[CostItem]:
    catalogue = {item["id"]: item for item in rates["items"]}
    length_m = crack.length_mm / 1000.0
    items = []
    for repair_id in repair_ids:
        if repair_id not in catalogue:
            raise ValueError(f"Repair option '{repair_id}' is missing from config/cpwd_rates.json.")
        rate = catalogue[repair_id]
        # Running-metre work uses measured crack length. Surface work assumes a
        # 0.5 m wide repair strip: sqm = measured length in metres x 0.5 m.
        quantity = length_m if rate["unit"] == "rmt" else length_m * 0.5
        quantity = round(quantity, 2)
        amount = round(quantity * float(rate["rate_rs"]), 2)
        items.append(CostItem(description=rate["description"], unit=rate["unit"],
                              quantity=quantity, rate_rs=float(rate["rate_rs"]), amount_rs=amount))
    return items


def _estimate(repair_ids: list[str], crack: CrackResult, rates: dict) -> CostEstimate:
    items = _items_for(repair_ids, crack, rates)
    return CostEstimate(items=items, total_rs=round(sum(item.amount_rs for item in items), 2),
                        rates_are_placeholder=bool(rates.get("is_placeholder", True)))


def estimate_cost(verdict: Verdict, crack: CrackResult) -> CostEstimate:
    """Return the recommended repair BoQ estimate for one verdict."""
    return _estimate(_repair_ids(verdict), crack, load_cpwd_rates())


def compare_repair_options(verdict: Verdict, crack: CrackResult) -> dict[str, CostEstimate]:
    """Return a lower-cost crack-sealing estimate and recommended estimate.

    The comparison is indicative only; the lower-cost option may not be an
    appropriate structural repair. The verdict's recommended work remains the
    estimate returned by :func:`estimate_cost`.
    """
    rates = load_cpwd_rates()
    recommended_ids = _repair_ids(verdict)
    cheaper_ids = [] if not recommended_ids else ["crack_sealing"]
    return {"cheaper": _estimate(cheaper_ids, crack, rates),
            "recommended": _estimate(recommended_ids, crack, rates)}
