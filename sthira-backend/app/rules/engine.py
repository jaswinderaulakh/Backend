"""Configured crack/audio verdict rules for STHIRA."""
from __future__ import annotations

from typing import Any

from app.core.config import load_rules, load_thresholds
from app.core.schemas import AudioResult, CrackResult, Verdict


def _configured_value(path: str, thresholds: dict[str, Any]) -> float:
    """Resolve dotted config paths such as ``audio.void_below_hz``."""
    value: Any = thresholds
    try:
        for part in path.split("."):
            value = value[part]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Rule configuration refers to missing threshold '{path}'.") from exc
    if not isinstance(value, (int, float)):
        raise ValueError(f"Configured threshold '{path}' must be a number.")
    return float(value)


def _field_value(name: str, crack: CrackResult, audio: AudioResult) -> float | None:
    if name == "max_width_mm":
        return crack.max_width_mm
    if name == "mean_width_mm":
        return crack.mean_width_mm
    if name == "length_mm":
        return crack.length_mm
    if name == "angle_deg":
        return crack.angle_deg
    if name == "dominant_hz":
        return audio.dominant_hz
    raise ValueError(f"Rule configuration uses unsupported measurement '{name}'.")


def _matches(condition: dict, crack: CrackResult, audio: AudioResult,
             thresholds: dict[str, Any]) -> tuple[bool, str]:
    field = condition["field"]
    measured = _field_value(field, crack, audio)
    op = condition["op"]
    if measured is None:
        return False, f"{field} was not available"

    if op == "between":
        low = _configured_value(condition["low"], thresholds)
        high = _configured_value(condition["high"], thresholds)
        return low <= measured <= high, f"{field} {measured:g} is {low:g} to {high:g} (inclusive)"
    if op in {"gt", "lt", "gte", "lte", "eq"}:
        limit = _configured_value(condition["value"], thresholds)
        checks = {"gt": measured > limit, "lt": measured < limit,
                  "gte": measured >= limit, "lte": measured <= limit,
                  "eq": measured == limit}
        return checks[op], f"{field} {measured:g} {op} {limit:g}"
    raise ValueError(f"Rule configuration uses unsupported comparison '{op}'.")


def decide_verdict(crack: CrackResult, audio: AudioResult, exposure_class: str) -> Verdict:
    """Return the first matching configured verdict and its IS 456 context."""
    rules_config = load_rules()
    thresholds = load_thresholds()
    limits = thresholds.get("is456_crack_limit_mm", {})
    if exposure_class not in limits:
        allowed = ", ".join(sorted(limits))
        raise ValueError(f"Exposure class must be one of: {allowed}.")

    chosen = None
    evidence: list[str] = []
    for rule in rules_config["rules"]:
        checks = [_matches(condition, crack, audio, thresholds) for condition in rule["when"]]
        if all(passed for passed, _ in checks):
            chosen = rule
            evidence = [detail for _, detail in checks]
            break
    if chosen is None:
        chosen = rules_config["fallback"]
        evidence = [f"no configured rule matched (tap classification: {audio.classification}; "
                    f"dominant frequency: {audio.dominant_hz if audio.dominant_hz is not None else 'unavailable'} Hz)"]

    limit = float(limits[exposure_class])
    exceeds = crack.max_width_mm > limit
    is456 = (f"For {exposure_class} exposure, the IS 456 crack-width limit is {limit:g} mm; "
             f"the measured maximum is {crack.max_width_mm:g} mm, so it "
             f"{'exceeds' if exceeds else 'does not exceed'} the limit.")
    reason = (f"{'; '.join(evidence)}. {is456}")
    return Verdict(label=chosen["label"], severity=chosen["severity"], reason=reason)
