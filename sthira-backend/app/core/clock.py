"""One place for "what time is it". All times in STHIRA are UTC."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
