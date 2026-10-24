"""Building Health Index and trend calculations."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

from app.core.config import load_campus_config


def _get(value: Any, key: str, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def _severity(inspection: Any) -> int | None:
    direct = _get(inspection, "severity")
    verdict = _get(inspection, "verdict")
    if direct is None and verdict is not None:
        direct = _get(verdict, "severity")
    if direct is None:
        raw = _get(inspection, "result_json")
        if raw:
            try:
                payload = json.loads(raw) if isinstance(raw, str) else raw
                direct = (payload.get("verdict") or {}).get("severity")
            except (TypeError, ValueError, AttributeError):
                direct = None
    try:
        value = int(direct)
    except (TypeError, ValueError):
        return None
    return value if 1 <= value <= 5 else None


def _time_key(inspection: Any) -> tuple[float, int]:
    created = _get(inspection, "created_at") or _get(inspection, "completed_at")
    if isinstance(created, str):
        try:
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            created = None
    if isinstance(created, datetime):
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        timestamp = created.timestamp()
    else:
        timestamp = 0.0
    identity = _get(inspection, "id", _get(inspection, "inspection_id", 0)) or 0
    return timestamp, int(identity)


def latest_per_location(inspections: Iterable[Any]) -> list[Any]:
    """Pick the newest completed inspection for each floor/location pair."""
    latest: dict[tuple[str, str], Any] = {}
    for inspection in inspections:
        if _get(inspection, "status", "completed") != "completed":
            continue
        if _severity(inspection) is None:
            continue
        key = (str(_get(inspection, "floor", "")).strip().casefold(),
               str(_get(inspection, "location", "")).strip().casefold())
        old = latest.get(key)
        if old is None or _time_key(inspection) > _time_key(old):
            latest[key] = inspection
    return list(latest.values())


def calculate_health_index(inspections: Iterable[Any]) -> int:
    """Start at the configured score and subtract configured severity penalties."""
    config = load_campus_config()["health_index"]
    score = int(config["starting_score"])
    penalties = config["severity_penalties"]
    for inspection in latest_per_location(inspections):
        severity = _severity(inspection)
        if severity is not None:
            score -= int(penalties[str(severity)] if str(severity) in penalties else penalties[severity])
    return max(int(config["minimum_score"]), score)


def health_colour(index: int | float) -> str:
    """Return green, yellow, or red using the configured lower bounds."""
    bands = load_campus_config()["colour_bands"]
    if index >= float(bands["green_minimum"]):
        return "green"
    if index >= float(bands["yellow_minimum"]):
        return "yellow"
    return "red"


def health_index_trend(inspections: Iterable[Any]) -> list[dict[str, Any]]:
    """Return the score after each chronologically added inspection."""
    ordered = sorted(inspections, key=_time_key)
    seen: list[Any] = []
    trend = []
    for item in ordered:
        seen.append(item)
        created = _get(item, "created_at") or _get(item, "completed_at")
        if isinstance(created, datetime):
            date_text = created.isoformat()
        else:
            date_text = str(created or "")
        trend.append({"date": date_text, "health_index": calculate_health_index(seen)})
    return trend
